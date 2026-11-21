"""
Link UTSA students to GATEWAY district/neighbourhood context — LOCALLY.

GOVERNANCE (PI instruction, 2026-08-08)
    "You can write code to call records and process locally, but you cannot
     ingest individual student records."

So the shape of this module is not incidental, it IS the constraint:

  * student rows are pulled from SQL Server into memory, joined to GATEWAY
    lookup tables (district poverty, neighbourhood context, the school
    crosswalk — all PUBLIC data), and reduced to CELLS here;
  * ONLY aggregated cells are written back to GATEWAY, and only cells with at
    least `MIN_CELL` students, so no cell can identify a person;
  * the per-student frame never leaves this process except as the local pickle
    cache that `db.cached_query` already maintains, which is the same
    local-processing pattern the rest of this package uses.

An earlier version of this work built `mart.utsa_student_context`, a 92,769-row
per-student table in GATEWAY. That violated the instruction above and has been
dropped. This module replaces it.

OUTCOME
    `OIR2` is the table the pipeline document calls `DATA`. It carries the
    pre-college mathematics credit fields the programme is actually about:
        MAT1073 (Algebra), MAT1093 (Precalculus),
        MAT1214 (Calculus I), MAT1224 (Calculus II)
    each as _AP_GRDE / _DUAL_GRDE / _CLEP_GRDE.
    `any_precollege_math_credit` = any of the twelve is non-null.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

import config
import db

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from gateway import db as gdb  # noqa: E402

MIN_CELL = 10          # no aggregate row may rest on fewer students than this

STUDENT_SQL = """
SELECT  IDENTIFIER,
        MIN(FIRSTTERMCODE)                              AS first_term,
        MIN(STUDENTTYPE)                                AS student_type,
        MIN(ETHNICITY)                                  AS ethnicity,
        MIN(PELLSTATUS)                                 AS pell,
        MIN(FIRSTGENERATIONSTATUS)                      AS first_gen,
        MIN(RIGHT('00000'+LTRIM(RTRIM(ZIPCODE)),5))     AS home_zip,
        MIN(LTRIM(RTRIM(HIGHSCHOOLNAME)))               AS hs_name,
        MIN(LTRIM(RTRIM(HIGHSCHOOLCITY)))               AS hs_city,
        MIN(LTRIM(RTRIM(HIGHSCHOOLSTATE)))              AS hs_state,
        MAX(CASE WHEN MAT1073_AP_GRDE   IS NOT NULL OR MAT1073_DUAL_GRDE IS NOT NULL
                   OR MAT1073_CLEP_GRDE IS NOT NULL THEN 1 ELSE 0 END) AS cr_1073,
        MAX(CASE WHEN MAT1093_AP_GRDE   IS NOT NULL OR MAT1093_DUAL_GRDE IS NOT NULL
                   OR MAT1093_CLEP_GRDE IS NOT NULL THEN 1 ELSE 0 END) AS cr_1093,
        MAX(CASE WHEN MAT1214_AP_GRDE   IS NOT NULL OR MAT1214_DUAL_GRDE IS NOT NULL
                   OR MAT1214_CLEP_GRDE IS NOT NULL THEN 1 ELSE 0 END) AS cr_1214,
        MAX(CASE WHEN MAT1224_AP_GRDE   IS NOT NULL OR MAT1224_DUAL_GRDE IS NOT NULL
                   OR MAT1224_CLEP_GRDE IS NOT NULL THEN 1 ELSE 0 END) AS cr_1224,
        MAX(HIGHEST_SATACT_MATH)                        AS satact_math
FROM OIR2
GROUP BY IDENTIFIER
"""


def students(refresh: bool = False) -> pd.DataFrame:
    """Per-student frame. Stays in memory / the local pickle cache."""
    d = db.cached_query("gateway-students-OIR2", STUDENT_SQL, refresh=refresh)
    for c in ("cr_1073", "cr_1093", "cr_1214", "cr_1224"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0).astype(int)
    d["any_math_credit"] = d[["cr_1073", "cr_1093",
                              "cr_1214", "cr_1224"]].max(axis=1)
    ft = pd.to_numeric(d.first_term, errors="coerce")
    d["univ_entry_year"] = np.floor(ft)
    d["hs_entry_year"] = d.univ_entry_year - 4
    d["hb5_default"] = d.hs_entry_year >= 2014
    d["new_entrant"] = d.student_type.astype(str).str.strip().str.lower().eq("new")
    d["satact_math"] = pd.to_numeric(d.satact_math, errors="coerce")
    return d


def context() -> dict[str, pd.DataFrame]:
    """GATEWAY lookups. All PUBLIC data — no student records involved."""
    with gdb.connect() as c:
        xw = pd.read_sql("SELECT hs_name, hs_city, leaid FROM core.hs_crosswalk "
                         "WHERE decision LIKE 'auto%%'", c)
        sa = pd.read_sql("""
            SELECT leaid, vintage,
                   CASE WHEN pop_5_17>0 THEN pov_5_17/pop_5_17 END AS pov_rate
            FROM stg.saipe_sd WHERE pop_5_17 > 0""", c)
        oa = pd.read_sql("SELECT zcta5, kfr_p25, poor_share2010 "
                         "FROM context_zcta.oa_zcta", c)
    return {"xw": xw, "saipe": sa, "oa": oa}


def joined(refresh: bool = False) -> pd.DataFrame:
    """Per-student + context, IN MEMORY ONLY. Never persisted."""
    d = students(refresh=refresh)
    ctx = context()
    d = d.merge(ctx["xw"], on=["hs_name", "hs_city"], how="left")
    d["vintage"] = d.hs_entry_year.clip(1995, 2024)
    d = d.merge(ctx["saipe"], on=["leaid", "vintage"], how="left")
    d = d.merge(ctx["oa"], left_on="home_zip", right_on="zcta5", how="left")
    return d


def publish(cells: pd.DataFrame, table: str, keys: list[str]) -> None:
    """Write an AGGREGATE to GATEWAY, refusing any cell below MIN_CELL."""
    small = int((cells.n_students < MIN_CELL).sum())
    cells = cells[cells.n_students >= MIN_CELL].copy()
    import io
    with gdb.connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS mart")
        cur.execute(f"DROP TABLE IF EXISTS mart.{table} CASCADE")
        cols = ", ".join(
            f'"{c}" ' + ("text" if cells[c].dtype == object else "double precision")
            for c in cells.columns)
        cur.execute(f"CREATE TABLE mart.{table} ({cols})")
        buf = io.StringIO()
        cells.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            f"COPY mart.{table} FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute(f"""
            COMMENT ON TABLE mart.{table} IS
            'AGGREGATE ONLY. Built by code/student_success/gateway_link.py from
             UTSA SQL Server records processed locally. No individual student
             record is stored here; every cell has at least {MIN_CELL} students.
             Keys: {", ".join(keys)}.'""")
    print(f"  mart.{table}: {len(cells):,} cells published "
          f"({small} suppressed for n < {MIN_CELL})", flush=True)
