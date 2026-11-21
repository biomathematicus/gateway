"""Machine-readable audit of the declared cohort observation window.

Backs the boundary-sensitivity numbers stated in Section 2.2 of the
Paper 0 manuscript with a generated artifact instead of hand-entered
prose. Runs one read-only aggregate query against the institutional
SQL Server (bypassing the pickle cache deliberately) and writes
aggregate counts only: no student identifier or row leaves the query.

Output: code/figures/student_success/cohort_window_audit.json
"""
from __future__ import annotations

import json

import pyodbc

import config

MIN_CELL = 10       # a smaller count of students is withheld


def released(n: int):
    """the count, or None when it rests on fewer than MIN_CELL students"""
    return n if n == 0 or n >= MIN_CELL else None


SQL = """
set nocount on;
with C as (
  select IDENTIFIER, min(try_cast(FIRSTTERMCODE as float)) as ft
  from OIR where STUDENTTYPE = 'New'
  group by IDENTIFIER
  having min(try_cast(FIRSTTERMCODE as float))
         between {start} and {end}
),
T as (
  select C.IDENTIFIER as id,
    max(case when try_cast(O.CT_SUBJECT as int) > 4000
             and O.CURRENTTERM <= C.ft + {h} then 1 else 0 end) as k_i,
    max(case when try_cast(O.CT_SUBJECT as int) > 4000
             and O.CURRENTTERM <  C.ft + {h} then 1 else 0 end) as k_s,
    max(case when O.SHRTCKN_SUBJ_CODE = 'MAT'
             and O.CURRENTTERM <= C.ft + {h} then 1 else 0 end) as mat_i,
    max(case when O.SHRTCKN_SUBJ_CODE = 'MAT'
             and O.CURRENTTERM <  C.ft + {h} then 1 else 0 end) as mat_s,
    max(case when O.SHRTCKN_SUBJ_CODE = 'WRC'
             and O.CURRENTTERM <= C.ft + {h} then 1 else 0 end) as wrc_i,
    max(case when O.SHRTCKN_SUBJ_CODE = 'WRC'
             and O.CURRENTTERM <  C.ft + {h} then 1 else 0 end) as wrc_s,
    max(case when O.SHRTCKN_SUBJ_CODE = 'AIS'
             and O.CURRENTTERM <= C.ft + {h} then 1 else 0 end) as ais_i,
    max(case when O.SHRTCKN_SUBJ_CODE = 'AIS'
             and O.CURRENTTERM <  C.ft + {h} then 1 else 0 end) as ais_s,
    max(case when try_cast(O.CT_SUBJECT as int) = 4000
             and O.CURRENTTERM <= C.ft + {h} then 1 else 0 end) as ex4000,
    max(case when try_cast(O.CT_SUBJECT as int) >= 5000
             and O.CURRENTTERM <= C.ft + {h} then 1 else 0 end) as ge5000,
    max(case when O.CURRENTTERM < C.ft then 1 else 0 end) as pre_entry
  from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
  group by C.IDENTIFIER)
select count(*) as n, sum(k_i) as k_i, sum(k_s) as k_s,
  sum(case when mat_i=1 and k_i=0 then 1 else 0 end) as mat_a_i,
  sum(case when mat_i=1 and k_i=1 then 1 else 0 end) as mat_b_i,
  sum(case when mat_s=1 and k_s=0 then 1 else 0 end) as mat_a_s,
  sum(case when mat_s=1 and k_s=1 then 1 else 0 end) as mat_b_s,
  sum(case when wrc_i=1 and k_i=0 then 1 else 0 end) as wrc_a_i,
  sum(case when wrc_i=1 and k_i=1 then 1 else 0 end) as wrc_b_i,
  sum(case when wrc_s=1 and k_s=0 then 1 else 0 end) as wrc_a_s,
  sum(case when wrc_s=1 and k_s=1 then 1 else 0 end) as wrc_b_s,
  sum(case when ais_i=1 and k_i=0 then 1 else 0 end) as ais_a_i,
  sum(case when ais_i=1 and k_i=1 then 1 else 0 end) as ais_b_i,
  sum(case when ais_s=1 and k_s=0 then 1 else 0 end) as ais_a_s,
  sum(case when ais_s=1 and k_s=1 then 1 else 0 end) as ais_b_s,
  sum(ex4000) as n_exactly_4000,
  sum(ge5000) as n_5000_plus,
  sum(pre_entry) as n_pre_entry_records
from T
"""


def run() -> dict:
    sql = SQL.format(start=config.COHORT_ENTRY_START,
                     end=config.COHORT_ENTRY_END,
                     h=f"{config.COHORT_HORIZON_YEARS:g}")
    with pyodbc.connect(config.CONN_STRING, timeout=30) as cn:
        cn.timeout = 570
        cur = cn.cursor()
        row = cur.execute(sql).fetchone()
        v = {d[0]: int(x) for d, x in zip(cur.description, row)}

    def cells(prefix: str, k: str) -> dict:
        a, b = v[f"{prefix}_a{k}"], v[f"{prefix}_b{k}"]
        c = (v["n"] - v[f"k{k}"]) - a
        d = v[f"k{k}"] - b
        return {"a": a, "b": b, "c": c, "d": d,
                "odds_ratio": round((a / c) / (b / d), 3)}

    out = {
        "entry_window": [config.COHORT_ENTRY_START, config.COHORT_ENTRY_END],
        "horizon_years": config.COHORT_HORIZON_YEARS,
        "declared_boundary": "inclusive (CURRENTTERM <= ft + horizon)",
        "cohort_n": v["n"],
        "reached_above_4000": {
            "inclusive": {"n": v["k_i"],
                          "pct": round(100 * v["k_i"] / v["n"], 2)},
            "strict": {"n": v["k_s"],
                       "pct": round(100 * v["k_s"] / v["n"], 2)},
        },
        "odds_ratios": {
            s: {"inclusive": cells(s, "_i"), "strict": cells(s, "_s")}
            for s in ("mat", "wrc", "ais")
        },
        # a count of fewer than MIN_CELL students is withheld (null)
        "min_cell": MIN_CELL,
        "outcome_band": {
            "students_touching_exactly_4000": released(v["n_exactly_4000"]),
            "students_touching_5000_plus_in_window": released(
                v["n_5000_plus"]),
            "students_with_pre_entry_records": released(
                v["n_pre_entry_records"]),
        },
    }
    for s in out["odds_ratios"].values():
        for cell in s.values():
            assert min(cell[k] for k in "abcd") >= MIN_CELL
    path = config.IMG_DIR / "cohort_window_audit.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"  {path}")
    print(json.dumps(out["reached_above_4000"], indent=1))
    return out


if __name__ == "__main__":
    run()
