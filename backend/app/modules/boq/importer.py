"""BOQ file import engine (pure functions, no database).

read_table      CSV (UTF-8, UTF-8 with BOM, Windows-1252; , ; tab | delimiters) or XLSX
detect_header   the header row among the first rows (title rows above it are skipped)
suggest_mapping column -> field from header synonyms (or a saved template)
validate        normalise rows, report errors and warnings per source row, merge lines

Nothing here writes anything; the service commits a revision only after validation passes.
"""

import csv
import io
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

FIELDS: dict[str, str] = {
    "line_no": "Line no.",
    "ref_des": "Ref des",
    "qty": "Qty per unit",
    "mpn": "MPN",
    "manufacturer": "Manufacturer",
    "description": "Description",
    "value": "Value",
    "package": "Footprint / package",
    "dnp": "DNP",
    "category": "Category",
    "unit": "Unit",
    "unit_price": "Unit price",
    "preferred_vendor": "Preferred vendor",
    "notes": "Notes",
}

_SYNONYMS: dict[str, list[str]] = {
    "line_no": [
        "line no",
        "line",
        "line number",
        "item",
        "item no",
        "sr no",
        "s no",
        "sl no",
        "sno",
    ],
    "ref_des": [
        "ref des",
        "refdes",
        "reference",
        "references",
        "ref",
        "refs",
        "designator",
        "designators",
        "part reference",
        "ref designator",
    ],
    "qty": [
        "qty per unit",
        "qty",
        "quantity",
        "qty unit",
        "quantity per pcb",
        "qty per board",
        "qty per pcb",
        "count",
        "quantity per unit",
    ],
    "mpn": [
        "mpn",
        "mfr part number",
        "manufacturer part number",
        "mfg part number",
        "mfr pn",
        "mfr part",
        "part number",
        "mfg pn",
        "manufacturer pn",
        "mfr part no",
        "manufacturer part no",
    ],
    "manufacturer": ["manufacturer", "mfr", "mfg", "make", "maker", "brand", "manufacturer name"],
    "description": ["description", "desc", "part description", "comment", "item description"],
    "value": ["value", "val"],
    "package": ["package", "footprint", "case", "package case", "pkg", "size"],
    "dnp": ["dnp", "dnf", "do not populate", "do not fit", "not fitted"],
    "category": ["category", "type", "part type", "class", "component type"],
    "unit": ["unit", "uom", "units"],
    "unit_price": [
        "unit price",
        "unit price inr",
        "price",
        "unit cost",
        "cost",
        "rate",
        "price inr",
    ],
    "preferred_vendor": ["preferred vendor", "vendor", "supplier", "preferred supplier"],
    "notes": ["notes", "note", "remarks", "remark", "comments"],
}

COUNTABLE_UNITS = {"pcs", "pc", "ea", "each", "nos", "no", "set", "sets", "unit", "units"}
_TRUE = {"y", "yes", "true", "1", "dnp", "dnf", "x", "not fitted", "nf"}
_CATEGORIES = {
    "passive": "Passive",
    "passives": "Passive",
    "capacitor": "Passive",
    "resistor": "Passive",
    "ic": "IC",
    "ics": "IC",
    "integrated circuit": "IC",
    "discrete": "Discrete",
    "connector": "Connector",
    "connectors": "Connector",
    "electromechanical": "Electromechanical",
    "magnetics": "Magnetics",
    "inductor": "Magnetics",
    "opto": "Opto",
    "led": "Opto",
    "crystal": "Crystal",
    "oscillator": "Crystal",
    "mechanical": "Mechanical",
    "pcb": "PCB",
    "consumable": "Consumable",
    "other": "Other",
}


def norm_header(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def norm_mpn(mpn: str) -> str:
    """Comparison key for MPNs: case-, space- and dash-insensitive."""
    return re.sub(r"[\s\-_./]+", "", mpn).upper()


# ---------------------------------------------------------------- reading


@dataclass
class RawTable:
    rows: list[list[str]]
    encoding: str | None
    delimiter: str | None
    sheet: str | None = None


class ImportFormatError(ValueError):
    """The file cannot be read as a table at all."""


def decode(content: bytes) -> tuple[str, str]:
    if content.startswith(b"\xef\xbb\xbf"):
        return content[3:].decode("utf-8"), "utf-8-sig"
    try:
        return content.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace"), "windows-1252"


def _sniff_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:30])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in ",;\t|"}
        return max(counts, key=lambda d: counts[d])


