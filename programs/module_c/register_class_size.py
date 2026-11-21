"""Write the registration record of the class-size addendum.

Hashes the frozen addendum, its code, and the Module C files it imports,
and writes `class_size_registration.md` beside the plan as a typed
DECISION event in the VER9 format. Run once, at the freeze, before the
registered estimation on real grades.
"""
import hashlib
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PLAN_DIR = ROOT / "Economics" / "Paper0" / "module_c"
FILES = [PLAN_DIR / "class_size_addendum.md",
         HERE / "cs_data.py", HERE / "run_class_size.py",
         HERE / "mc_data.py", HERE / "mc_models.py", HERE / "run_module_c.py",
         HERE.parent / "figures" / "module_c" / "cohorts_2014_2019"
         / "stage0_subjects.csv"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = PLAN_DIR / "class_size_registration.md"
    if out.exists() and "--force" not in sys.argv:
        raise SystemExit(f"{out} exists; registration is written once")
    today = date.today().isoformat()
    lines = [
        "# Typed event: registration of the class-size addendum to Module C "
        "(P0-D06)",
        "",
        "Status: the design decisions listed in the addendum header were "
        "accepted by the PI on " + today + ". The specification beyond them "
        "(the model ladder, hypotheses H3 and H4, the support thresholds, "
        "and the 45-student cap) was fixed by the analyst before the freeze; "
        "a PI amendment to any of it enters Section 14 of the addendum as a "
        "deviation. The event follows the §0.4 template of "
        "`VER9_Architecture.md` and is ready for entry into `VER9_Log.md`. "
        "It was written before any within-course model was fitted to "
        "unshuffled grades; Section 12 of the addendum lists what was seen "
        "before the freeze.",
        "",
        "```yaml",
        f"event_id: EVT-P0-D06-CLASS-SIZE-ADDENDUM-{today}",
        "event_type: DECISION",
        "object_type: DELIVERABLE",
        "object_id: P0-D06",
        "claim_id: null",
        "document: VER9_paper0_math_gateway.md",
        "source_path: Economics/Paper0/module_c/class_size_addendum.md",
        'source_locator: "# Module C addendum: section size and first-year '
        'performance"',
        f"source_sha256: {sha(FILES[0])}",
        "decision: ACCEPTED",
        "decision_owner: PI",
        f"effective_at: {today}",
        "text_exact: >",
        "  The class-size addendum to the Module C analysis plan, version",
        "  1.0, is frozen. Outcome estimation for this question proceeds",
        "  under its text. Any later change is recorded in Section 14 of the",
        "  addendum with date and reason, and results from a deviating",
        "  analysis are labeled exploratory.",
        "reason_exact: >",
        "  PI decisions of " + today + ": the class-size curves are to be",
        "  examined as evidence for an intervention with a model of smaller",
        "  sections; all 25 subjects with mathematics first; next-course",
        "  grade as the leniency check; registration before estimation on",
        "  real grades; section size within a course varies for logistical",
        "  reasons.",
        "```",
        "",
        "## Frozen inputs",
        "",
        "| Object | SHA-256 |",
        "|---|---|",
    ]
    for f in FILES:
        lines.append(f"| `{f.relative_to(ROOT).as_posix()}` | `{sha(f)}` |")
    lines += ["",
              "The three `mc_*` and `run_module_c` files are the Module C "
              "pipeline as it stands after deviation D1; the addendum imports "
              "them unchanged. A whole-file hash cannot sit inside the file "
              "it describes, so the addendum's hash lives here.", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
