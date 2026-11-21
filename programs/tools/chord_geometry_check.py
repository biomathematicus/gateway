"""Check of a chord figure against the publication rule, from the PDF.

    python programs/tools/chord_geometry_check.py [figure.pdf ...]

A ribbon of a chord diagram is a count of students: on the ring, each
student of a flow occupies one piece of arc at the donor and one at the
acceptor, so the width of a ribbon states its count. A scan of CSV and
JSON files cannot see that. This program reads the vector figure itself,
recovers the count of every ribbon from the arc it spans at its source,
and fails when a ribbon holds fewer students than the minimum cell.

It needs, beside <figure>.pdf, the files that chord.py writes with it:
<figure>_stats.json (students drawn, number of sectors) and
<figure>_flows.csv (the flows drawn). Three things are checked:

  1. the recovered counts are whole numbers to within a small tolerance
     and add up to the students drawn;
  2. the smallest recovered count is at least the minimum cell;
  3. the recovered counts are the counts of <figure>_flows.csv, so the
     released file states what the figure encodes.

Geometry of student_success/chord.py: the sectors share 360 degrees minus
n_sectors * max(0.3, 120 / n_sectors) degrees of spacing, and every
student takes part in one flow, which occupies arc at both of its ends.
One student is therefore (360 - spacing) / (2 * students drawn) degrees.
The recovery of counts from ribbon arcs follows the check of the REV8
review of the manuscript. No student record is read.

Without arguments the program checks every figChord-*-majors.pdf under
programs/figures/student_success that has its two companion files.
"""
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

FIG = Path(__file__).resolve().parents[1] / "figures"
MIN_CELL = 10
RIBBON_ALPHA = 0.55      # link_kws alpha of chord.py: marks the ribbons
TOLERANCE = 0.02         # students


def recovered_counts(pdf: Path, students: int, sectors: int,
                     page: int = 0) -> np.ndarray:
    """count of students of every ribbon, from the arc at its source.
    `page` is the page of the PDF that holds the figure (the first page
    of a figure file; any page of a compiled manuscript)."""
    import fitz
    with fitz.open(pdf) as doc:
        drawings = doc[page].get_drawings()
    ribbons = [x for x in drawings
               if abs((x["fill_opacity"] or 0) - RIBBON_ALPHA) < 0.01]
    if not ribbons:
        raise ValueError(f"no ribbon found in {pdf.name}")
    start = np.array([[x["items"][0][1].x, x["items"][0][1].y]
                      for x in ribbons])
    # the ribbons start on one circle: least-squares center
    design = np.c_[2 * start[:, 0], 2 * start[:, 1], np.ones(len(start))]
    center = np.linalg.lstsq(design, (start ** 2).sum(axis=1),
                             rcond=None)[0][:2]
    degrees_per_student = (360 - sectors * max(0.3, 120 / sectors)) / (
        2 * students)
    out = []
    for ribbon in ribbons:
        first = last = ribbon["items"][0][1]
        for item in ribbon["items"]:
            if item[0] == "c":           # the ribbon leaves the ring
                break
            if item[0] != "l":
                raise ValueError("unexpected path along the source arc")
            last = item[-1]
        u = np.array([first.x, first.y]) - center
        v = np.array([last.x, last.y]) - center
        angle = abs(math.atan2(u[0] * v[1] - u[1] * v[0], u @ v))
        out.append(math.degrees(angle) / degrees_per_student)
    return np.array(out)


def check(pdf: Path) -> list[str]:
    """problems found in one figure; an empty list when it passes"""
    stem = pdf.with_suffix("")
    stats = json.loads(Path(f"{stem}_stats.json").read_text(encoding="utf-8"))
    with open(f"{stem}_flows.csv", newline="", encoding="utf-8") as fh:
        released = sorted(int(r["n_students"]) for r in csv.DictReader(fh))
    est = recovered_counts(pdf, stats["n_drawn_students"], stats["n_sectors"])
    counts = np.rint(est).astype(int)
    problems = []
    error = float(np.max(np.abs(est - counts)))
    if error > TOLERANCE:
        problems.append(f"counts not recovered as whole numbers "
                        f"(largest deviation {error:.3f})")
    if int(counts.sum()) != stats["n_drawn_students"]:
        problems.append(f"recovered counts add up to {int(counts.sum())}, "
                        f"not to the {stats['n_drawn_students']} drawn")
    small = int((counts < MIN_CELL).sum())
    if small:
        problems.append(f"{small} ribbons hold fewer than {MIN_CELL} "
                        f"students (smallest {int(counts.min())})")
    if sorted(counts.tolist()) != released:
        problems.append("the ribbons do not match the released flows file")
    print(f"  {pdf.name}: {len(counts)} ribbons, {int(counts.sum()):,} "
          f"students, smallest ribbon {int(counts.min())}, largest "
          f"deviation from a whole number {error:.4f}")
    return problems


def main(paths: list[str]) -> int:
    pdfs = [Path(p) for p in paths] or sorted(
        p for p in (FIG / "student_success").glob("figChord-*-majors.pdf")
        if Path(f"{p.with_suffix('')}_flows.csv").exists())
    bad = 0
    for pdf in pdfs:
        for problem in check(pdf):
            print(f"  FAIL {pdf.name}: {problem}")
            bad += 1
    print("chord geometry:", "clean" if not bad else f"{bad} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
