"""
Build the ZIP(ZCTA) -> tract and county -> CBSA crosswalks.

SOURCE CHOICE -- why NOT HUD.
  The plan named HUD's quarterly USPS ZIP crosswalk. Two facts moved it:
    * HUD's file endpoint returns HTTP 202 (it is behind an API token), so it is
      not reproducible from this tree without registering a key;
    * the Census ZCTA-to-Tract relationship file is a direct, hashable download,
      it is built on **2010 tract definitions** -- which is exactly the vintage
      the Opportunity Atlas uses -- and it carries actual POPULATION overlap
      (`POPPT`, `ZPOPPCT`) rather than HUD's address counts.
  For allocating a student's home ZIP across tracts, population overlap is the
  quantity we actually want, so the Census file is not a fallback here; it is
  the better instrument.

TWO CROSSWALKS ARE BUILT, deliberately, because they serve different analyses:

  fractional   every (zcta, tract) pair with its weight `zpop_pct`/100.
               Correct in expectation for AGGREGATE/ecological estimates. A
               student becomes 0.42 of tract A and 0.31 of tract B, which breaks
               any model that assumes one student = one row.

  deterministic  one row per ZCTA: the single highest-population tract, with
               `match_quality` = that tract's share. Keeps one student = one
               row so student-level models work, at the cost of
               misclassification -- and `match_quality` makes the cost visible
               per ZIP (0.95 is near-certain, 0.34 is a coin flip).

County -> CBSA is derived from the NCES EDGE school file, which carries both
`CNTY` and `CBSA` per school, so it needs no additional download.
"""

from __future__ import annotations

import hashlib
import io
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402
from gateway import paths  # noqa: E402

GEO = paths.data_dir("geo")
REL = os.path.join(GEO, "zcta_tract_rel_10.txt")


def build_zcta_tract() -> pd.DataFrame:
    d = pd.read_csv(REL, dtype=str)
    d.columns = [c.strip().upper() for c in d.columns]
    out = pd.DataFrame({
        "zcta5": d["ZCTA5"].str.strip().str.zfill(5),
        "geoid_2010": (d["STATE"].str.strip().str.zfill(2)
                       + d["COUNTY"].str.strip().str.zfill(3)
                       + d["TRACT"].str.strip().str.zfill(6)),
        "state_fips": d["STATE"].str.strip().str.zfill(2),
        "county_fips": (d["STATE"].str.strip().str.zfill(2)
                        + d["COUNTY"].str.strip().str.zfill(3)),
        "pop_overlap": pd.to_numeric(d["POPPT"], errors="coerce"),
        "zpop_pct": pd.to_numeric(d["ZPOPPCT"], errors="coerce"),
    })
    out = out[out.geoid_2010.str.fullmatch(r"\d{11}", na=False)]
    out["weight"] = out["zpop_pct"] / 100.0
    return out


def main() -> int:
    d = build_zcta_tract()
    print(f"fractional pairs: {len(d):,}  ZCTAs: {d.zcta5.nunique():,}  "
          f"tracts: {d.geoid_2010.nunique():,}", flush=True)

    # deterministic: highest-population tract per ZCTA
    det = (d.sort_values(["zcta5", "pop_overlap"], ascending=[True, False])
             .drop_duplicates(subset=["zcta5"], keep="first")
             .rename(columns={"weight": "match_quality"})
             [["zcta5", "geoid_2010", "state_fips", "county_fips",
               "pop_overlap", "match_quality"]])
    print(f"deterministic: {len(det):,} ZCTAs; "
          f"median match_quality {det.match_quality.median():.3f}; "
          f"share >=0.80: {100*(det.match_quality>=0.80).mean():.1f}%; "
          f"share <0.50: {100*(det.match_quality<0.50).mean():.1f}%", flush=True)

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw_xwalk")
        cur.execute("DROP TABLE IF EXISTS raw_xwalk.zcta_tract_frac CASCADE")
        cur.execute("""
            CREATE TABLE raw_xwalk.zcta_tract_frac (
                zcta5 text, geoid_2010 text, state_fips text, county_fips text,
                pop_overlap double precision, zpop_pct double precision,
                weight double precision,
                tract_vintage text NOT NULL DEFAULT '2010')""")
        buf = io.StringIO()
        d.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            "COPY raw_xwalk.zcta_tract_frac (zcta5,geoid_2010,state_fips,"
            "county_fips,pop_overlap,zpop_pct,weight) "
            "FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("CREATE INDEX ON raw_xwalk.zcta_tract_frac (zcta5)")
        cur.execute("CREATE INDEX ON raw_xwalk.zcta_tract_frac (geoid_2010)")

        cur.execute("DROP TABLE IF EXISTS raw_xwalk.zcta_tract_best CASCADE")
        cur.execute("""
            CREATE TABLE raw_xwalk.zcta_tract_best (
                zcta5 text PRIMARY KEY, geoid_2010 text, state_fips text,
                county_fips text, pop_overlap double precision,
                match_quality double precision,
                tract_vintage text NOT NULL DEFAULT '2010')""")
        buf = io.StringIO()
        det.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            "COPY raw_xwalk.zcta_tract_best (zcta5,geoid_2010,state_fips,"
            "county_fips,pop_overlap,match_quality) "
            "FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("""
            COMMENT ON TABLE raw_xwalk.zcta_tract_best IS
            'ONE tract per ZCTA (highest population overlap). Use for
             STUDENT-LEVEL work, where one student must stay one row.
             `match_quality` is that tract''s share of the ZCTA population --
             0.95 is near-certain, 0.34 is a coin flip. For aggregate estimates
             prefer raw_xwalk.zcta_tract_frac and its fractional weights.'""")

        # county -> CBSA from EDGE, which already carries both
        cur.execute("DROP TABLE IF EXISTS raw_xwalk.county_cbsa CASCADE")
        cur.execute("""
            CREATE TABLE raw_xwalk.county_cbsa AS
            SELECT DISTINCT ON (cnty)
                   cnty AS county_fips, cbsa, nmcbsa AS cbsa_name
            FROM raw_xwalk.edge_school
            WHERE cycle='2017-18' AND cnty IS NOT NULL
              AND cbsa IS NOT NULL AND cbsa <> 'N'
            ORDER BY cnty, cbsa""")
        cur.execute("ALTER TABLE raw_xwalk.county_cbsa ADD PRIMARY KEY (county_fips)")

        blob = open(REL, "rb").read()
        cur.execute("""
            INSERT INTO core.source_file (dataset, vintage, rel_path, sha256,
                                          bytes, source_url, n_rows)
            VALUES ('zcta_tract_rel','2010','geo/zcta_tract_rel_10.txt',%s,%s,
                    'https://www2.census.gov/geo/docs/maps-data/data/rel/zcta_tract_rel_10.txt',%s)
            ON CONFLICT (dataset, vintage, rel_path) DO UPDATE
               SET sha256=EXCLUDED.sha256, loaded_at=now()""",
            (hashlib.sha256(blob).hexdigest(), len(blob), len(d)))

    with db.connect() as c:
        print()
        print(pd.read_sql("""
            SELECT 'zcta_tract_frac' t, count(*) n FROM raw_xwalk.zcta_tract_frac
            UNION ALL SELECT 'zcta_tract_best', count(*) FROM raw_xwalk.zcta_tract_best
            UNION ALL SELECT 'county_cbsa', count(*) FROM raw_xwalk.county_cbsa
        """, c).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
