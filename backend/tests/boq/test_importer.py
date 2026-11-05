"""Import engine on every sample file, encoding, header layout and error type."""

from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.boq.importer import (
    ImportFormatError,
    detect_header,
    error_report_csv,
    mapping_from_template,
    norm_mpn,
    read_table,
    split_ref_des,
    suggest_mapping,
    template_from_mapping,
    validate,
)

SAMPLES = Path(__file__).resolve().parents[3] / "samples"
KNOWN = {
    norm_mpn(m): (m, mfr)
    for m, mfr in [
        ("GRM188R71H104KA93D", "Murata"),
        ("GRM21BR61E106KA73L", "Murata"),
        ("GRM1885C1H220JA01D", "Murata"),
        ("RC0603FR-0710KL", "Yageo"),
        ("RC0603FR-071KL", "Yageo"),
        ("RC0603FR-0722RL", "Yageo"),
        ("BLM18PG221SN1D", "Murata"),
        ("STM32F407VGT6", "STMicroelectronics"),
        ("AMS1117-3.3", "AMS"),
        ("USBLC6-2SC6", "STMicroelectronics"),
        ("ABM8-8.000MHZ-B2-T", "Abracon"),
        ("LTST-C191KGKT", "Lite-On"),
        ("10118194-0001LF", "Amphenol"),
        ("TS-1187A-B-A-B", "XKB"),
    ]
}


def load(name: str):
    content = (SAMPLES / name).read_bytes()
    table = read_table(content, name)
    header = detect_header(table.rows)
    mapping = suggest_mapping(table.rows[header])
    return table, header, mapping


def codes(result, severity: str | None = None) -> list[tuple[int, str]]:
    return [(i.row, i.code) for i in result.issues if severity is None or i.severity == severity]


def test_clean_csv_has_no_errors_and_recognises_all_columns() -> None:
    table, header, mapping = load("boq-clean.csv")
    assert (table.encoding, table.delimiter, header) == ("utf-8", ",", 0)
    assert set(mapping) == {
        "line_no",
        "ref_des",
        "qty",
        "mpn",
        "manufacturer",
        "description",
        "value",
        "package",
        "category",
        "unit",
        "dnp",
        "preferred_vendor",
        "unit_price",
        "notes",
    }
    result = validate(table.rows, header, mapping, KNOWN)
    assert result.error_count == 0
    assert codes(result, "warning") == []
    assert result.stats == {
        "source_rows": 15,
        "lines": 15,
        "errors": 0,
        "warnings": 0,
        "unknown_parts": 0,
        "dnp_lines": 1,
    }
    caps = result.lines[2]
    assert caps.ref_des == ["C6", "C7", "C8", "C9"]  # range expanded
    assert caps.qty_per_unit == Decimal(4)
    dnp = result.lines[-1]
    assert dnp.dnp is True and dnp.mpn is None and dnp.category == "Connector"
    assert result.lines[7].unit_price == Decimal("780.00")


def test_xlsx_with_title_row() -> None:
    table, header, mapping = load("boq-clean.xlsx")
    assert table.sheet == "BOQ" and header == 1
    result = validate(table.rows, header, mapping, KNOWN)
    assert result.error_count == 0 and len(result.lines) == 15
    assert result.lines[0].qty_per_unit == Decimal(3)


def test_messy_windows_1252_reports_every_error_type() -> None:
    table, header, mapping = load("boq-messy.csv")
    assert table.encoding == "windows-1252"
    assert header == 3  # two title rows and a blank line above the header
    assert mapping == {
        "line_no": 0,
        "ref_des": 1,
        "qty": 2,
        "mpn": 3,
        "manufacturer": 4,
        "description": 5,
        "unit_price": 6,
        "notes": 7,
    }
    result = validate(table.rows, header, mapping, KNOWN)
    errors = codes(result, "error")
    assert (6, "missing_mpn") in errors
    assert (7, "invalid_qty") in errors  # "two"
    assert (9, "duplicate_ref_des") in errors  # R3 again
    assert (10, "qty_ref_des_mismatch") in errors  # 3 vs U1,U2
    assert (16, "invalid_qty") in errors  # negative
    assert (16, "qty_ref_des_mismatch") not in errors  # one error per cause
    warnings = codes(result, "warning")
    assert (11, "unknown_part") in warnings
    assert (12, "mpn_variant_master") in warnings  # stm32f407vgt6 vs STM32F407VGT6
    assert (14, "invalid_price") in warnings
    assert (13, "merged") in codes(result, "info")
    assert "µ" in table.rows[5][5] and "±" in table.rows[10][5]  # decoded correctly
    first = result.lines[0]
    assert first.ref_des == ["C1", "C2", "C10", "C11"]  # merged, naturally sorted
    assert first.qty_per_unit == Decimal(4)
    assert result.stats["source_rows"] == 11  # blank lines ignored


def test_kicad_bom_export() -> None:
    table, header, mapping = load("kicad-bom.csv")
    assert {"ref_des", "value", "package", "qty", "dnp", "mpn", "manufacturer"} <= set(mapping)
    result = validate(table.rows, header, mapping, KNOWN)
    assert result.error_count == 0
    tp = next(ln for ln in result.lines if ln.ref_des == ["TP1", "TP2"])
    assert tp.dnp is True and tp.mpn is None
    assert result.stats["unknown_parts"] == 4  # STM32G431, TPS62162, LQH3, 61300511121 not in KNOWN
    assert (
        next(ln for ln in result.lines if ln.mpn == "61300511121").manufacturer
        == "Würth Elektronik"
    )


