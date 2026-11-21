"""
Ingest Algebra II enrollment across ALL FIVE CRDC cycles into a district panel.

Five cycles ship in FOUR package shapes and TWO column vocabularies. Nothing
about this is guessable from one cycle, so the spec is written out explicitly:

  cycle    package                       Algebra II total columns
  2011-12  per-topic .xlsx, deep paths   M_TOT_7_ALGEBRA2_ENR / F_TOT_7_ALGEBRA2_ENR
  2013-14  per-topic .xlsx               TOT_MATHENR_ALG2_M / _F   (inside "Other Math")
  2015-16  ONE wide .csv (1,836 cols)    TOT_MATHENR_ALG2_M / _F
  2017-18  per-topic .csv                TOT_MATHENR_ALG2_M / _F
  2021-22  per-topic .csv                TOT_MATHENR_ALG2_M / _F

The 2011-12 vocabulary is the odd one out and is the reason a single reader
kept returning empty columns for that cycle.

SENTINELS: every cycle stores reserve codes inside the count columns
(-3,-4,-5,-6,-9,-11,-12,-13). They become NULL and never enter a sum. The
district row carries n_schools / n_alg2_reported / n_alg2_missing so a
partially-suppressed district is visible rather than silently small.

FRAME: all five cycles are universe collections; the CRDC has covered every
public district since 2011-12, and the cycles hold between 95,147 and 97,985
schools. `core.crdc_district_panel.is_universe` records the frame of each
cycle, so that a sampled cycle (2009-10 and earlier) could not enter
unnoticed. An earlier version of this loader flagged 2011-12 and 2013-14 as
samples; that flag was wrong and is corrected here.
"""

from __future__ import annotations

import glob
import hashlib
import io
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402
from gateway import paths  # noqa: E402

DATA = paths.data_dir("CRDC")

RESERVE = {-2, -3, -4, -5, -6, -9, -11, -12, -13}

# (glob for the Algebra II source, male col, female col, is_universe)
SPEC = {
    "2011-12": ("2011-12-crdc-data/**/*13-4 - Students enrolled in Algebra II.xlsx",
                "M_TOT_7_ALGEBRA2_ENR", "F_TOT_7_ALGEBRA2_ENR", True),
    "2013-14": ("2013-14-crdc-data/**/05-3 Other Math Courses and Classes.xlsx",
                "TOT_MATHENR_ALG2_M", "TOT_MATHENR_ALG2_F", True),
    "2015-16": ("2015-16-crdc-data/**/CRDC 2015-16 School Data.csv",
                "TOT_MATHENR_ALG2_M", "TOT_MATHENR_ALG2_F", True),
    "2017-18": ("2017-18-crdc-data/**/SCH/CRDC/CSV/Algebra II.csv",
                "TOT_MATHENR_ALG2_M", "TOT_MATHENR_ALG2_F", True),
    "2021-22": ("2021-22-crdc-data/SCH/Algebra II.csv",
                "TOT_MATHENR_ALG2_M", "TOT_MATHENR_ALG2_F", True),
}

KEYS = ["LEA_STATE", "LEAID", "SCHID", "SCH_NAME", "COMBOKEY", "JJ"]