def read_table(content: bytes, filename: str) -> RawTable:
    if not content:
        raise ImportFormatError("The file is empty")
    if filename.lower().endswith((".xlsx", ".xlsm")) or content.startswith(b"PK\x03\x04"):
        return _read_xlsx(content)
    text, encoding = decode(content)
    if "\x00" in text:
        raise ImportFormatError("This does not look like a CSV or XLSX file")
    delimiter = _sniff_delimiter(text)
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delimiter)]
    return RawTable(rows=rows, encoding=encoding, delimiter=delimiter)


def _read_xlsx(content: bytes) -> RawTable:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ImportFormatError("The XLSX file could not be opened") from exc
    ws = wb.worksheets[0]
    rows: list[list[str]] = []
    for values in ws.iter_rows(values_only=True):
        rows.append(["" if v is None else _cell_text(v) for v in values])
    wb.close()
    return RawTable(rows=rows, encoding=None, delimiter=None, sheet=ws.title)


def _cell_text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


# ---------------------------------------------------------------- header and mapping


def _field_for(header: str) -> str | None:
    h = norm_header(header)
    for fld, names in _SYNONYMS.items():
        if h in names:
            return fld
    return None


def detect_header(rows: list[list[str]], scan: int = 20) -> int:
    """Index of the row with the most recognised headers (title rows above are skipped)."""
    best, best_score = 0, -1
    for i, row in enumerate(rows[:scan]):
        score = len({f for c in row if (f := _field_for(c))})
        if score > best_score:
            best, best_score = i, score
    return best


def suggest_mapping(headers: list[str]) -> dict[str, int]:
    """field -> column index; the first column wins when two match the same field."""
    mapping: dict[str, int] = {}
    for idx, header in enumerate(headers):
        fld = _field_for(header)
        if fld and fld not in mapping:
            mapping[fld] = idx
    return mapping


def mapping_from_template(headers: list[str], template: dict[str, str]) -> dict[str, int]:
    """Template stores field -> normalised header text, so it works when columns move."""
    by_header = {norm_header(h): i for i, h in enumerate(headers)}
    return {fld: by_header[h] for fld, h in template.items() if h in by_header}


def template_from_mapping(headers: list[str], mapping: dict[str, int]) -> dict[str, str]:
    return {fld: norm_header(headers[i]) for fld, i in mapping.items() if 0 <= i < len(headers)}


# ---------------------------------------------------------------- validation


@dataclass
class Issue:
    row: int  # 1-based row number in the source file
    field: str | None
    code: str
    message: str
    severity: str  # "error" | "warning" | "info"


@dataclass
class ImportLine:
    rows: list[int]
    ref_des: list[str]
    qty_per_unit: Decimal
    mpn: str | None
    manufacturer: str | None
    description: str | None
    value: str | None
    package: str | None
    category: str | None
    unit: str
    dnp: bool
    unit_price: Decimal | None
    preferred_vendor: str | None
    notes: str | None
    part_known: bool = False
    master_mpn: str | None = None


@dataclass
class ValidationResult:
    lines: list[ImportLine]
    issues: list[Issue]
    source_rows: int
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    def to_json(self) -> dict[str, Any]:
        def line(ln: ImportLine) -> dict[str, Any]:
            d = asdict(ln)
            d["qty_per_unit"] = str(ln.qty_per_unit)
            d["unit_price"] = None if ln.unit_price is None else str(ln.unit_price)
            return d

        return {
            "lines": [line(ln) for ln in self.lines],
            "issues": [asdict(i) for i in self.issues],
            "source_rows": self.source_rows,
            "stats": self.stats,
        }


_RANGE = re.compile(r"^([A-Za-z]+)(\d+)\s*[-\u2013]\s*(?:([A-Za-z]+))?(\d+)$")


def split_ref_des(text: str) -> list[str]:
    """'C1, C2,C5' / 'R1 R2' / 'R1-R4' / 'U1;U2' -> list of designators (ranges expanded)."""
    out: list[str] = []
    for token in re.split(r"[,;\s]+", text.strip()):
        if not token:
            continue
        m = _RANGE.match(token)
        if m and (m.group(3) is None or m.group(3).upper() == m.group(1).upper()):
            prefix, start, end = m.group(1), int(m.group(2)), int(m.group(4))
            if start <= end and end - start <= 2000:
                out.extend(f"{prefix}{n}" for n in range(start, end + 1))
                continue
        out.append(token)
    return out


