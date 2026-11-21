"""
Load the Opportunity Atlas and NMDB context layers AT THEIR TRUE LEVELS.

This module exists to make a level-shift impossible rather than merely
discouraged. Neither source is a household measurement:

  OA    tract / county / commuting zone. A value is a PREDICTED OUTCOME for
        children of a given parental income percentile who grew up there. It is
        not a property of any individual student.
  NMDB  state / CBSA / census division ONLY, quarterly. A 5% sample of
        mortgages with no person identifiers, so it has no household link at
        all and no geography finer than a metro.

Both therefore land in `context_*` schemas whose names state the level, and the
tables carry an explicit `is_ecological` marker. The failure mode this program
keeps punishing is a contextual variable being read as an individual one; the
schema is the cheapest place to stop it.

TRACT VINTAGE: OA is built on **2010** tract definitions. CRDC-era crosswalks
from 2021-22 are 2020 tracts. Mixing them silently is a real error, so the
vintage is recorded on the table.
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

OA = paths.data_dir("OA")
NMDB = paths.data_dir("NMDB")


def load_oa_tract() -> None:
    """tract_outcomes_simple + tract_covariates, keyed on a 11-digit GEOID."""
    o = pd.read_csv(os.path.join(OA, "tract_outcomes_simple.csv"), dtype=str)
    c = pd.read_csv(os.path.join(OA, "tract_covariates.csv"), dtype=str)

    def geoid(d):
        return (d["state"].str.strip().str.zfill(2)
                + d["county"].str.strip().str.zfill(3)
                + d["tract"].str.strip().str.zfill(6))

    keep_o = ["kfr_pooled_pooled_p25", "kfr_pooled_pooled_p25_se",
              "jail_pooled_pooled_p25", "pooled_pooled_count",
              "kfr_black_pooled_p25", "kfr_hisp_pooled_p25",
              "kfr_white_pooled_p25"]
    keep_c = ["hhinc_mean2000", "med_hhinc2016", "poor_share2010",
              "frac_coll_plus2010", "popdensity2000", "singleparent_share2010",
              "job_density_2013", "traveltime15_2010"]

    oo = pd.DataFrame({"geoid_2010": geoid(o)})
    for k in keep_o:
        oo[k] = pd.to_numeric(o[k], errors="coerce") if k in o.columns else None
    cc = pd.DataFrame({"geoid_2010": geoid(c)})
    for k in keep_c:
        cc[k] = pd.to_numeric(c[k], errors="coerce") if k in c.columns else None

    d = oo.merge(cc, on="geoid_2010", how="outer")
    d = d[d.geoid_2010.str.fullmatch(r"\d{11}", na=False)]
    d = d.drop_duplicates(subset=["geoid_2010"])

    cols = list(d.columns)
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS context_tract")
        cur.execute("DROP TABLE IF EXISTS context_tract.oa_tract CASCADE")
        cur.execute(f"""
            CREATE TABLE context_tract.oa_tract (
                geoid_2010 text PRIMARY KEY,
                {", ".join(f'"{c}" double precision' for c in cols[1:])},
                tract_vintage text NOT NULL DEFAULT '2010',
                is_ecological boolean NOT NULL DEFAULT true
            )""")
        buf = io.StringIO()
        d.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            f"COPY context_tract.oa_tract ({','.join(chr(34)+c+chr(34) for c in cols)}) "
            f"FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("""
            COMMENT ON TABLE context_tract.oa_tract IS
            'Opportunity Atlas, TRACT level, 2010 tract definitions. ECOLOGICAL: '
            'each value is a predicted outcome for children of a given parental '
            'income percentile who grew up in this tract, NOT a property of any '
            'individual. Do not join to a student and read as that student''s '
            'outcome.'""")
    print(f"  context_tract.oa_tract: {len(d):,} tracts, {len(cols)-1} measures",
          flush=True)


def load_nmdb_context() -> None:
    """NMDB at its FINEST available geography -- state / metro / division."""
    p = os.path.join(NMDB, "nmdb-mortgage-performance-statistics-all-quarterly.csv")
    d = pd.read_csv(p, dtype=str, low_memory=False)
    d.columns = [c.strip().upper() for c in d.columns]
    out = pd.DataFrame({
        "geolevel": d["GEOLEVEL"].str.strip(),
        "geoid": d["GEOID"].str.strip(),
        "geoname": d["GEONAME"].str.strip(),
        "market": d["MARKET"].str.strip(),
        "period": d["PERIOD"].str.strip(),
        "year": pd.to_numeric(d["YEAR"], errors="coerce"),
        "quarter": pd.to_numeric(d["QUARTER"], errors="coerce"),
        "seriesid": d["SERIESID"].str.strip(),
        "suppressed": d["SUPPRESSED"].str.strip() == "1",
        "value1": pd.to_numeric(d["VALUE1"], errors="coerce"),
    })
    out = out[~out.suppressed]
    cols = list(out.columns)
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS context_metro")
        cur.execute("DROP TABLE IF EXISTS context_metro.nmdb_performance CASCADE")
        cur.execute("""
            CREATE TABLE context_metro.nmdb_performance (
                geolevel text, geoid text, geoname text, market text,
                period text, year int, quarter int, seriesid text,
                suppressed boolean, value1 double precision,
                is_ecological boolean NOT NULL DEFAULT true)""")
        buf = io.StringIO()
        out.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            f"COPY context_metro.nmdb_performance ({','.join(cols)}) "
            f"FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("CREATE INDEX ON context_metro.nmdb_performance (geolevel, geoid)")
        cur.execute("CREATE INDEX ON context_metro.nmdb_performance (seriesid, year)")
        cur.execute("""
            COMMENT ON TABLE context_metro.nmdb_performance IS
            'NMDB mortgage performance. FINEST geography is STATE / METRO(CBSA) / '
            'census division -- there is NO tract, district or household level. '
            'A 5% sample of mortgages with no person identifiers, so no household '
            'link to a student exists or can be constructed. Purely contextual.'""")
    print(f"  context_metro.nmdb_performance: {len(out):,} rows, "
          f"levels {sorted(out.geolevel.unique())}", flush=True)


def main() -> int:
    print("loading OA tract layer ...", flush=True)
    load_oa_tract()
    print("loading NMDB metro/state layer ...", flush=True)
    load_nmdb_context()
    with db.connect() as c:
        print()
        print(pd.read_sql("""
            SELECT 'context_tract.oa_tract' AS tbl, count(*) n FROM context_tract.oa_tract
            UNION ALL SELECT 'context_metro.nmdb_performance', count(*) FROM context_metro.nmdb_performance
        """, c).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
