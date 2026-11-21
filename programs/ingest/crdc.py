"""
Ingest CRDC school-level counts into GATEWAY, sentinel-safe, and aggregate to
district.

THE SENTINEL PROBLEM, which is the whole reason this module exists:

  CRDC stores reserve codes IN the count columns --
    -3  skip logic / processing failure     -4  missing optional data
    -5  action plan / quick plan            -6  force certified
    -9  not applicable / skipped           -11/-12 suppressed for privacy
    -13 missing DIND skip logic
  A naive `int(col)` then `SUM()` therefore ADDS -9s into an enrollment total.
  Here every count is split into a value (NULL when the raw was a reserve code)
  and a `*_rc` smallint holding which code it was, so suppression stays
  reportable and a total can never absorb a sentinel.

  CRDC's own `TOT_*` columns were computed by treating reserve codes as ZERO,
  and where every disaggregated value was a code the total was set to the most
  negative code present. So the TOT_ columns are themselves sentinel-bearing and
  are ALSO passed through the same splitter.

AGGREGATION HONESTY:
  Summing schools to a district when some schools are suppressed biases the
  district total DOWNWARD. Every district row therefore carries n_schools,
  n_reported and n_suppressed so a user can see the coverage behind the number
  instead of inheriting a silently-partial sum.
"""

from __future__ import annotations

import hashlib
import io
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402
from gateway import paths  # noqa: E402

DATA = paths.data_dir("CRDC")

CYCLES = {
    "2017-18": os.path.join(
        DATA, "2017-18-crdc-data",
        "2017-18-crdc-data-corrected-publication 2",
        "2017-18 Public-Use Files", "Data", "SCH", "CRDC", "CSV"),
    "2021-22": os.path.join(DATA, "2021-22-crdc-data", "SCH"),
}

RESERVE_CODES = {-3, -4, -5, -6, -9, -11, -12, -13, -2}