def split_reserve(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    v = pd.to_numeric(s, errors="coerce")
    is_rc = v.isin(list(RESERVE)) | (v < 0)
    return v.mask(is_rc), v.where(is_rc)


def find(pattern: str) -> str | None:
    hits = glob.glob(os.path.join(DATA, pattern), recursive=True)
    hits = [h for h in hits if "~$" not in h]
    return hits[0] if hits else None


def read_cycle(cycle: str) -> pd.DataFrame | None:
    pat, mcol, fcol, universe = SPEC[cycle]
    path = find(pat)
    if path is None:
        print(f"  ! {cycle}: no file matching {pat}", flush=True)
        return None
    want = set(KEYS) | {mcol, fcol}
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path, dtype=str, encoding="latin-1", low_memory=False,
                         usecols=lambda c: c in want)
    else:
        df = pd.read_excel(path, dtype=str)
        df = df[[c for c in df.columns if c in want]]
    if mcol not in df.columns or fcol not in df.columns:
        print(f"  ! {cycle}: missing {mcol}/{fcol} in {os.path.basename(path)}",
              flush=True)
        return None
    m, m_rc = split_reserve(df[mcol])
    f, f_rc = split_reserve(df[fcol])
    leaid = df["LEAID"].astype(str).str.strip().str.zfill(7)
    # COMBOKEY is NOT trustworthy as stored. The 2015-16 wide CSV ships it with
    # leading zeros stripped (lengths 7-12), which collapses 66,986 of 96,360
    # distinct schools onto duplicate keys and silently destroyed two thirds of
    # that cycle. NCES defines it as LEAID(7) || SCHID(5), so build it.
    schid = df["SCHID"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out = pd.DataFrame({
        "cycle": cycle,
        "leaid": leaid,
        "combokey": leaid + schid.str.zfill(5),
        "state_pc": df.get("LEA_STATE", pd.Series(dtype=str)),
        "alg2_tot": pd.concat([m, f], axis=1).sum(axis=1, min_count=1),
        "alg2_m_rc": m_rc.astype("Int16"),
        "alg2_f_rc": f_rc.astype("Int16"),
        "is_universe": universe,
        "src_file": os.path.relpath(path, DATA).replace("\\", "/"),
    })
    print(f"  {cycle}: {len(out):,} schools, "
          f"alg2 reported {out.alg2_tot.notna().sum():,}, "
          f"universe={universe}  [{os.path.basename(path)}]", flush=True)
    return out


def main() -> int:
    frames = [x for x in (read_cycle(c) for c in SPEC) if x is not None]
    if not frames:
        raise SystemExit("no CRDC cycle could be read")
    df = pd.concat(frames, ignore_index=True)
    df = df[df.leaid.str.fullmatch(r"\d{7}", na=False)]

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS stg.crdc_alg2_panel CASCADE")
        cur.execute("""
            CREATE TABLE stg.crdc_alg2_panel (
                cycle       text NOT NULL,
                leaid       text NOT NULL,
                combokey    text NOT NULL,
                state_pc    text,
                alg2_tot    double precision,
                alg2_m_rc   smallint,
                alg2_f_rc   smallint,
                is_universe boolean,
                src_file    text,
                PRIMARY KEY (cycle, combokey)
            )""")
        d = df.drop_duplicates(subset=["cycle", "combokey"])
        buf = io.StringIO()
        d.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            "COPY stg.crdc_alg2_panel FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("CREATE INDEX ON stg.crdc_alg2_panel (leaid)")
        print(f"  stg.crdc_alg2_panel: {len(d):,} rows", flush=True)

    db.exec_sql("""
        DROP TABLE IF EXISTS core.crdc_district_panel CASCADE;
        CREATE TABLE core.crdc_district_panel AS
        SELECT cycle, leaid,
               min(state_pc)                 AS state_pc,
               bool_and(is_universe)         AS is_universe,
               count(*)                      AS n_schools,
               count(alg2_tot)               AS n_alg2_reported,
               count(*) - count(alg2_tot)    AS n_alg2_missing,
               sum(alg2_tot)                 AS alg2_enrollees
        FROM stg.crdc_alg2_panel
        GROUP BY cycle, leaid;
        ALTER TABLE core.crdc_district_panel ADD PRIMARY KEY (cycle, leaid);
        CREATE INDEX ON core.crdc_district_panel (leaid);
    """)

    # register provenance
    with db.connect() as conn, conn.cursor() as cur:
        for cycle in SPEC:
            p = find(SPEC[cycle][0])
            if not p:
                continue
            blob = open(p, "rb").read()
            cur.execute("""
                INSERT INTO core.source_file (dataset, vintage, rel_path, sha256,
                                              bytes, source_url)
                VALUES ('crdc_alg2', %s, %s, %s, %s,
                        'https://civilrightsdata.ed.gov/assets/ocr/docs/')
                ON CONFLICT (dataset, vintage, rel_path) DO UPDATE
                   SET sha256=EXCLUDED.sha256, loaded_at=now()""",
                (cycle, os.path.relpath(p, DATA).replace("\\", "/"),
                 hashlib.sha256(blob).hexdigest(), len(blob)))

    print()
    print(db.read_sql("""
        SELECT cycle, is_universe, count(*) districts,
               sum(n_schools) schools,
               round(sum(alg2_enrollees)::numeric) alg2_enrollees,
               round(100.0*sum(n_alg2_missing)/sum(n_schools),1) pct_missing
        FROM core.crdc_district_panel
        GROUP BY cycle, is_universe ORDER BY cycle
    """).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
