"""Release-boundary disclosure scan: find aggregate exports whose count
columns hold cells below the minimum-cell rule (10).

Scans every CSV under code/figures for columns whose names look like
student-support counts and reports files containing values below the
threshold. The scan reads aggregate artifacts only; it opens no
student-level records. Run it before any package leaves the authorized
team, and treat any hit as a release blocker until suppressed,
aggregated, or cleared by the custodian.

Usage: python code/tools/disclosure_scan.py [root]
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

MIN_CELL = 10
# column names that denote how many students support a row
COUNT_PAT = re.compile(
    r"^(n|N|count|n_students|n_entrants|students|n_matched|n_kids"
    r"|n_cells|n_schools_students|entrants|with_dfw)$|_students$|^n_(?!schools"
    r"|districts|states|tracts|cycles|sections|courses|majors|subjects"
    r"|files|rows)\w+$")


def scan_file(path: Path) -> dict | None:
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return None
            cols = [c for c in reader.fieldnames if c and COUNT_PAT.match(c)]
            if not cols:
                return None
            hits: dict[str, list[float]] = {c: [] for c in cols}
            for row in reader:
                for c in cols:
                    raw = (row.get(c) or "").strip()
                    if not raw:
                        continue
                    try:
                        v = float(raw)
                    except ValueError:
                        continue
                    if 0 < v < MIN_CELL:
                        hits[c].append(v)
    except OSError:
        return None
    hits = {c: v for c, v in hits.items() if v}
    if not hits:
        return None
    return {"file": str(path), "columns": {
        c: {"cells_below_min": len(v), "minimum": min(v)}
        for c, v in hits.items()}}


def main(root: str) -> int:
    base = Path(root)
    findings = []
    for path in sorted(base.rglob("*.csv")):
        f = scan_file(path)
        if f:
            findings.append(f)
    if not findings:
        print(f"disclosure scan clean under {base} (threshold {MIN_CELL})")
        return 0
    print(f"disclosure scan: {len(findings)} file(s) with count cells "
          f"below {MIN_CELL} under {base}\n")
    for f in findings:
        cols = ", ".join(f"{c} ({d['cells_below_min']} cells, min "
                         f"{d['minimum']:g})"
                         for c, d in f["columns"].items())
        print(f"  {f['file']}\n    {cols}")
    print("\nEvery file above is a release blocker until suppressed, "
          "aggregated, or cleared by the data custodian.")
    return 1


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "figures")
    raise SystemExit(main(target))