def split_reserve(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """(value, reserve_code). Value is NaN wherever the raw was a reserve code."""
    v = pd.to_numeric(s, errors="coerce")
    is_rc = v.isin(list(RESERVE_CODES)) | (v < 0)
    rc = v.where(is_rc)
    val = v.mask(is_rc)
    return val, rc


def read_school_file(cycle: str, fname: str, keep: list[str]) -> pd.DataFrame:
    path = os.path.join(CYCLES[cycle], fname)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    usecols = ["LEA_STATE", "LEAID", "SCHID", "COMBOKEY", "SCH_NAME", "JJ"] + keep
    df = pd.read_csv(path, dtype=str, usecols=lambda c: c in usecols,
                     encoding="latin-1", low_memory=False)
    df["cycle"] = cycle
    df["leaid"] = df["LEAID"].astype(str).str.strip().str.zfill(7)
    df["combokey"] = df["COMBOKEY"].astype(str).str.strip()
    return df


def sha_of(path: str) -> tuple[str, int]:
    blob = open(path, "rb").read()
    return hashlib.sha256(blob).hexdigest(), len(blob)


def build() -> pd.DataFrame:
    frames = []
    for cycle in CYCLES:
        alg = read_school_file(cycle, "Algebra II.csv",
                               ["TOT_MATHENR_ALG2_M", "TOT_MATHENR_ALG2_F"])
        enr = read_school_file(cycle, "Enrollment.csv",
                               ["TOT_ENR_M", "TOT_ENR_F"])
        a_m, a_m_rc = split_reserve(alg["TOT_MATHENR_ALG2_M"])
        a_f, a_f_rc = split_reserve(alg["TOT_MATHENR_ALG2_F"])
        alg = alg.assign(alg2_m=a_m, alg2_f=a_f,
                         alg2_m_rc=a_m_rc, alg2_f_rc=a_f_rc)
        alg["alg2_tot"] = alg[["alg2_m", "alg2_f"]].sum(axis=1, min_count=1)

        e_m, _ = split_reserve(enr["TOT_ENR_M"])
        e_f, _ = split_reserve(enr["TOT_ENR_F"])
        enr = enr.assign(enr_m=e_m, enr_f=e_f)
        enr["enr_tot"] = enr[["enr_m", "enr_f"]].sum(axis=1, min_count=1)

        m = alg[["cycle", "leaid", "combokey", "SCH_NAME", "LEA_STATE", "JJ",
                 "alg2_tot", "alg2_m_rc", "alg2_f_rc"]].merge(
            enr[["combokey", "enr_tot"]], on="combokey", how="left")
        frames.append(m)
        print(f"  {cycle}: {len(m):,} schools; "
              f"alg2 reported {m.alg2_tot.notna().sum():,}; "
              f"suppressed/NA {m.alg2_tot.isna().sum():,}", flush=True)
    return pd.concat(frames, ignore_index=True)


def write_school(df: pd.DataFrame) -> None:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS stg.crdc_school CASCADE")
        cur.execute("""
            CREATE TABLE stg.crdc_school (
                cycle      text NOT NULL,
                leaid      text NOT NULL,
                combokey   text NOT NULL,
                sch_name   text,
                state_pc   text,
                jj         text,
                alg2_tot   double precision,
                alg2_m_rc  smallint,
                alg2_f_rc  smallint,
                enr_tot    double precision,
                PRIMARY KEY (cycle, combokey)
            )""")
        d = df.drop_duplicates(subset=["cycle", "combokey"]).copy()
        # reserve codes arrive as float (-9.0) because the column carries NaN;
        # COPY into smallint needs an integer literal, so use a nullable Int
        for c in ("alg2_m_rc", "alg2_f_rc"):
            d[c] = d[c].astype("Int16")
        out = d[["cycle", "leaid", "combokey", "SCH_NAME", "LEA_STATE", "JJ",
                 "alg2_tot", "alg2_m_rc", "alg2_f_rc", "enr_tot"]]
        buf = io.StringIO()
        out.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            "COPY stg.crdc_school FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("CREATE INDEX ON stg.crdc_school (leaid)")
        print(f"  stg.crdc_school: {len(out):,} rows", flush=True)


def build_district() -> None:
    db.exec_sql("""
        DROP TABLE IF EXISTS core.crdc_district CASCADE;
        CREATE TABLE core.crdc_district AS
        SELECT cycle,
               leaid,
               min(state_pc)                                    AS state_pc,
               count(*)                                         AS n_schools,
               count(alg2_tot)                                  AS n_alg2_reported,
               count(*) - count(alg2_tot)                        AS n_alg2_missing,
               sum(alg2_tot)                                    AS alg2_enrollees,
               sum(enr_tot)                                     AS enr_total,
               count(enr_tot)                                   AS n_enr_reported
        FROM stg.crdc_school
        GROUP BY cycle, leaid;
        ALTER TABLE core.crdc_district ADD PRIMARY KEY (cycle, leaid);
        CREATE INDEX ON core.crdc_district (leaid);
    """)


def register_sources() -> None:
    with db.connect() as conn, conn.cursor() as cur:
        for cycle, d in CYCLES.items():
            for f in ("Algebra II.csv", "Enrollment.csv"):
                p = os.path.join(d, f)
                if not os.path.isfile(p):
                    continue
                sha, n = sha_of(p)
                cur.execute("""
                    INSERT INTO core.source_file
                        (dataset, vintage, rel_path, sha256, bytes, source_url)
                    VALUES ('crdc', %s, %s, %s, %s, %s)
                    ON CONFLICT (dataset, vintage, rel_path) DO UPDATE
                       SET sha256=EXCLUDED.sha256, bytes=EXCLUDED.bytes, loaded_at=now()
                """, (cycle, os.path.relpath(p, os.path.dirname(DATA)).replace("\\", "/"),
                      sha, n, "https://civilrightsdata.ed.gov/data"))


def main() -> int:
    print("reading CRDC school files ...", flush=True)
    df = build()
    write_school(df)
    build_district()
    register_sources()
    q = db.read_sql("""
        SELECT cycle, count(*) AS districts,
               sum(n_schools) AS schools,
               round(sum(alg2_enrollees)::numeric) AS alg2_enrollees,
               round(100.0*sum(n_alg2_missing)/sum(n_schools),1) AS pct_schools_alg2_missing
        FROM core.crdc_district GROUP BY cycle ORDER BY cycle
    """)
    print(q.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
