"""Aggregate facts about the reference cohort that the manuscript cites.

Reads the institutional source in place and writes aggregates only:
entry-term counts of the reference cohort (first term between Fall 2014
and Fall 2015), and senior-level progression and mathematics exposure by
CAP status. Cells under 10 students are never written; totals are.
"""
import json
import sys
from pathlib import Path

import pyodbc

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from student_success import config as _ss  # noqa: E402

OUT = HERE.parent / "figures" / "module_c" / "reference_cohort_notes.json"
_FT = "min(try_cast(FIRSTTERMCODE as float))"
SQL = f"""
with C as (select IDENTIFIER, {_FT} ft, max(CAP) cap from OIR
           where STUDENTTYPE = 'New' group by IDENTIFIER
           having {_FT} between 2014.66 and 2015.66),
X as (select C.IDENTIFIER, C.ft, C.cap,
             max(case when try_cast(O.CT_SUBJECT as int) > 4000
                       and O.CURRENTTERM <= C.ft + 4 then 1 else 0 end) r4k,
             max(case when O.SHRTCKN_SUBJ_CODE = 'MAT'
                       and O.CURRENTTERM <= C.ft + 4 then 1 else 0 end) mat
      from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
      group by C.IDENTIFIER, C.ft, C.cap)
select round(ft, 2), cap, mat, r4k, count(*) from X
group by round(ft, 2), cap, mat, r4k
"""


def main():
    with pyodbc.connect(_ss.CONN_STRING, timeout=20) as cn:
        rows = cn.cursor().execute(SQL).fetchall()
    term = {}
    cap = {0: [0, 0], 1: [0, 0]}                 # [students, reached]
    t22 = {(m, r): 0 for m in (0, 1) for r in (0, 1)}   # CAP not set
    for ft, c, mat, r4k, n in rows:
        term[f"{ft:.2f}"] = term.get(f"{ft:.2f}", 0) + n
        cap[int(c or 0)][0] += n
        cap[int(c or 0)][1] += n * r4k
        if not c:
            t22[(mat, r4k)] += n
    a, b = t22[(1, 0)], t22[(1, 1)]              # MAT: not reached, reached
    c_, d = t22[(0, 0)], t22[(0, 1)]
    out = {
        "cohort_n": sum(term.values()),
        "entry_terms": {"fall_2014": term.get("2014.66", 0),
                        "spring_2015": term.get("2015.00", 0),
                        "summer_2015": term.get("2015.33", 0),
                        "fall_2015": term.get("2015.66", 0)},
        "cap_set": {"students": cap[1][0], "reached_senior_level": cap[1][1],
                    "share": cap[1][1] / cap[1][0]},
        "cap_not_set": {"students": cap[0][0],
                        "reached_senior_level": cap[0][1],
                        "share": cap[0][1] / cap[0][0],
                        "mat_odds_ratio_not_reaching": (a / b) / (c_ / d)},
    }
    assert all(v >= 10 for v in out["entry_terms"].values())
    assert min(a, b, c_, d) >= 10
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
