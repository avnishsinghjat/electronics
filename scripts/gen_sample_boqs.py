"""Generate the binary / large BOQ samples deterministically.

    backend/.venv/bin/python scripts/gen_sample_boqs.py

Writes samples/boq-clean.xlsx (same content as boq-clean.csv) and samples/boq-2000.csv
(2,000 distinct lines for the import performance test).
"""

import csv
import random
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1] / "samples"


def xlsx() -> None:
    with (ROOT / "boq-clean.csv").open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "BOQ"
    ws.append(["Customer BOQ - Controller board rev A"])  # title row above the header
    for r in rows:
        ws.append([float(c) if c.replace(".", "", 1).isdigit() and "," not in c else c for c in r])
    wb.save(ROOT / "boq-clean.xlsx")


def large(n: int = 2000) -> None:
    rng = random.Random(2026)
    cats = [("C", "Passive", "Cap"), ("R", "Passive", "Res"), ("U", "IC", "IC"), ("D", "Discrete", "Diode"), ("J", "Connector", "Conn")]
    ref_counter: dict[str, int] = {}
    with (ROOT / "boq-2000.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["line_no", "ref_des", "qty_per_unit", "mpn", "manufacturer", "description", "package", "category", "unit", "dnp", "unit_price_inr"])
        for i in range(1, n + 1):
            prefix, cat, desc = rng.choice(cats)
            qty = rng.randint(1, 4)
            refs = []
            for _ in range(qty):
                ref_counter[prefix] = ref_counter.get(prefix, 0) + 1
                refs.append(f"{prefix}{ref_counter[prefix]}")
            w.writerow([i, ",".join(refs), qty, f"PERF-{prefix}-{i:05d}", "PerfCo", f"{desc} {i}", "0603", cat, "pcs", "N", f"{rng.uniform(0.1, 500):.2f}"])


if __name__ == "__main__":
    xlsx()
    large()
    print("wrote", ROOT / "boq-clean.xlsx", "and", ROOT / "boq-2000.csv")