def _natural(ref: str) -> tuple[str, int, str]:
    m = re.match(r"^([A-Za-z_]*)(\d*)(.*)$", ref)
    assert m is not None
    return (m.group(1).upper(), int(m.group(2) or 0), m.group(3))


def parse_decimal(text: str, *, decimal_comma: bool = False) -> Decimal | None:
    cleaned = re.sub(r"[₹$€£\s]|INR|Rs\.?", "", text, flags=re.IGNORECASE)
    if decimal_comma:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(text) from exc
    if not value.is_finite():
        raise ValueError(text)
    return value


def normalise_category(text: str) -> str | None:
    t = text.strip()
    if not t:
        return None
    return _CATEGORIES.get(t.lower(), t[:32])


def validate(
    rows: list[list[str]],
    header_index: int,
    mapping: dict[str, int],
    known_parts: Mapping[str, tuple[str, str | None]] | None = None,
    *,
    decimal_comma: bool = False,
    merge: bool = True,
) -> ValidationResult:
    """known_parts: normalised MPN -> (MPN as stored in the part master, manufacturer)."""
    known = known_parts or {}
    issues: list[Issue] = []
    if "mpn" not in mapping and "description" not in mapping:
        issues.append(
            Issue(
                header_index + 1,
                "mpn",
                "mapping_incomplete",
                "Map at least the MPN column",
                "error",
            )
        )
    if "qty" not in mapping and "ref_des" not in mapping:
        issues.append(
            Issue(
                header_index + 1,
                "qty",
                "mapping_incomplete",
                "Map the quantity or ref des column",
                "error",
            )
        )
    if issues:
        return ValidationResult([], issues, 0)

    def cell(row: list[str], fld: str) -> str:
        idx = mapping.get(fld)
        return row[idx].strip() if idx is not None and idx < len(row) else ""

    parsed: list[ImportLine] = []
    seen_ref: dict[str, int] = {}
    raw_mpn_by_norm: dict[str, tuple[str, int]] = {}
    data_rows = 0
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(c.strip() for c in row):
            continue
        data_rows += 1
        refs = split_ref_des(cell(row, "ref_des"))
        mpn = cell(row, "mpn") or None
        dnp = cell(row, "dnp").lower() in _TRUE
        unit = (cell(row, "unit") or "pcs").lower()[:16]
        row_errors = 0

        qty_text = cell(row, "qty")
        qty: Decimal | None
        try:
            qty = parse_decimal(qty_text, decimal_comma=decimal_comma)
        except ValueError:
            issues.append(
                Issue(
                    offset, "qty", "invalid_qty", f"Quantity '{qty_text}' is not a number", "error"
                )
            )
            qty, row_errors = None, row_errors + 1
        if qty is not None and qty < 0:
            issues.append(
                Issue(offset, "qty", "invalid_qty", "Quantity cannot be negative", "error")
            )
            row_errors += 1
        if qty is None and not row_errors:
            if refs:
                qty = Decimal(len(refs))
                issues.append(
                    Issue(
                        offset,
                        "qty",
                        "qty_from_ref_des",
                        f"No quantity given; using the ref des count ({len(refs)})",
                        "warning",
                    )
                )
            else:
                issues.append(Issue(offset, "qty", "missing_qty", "Quantity is missing", "error"))
                row_errors += 1

        if not mpn and not dnp:
            issues.append(
                Issue(
                    offset,
                    "mpn",
                    "missing_mpn",
                    "MPN is missing (only DNP lines may omit it)",
                    "error",
                )
            )
            row_errors += 1

        if (
            not row_errors
            and qty is not None
            and refs
            and unit in COUNTABLE_UNITS
            and qty != len(refs)
        ):
            issues.append(
                Issue(
                    offset,
                    "ref_des",
                    "qty_ref_des_mismatch",
                    f"Quantity {qty.normalize()} does not match {len(refs)} ref des",
                    "error",
                )
            )
            row_errors += 1

        for ref in refs:
            key = ref.upper()
            if key in seen_ref:
                issues.append(
                    Issue(
                        offset,
                        "ref_des",
                        "duplicate_ref_des",
                        f"{ref} is also on row {seen_ref[key]}",
                        "error",
                    )
                )
                row_errors += 1
            else:
                seen_ref[key] = offset

        price_text = cell(row, "unit_price")
        price: Decimal | None = None
        try:
            price = parse_decimal(price_text, decimal_comma=decimal_comma)
            if price is not None and price < 0:
                raise ValueError(price_text)
        except ValueError:
            issues.append(
                Issue(
                    offset,
                    "unit_price",
                    "invalid_price",
                    f"Unit price '{price_text}' is not a valid amount",
                    "warning",
                )
            )
            price = None

        master_mpn: str | None = None
        part_known = False
        if mpn:
            n = norm_mpn(mpn)
            if n in known:
                part_known = True
                master_mpn = known[n][0]
                if master_mpn != mpn:
                    issues.append(
                        Issue(
                            offset,
                            "mpn",
                            "mpn_variant_master",
                            f"'{mpn}' matches part master '{master_mpn}' "
                            "(different casing/spacing)",
                            "warning",
                        )
                    )
            else:
                issues.append(
                    Issue(
                        offset,
                        "mpn",
                        "unknown_part",
                        f"'{mpn}' is not in the part master; it will be created on commit",
                        "warning",
                    )
                )
            if n in raw_mpn_by_norm and raw_mpn_by_norm[n][0] != mpn:
                other, other_row = raw_mpn_by_norm[n]
                issues.append(
                    Issue(
                        offset,
                        "mpn",
                        "mpn_variant",
                        f"'{mpn}' looks like '{other}' on row {other_row} "
                        "(different casing/spacing)",
                        "warning",
                    )
                )
            raw_mpn_by_norm.setdefault(n, (mpn, offset))

        if row_errors:
            continue
        assert qty is not None
        parsed.append(
            ImportLine(
                rows=[offset],
                ref_des=refs,
                qty_per_unit=qty,
                mpn=mpn,
                manufacturer=cell(row, "manufacturer") or None,
                description=cell(row, "description") or None,
                value=cell(row, "value") or None,
                package=cell(row, "package") or None,
                category=normalise_category(cell(row, "category")),
                unit=unit,
                dnp=dnp,
                unit_price=price,
                preferred_vendor=cell(row, "preferred_vendor") or None,
                notes=cell(row, "notes") or None,
                part_known=part_known,
                master_mpn=master_mpn,
            )
        )

    lines = _merge(parsed, issues) if merge else parsed
    for ln in lines:
        ln.ref_des.sort(key=_natural)
    stats = {
        "source_rows": data_rows,
        "lines": len(lines),
        "errors": sum(1 for i in issues if i.severity == "error"),
        "warnings": sum(1 for i in issues if i.severity == "warning"),
        "unknown_parts": sum(1 for ln in lines if ln.mpn and not ln.part_known),
        "dnp_lines": sum(1 for ln in lines if ln.dnp),
    }
    if data_rows == 0:
        issues.append(
            Issue(header_index + 1, None, "no_rows", "No data rows below the header", "error")
        )
        stats["errors"] += 1
    return ValidationResult(lines, issues, data_rows, stats)


