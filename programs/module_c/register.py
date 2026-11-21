"""Write the Module C registration record.

Hashes the frozen plan, the Stage 0 maps, the pipeline code, and the
school crosswalk, and writes `registration_event.md` beside the plan as a
typed DECISION event in the VER9 format. Run once, at the freeze, before
any registered estimation.
"""
import hashlib
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent
ROOT = CODE.parent
sys.path.insert(0, str(CODE))
from gateway import db  # noqa: E402

PLAN_DIR = ROOT / "Economics" / "Paper0" / "module_c"
FILES = [PLAN_DIR / "analysis_plan.md", PLAN_DIR / "stage0_maps.md",
         HERE / "mc_data.py", HERE / "mc_models.py", HERE / "run_module_c.py",
         CODE / "ingest" / "crdc_courses.py"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def crosswalk_hash() -> tuple[str, int]:
    h = hashlib.sha256()
    with db.connect() as cn, cn.cursor() as cur:
        cur.execute("select hs_name, hs_city, hs_zip, ncessch, leaid, decision "
                    "from core.hs_crosswalk order by hs_name, hs_city, hs_zip")
        rows = cur.fetchall()
    for r in rows:
        h.update(("|".join("" if v is None else str(v) for v in r)
                  + "\n").encode("utf-8"))
    return h.hexdigest(), len(rows)


def main():
    out = PLAN_DIR / "registration_event.md"
    if out.exists() and "--force" not in sys.argv:
        raise SystemExit(f"{out} exists; registration is written once")
    xw, n = crosswalk_hash()
    today = date.today().isoformat()
    lines = [
        "# Typed event: registration of the Module C analysis plan (P0-D06)",
        "",
        "Status: ACCEPTED by the PI on " + today + ". The event follows the",
        "§0.4 template of `VER9_Architecture.md` and is ready for entry into",
        "`VER9_Log.md`. It was written before any registered estimation.",
        "",
        "```yaml",
        f"event_id: EVT-P0-D06-REGISTRATION-{today}",
        "event_type: DECISION",
        "object_type: DELIVERABLE",
        "object_id: P0-D06",
        "claim_id: null",
        "document: VER9_paper0_math_gateway.md",
        "source_path: Economics/Paper0/module_c/analysis_plan.md",
        'source_locator: "# Module C analysis plan"',
        f"source_sha256: {sha(FILES[0])}",
        "decision: ACCEPTED",
        "decision_owner: PI",
        f"effective_at: {today}",
        "text_exact: >",
        "  The Module C analysis plan, version 1.0, is frozen. Outcome",
        "  estimation proceeds under this text. Any later change is recorded",
        "  in Section 17 of the plan with date and reason, and results from a",
        "  deviating analysis are labeled exploratory.",
        "reason_exact: >",
        "  PI answers of " + today + ": all cohorts; CAP retained with a flag;",
        "  demographics block included; thresholds accepted; IRB coverage",
        "  confirmed by the PI; the two amendments of version 0.2 accepted.",
        "```",
        "",
        "## Frozen inputs",
        "",
        "| Object | SHA-256 |",
        "|---|---|",
    ]
    for f in FILES:
        lines.append(f"| `{f.relative_to(ROOT).as_posix()}` | `{sha(f)}` |")
    lines.append(f"| `core.hs_crosswalk` (GATEWAY, {n:,} rows, ordered "
                 f"name-city-zip, fields joined by a bar) | `{xw}` |")
    lines += ["",
              "A whole-file hash cannot sit inside the file it describes, so "
              "the plan's hash lives here.", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