def test_semicolon_utf8_bom_with_decimal_comma_and_metres() -> None:
    content = (SAMPLES / "boq-semicolon-utf8bom.csv").read_bytes()
    table = read_table(content, "x.csv")
    assert (table.encoding, table.delimiter) == ("utf-8-sig", ";")
    assert table.rows[0][0] == "Pos"  # BOM stripped
    mapping = suggest_mapping(table.rows[0])
    mapping["qty"] = 2  # "Menge" is not a known header: the user maps it
    result = validate(table.rows, 0, mapping, KNOWN, decimal_comma=True)
    assert result.error_count == 0
    wire = result.lines[0]
    assert (wire.qty_per_unit, wire.unit, wire.unit_price) == (
        Decimal("1.5"),
        "m",
        Decimal("12.50"),
    )
    assert result.lines[1].ref_des == ["C1", "C2"]


def test_two_thousand_line_sample_parses() -> None:
    table, header, mapping = load("boq-2000.csv")
    result = validate(table.rows, header, mapping, {})
    assert result.error_count == 0 and len(result.lines) == 2000


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("C1, C2,C5", ["C1", "C2", "C5"]),
        ("R1 R2", ["R1", "R2"]),
        ("U1;U2", ["U1", "U2"]),
        ("R1-R4", ["R1", "R2", "R3", "R4"]),
        ("C10-12", ["C10", "C11", "C12"]),
        ("TP1-R3", ["TP1-R3"]),  # mixed prefixes are not a range
        ("", []),
    ],
)
def test_split_ref_des(text: str, expected: list[str]) -> None:
    assert split_ref_des(text) == expected


def test_qty_from_ref_des_when_missing_and_missing_qty_error() -> None:
    rows = [["ref", "mpn", "qty"], ["R1,R2", "RC0603FR-0710KL", ""], ["", "RC0603FR-071KL", ""]]
    result = validate(rows, 0, suggest_mapping(rows[0]), KNOWN)
    assert (2, "qty_from_ref_des") in codes(result, "warning")
    assert (3, "missing_qty") in codes(result, "error")
    assert result.lines[0].qty_per_unit == Decimal(2)


def test_non_countable_units_skip_ref_des_count_check() -> None:
    rows = [["ref", "mpn", "qty", "unit"], ["W1", "WIRE-1", "2.5", "m"]]
    result = validate(rows, 0, suggest_mapping(rows[0]), {})
    assert result.error_count == 0


def test_mpn_variant_within_file_and_merge_disabled() -> None:
    rows = [["ref", "mpn", "qty"], ["R1", "RC0603FR-0710KL", "1"], ["R2", "rc0603fr 0710kl", "1"]]
    result = validate(rows, 0, suggest_mapping(rows[0]), {}, merge=False)
    assert (3, "mpn_variant") in codes(result, "warning")
    assert len(result.lines) == 2
    merged = validate(rows, 0, suggest_mapping(rows[0]), {})
    assert len(merged.lines) == 1 and merged.lines[0].ref_des == ["R1", "R2"]


def test_dnp_and_fitted_lines_of_same_mpn_do_not_merge() -> None:
    rows = [["ref", "mpn", "qty", "dnp"], ["R1", "X1", "1", ""], ["R2", "X1", "1", "DNP"]]
    assert len(validate(rows, 0, suggest_mapping(rows[0]), {}).lines) == 2


def test_incomplete_mapping_is_an_error() -> None:
    rows = [["foo", "bar"], ["1", "2"]]
    result = validate(rows, 0, {}, {})
    assert {i.code for i in result.issues} == {"mapping_incomplete"}


def test_no_rows_is_an_error() -> None:
    rows = [["ref", "mpn", "qty"]]
    result = validate(rows, 0, suggest_mapping(rows[0]), {})
    assert [i.code for i in result.issues] == ["no_rows"]


def test_mapping_template_round_trip_survives_column_reorder() -> None:
    headers_a = ["Item", "Designator", "Quantity", "Mfr Part Number"]
    template = template_from_mapping(headers_a, {"ref_des": 1, "qty": 2, "mpn": 3})
    headers_b = ["Mfr Part Number", "Quantity", "Designator", "Extra"]
    assert mapping_from_template(headers_b, template) == {"mpn": 0, "qty": 1, "ref_des": 2}


def test_unreadable_files() -> None:
    with pytest.raises(ImportFormatError):
        read_table(b"", "empty.csv")
    with pytest.raises(ImportFormatError):
        read_table(b"PK\x03\x04not really a zip", "fake.xlsx")


def test_error_report_csv_sorted_with_bom() -> None:
    table, header, mapping = load("boq-messy.csv")
    report = error_report_csv(validate(table.rows, header, mapping, KNOWN).issues)
    assert report.startswith("﻿Row,Severity,Field,Code,Message\r\n")
    rows = report.strip().splitlines()[1:]
    assert [int(r.split(",")[0]) for r in rows] == sorted(int(r.split(",")[0]) for r in rows)
    assert any("missing_mpn" in r for r in rows)