def _merge(lines: list[ImportLine], issues: list[Issue]) -> list[ImportLine]:
    """Lines with the same MPN (and manufacturer, and DNP state) become one line: quantities
    add up and ref des are concatenated."""
    merged: dict[tuple[str, str, bool], ImportLine] = {}
    out: list[ImportLine] = []
    for ln in lines:
        if not ln.mpn:
            out.append(ln)
            continue
        key = (norm_mpn(ln.mpn), (ln.manufacturer or "").strip().upper(), ln.dnp)
        if key in merged:
            target = merged[key]
            target.qty_per_unit += ln.qty_per_unit
            target.ref_des.extend(ln.ref_des)
            target.rows.extend(ln.rows)
            issues.append(
                Issue(
                    ln.rows[0],
                    "mpn",
                    "merged",
                    f"Merged into the line from row {target.rows[0]} (same MPN)",
                    "info",
                )
            )
        else:
            merged[key] = ln
            out.append(ln)
    return out


def error_report_csv(issues: list[Issue]) -> str:
    """Downloadable report: one row per issue, sorted by source row."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["Row", "Severity", "Field", "Code", "Message"])
    for i in sorted(
        issues, key=lambda x: (x.row, {"error": 0, "warning": 1, "info": 2}.get(x.severity, 3))
    ):
        w.writerow([i.row, i.severity, FIELDS.get(i.field or "", i.field or ""), i.code, i.message])
    return "﻿" + buf.getvalue()
