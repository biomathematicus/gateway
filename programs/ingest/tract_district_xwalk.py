"""
Build the census-tract -> school-district crosswalk from NCES EDGE GRF17.

SOURCE. NCES EDGE School District Geographic Relationship Files, 2017
release (TIGER 2017; per NCES the school-district boundaries in TIGER
2017 represent school year 2015-16), file grf17_lea_tract inside
GRF17.zip:
one row per (LEAID, TRACT) spatial intersection with the land area of
the overlap in square miles. TRACT is an 11-digit 2010 GEOID, which is
exactly the Opportunity Atlas vintage. The boundaries predate the
CRDC 2017-18 cycle used by the district exhibits by two school years;
GRF18 (TIGER 2018, SY 2017-18) would match the cycle exactly and is
the recorded upgrade path. Direct, hashable
download: https://nces.ed.gov/programs/edge/data/GRF17.zip

WEIGHTS. `share` is the tract's land-area share allocated to the
district: LANDAREA(tract, district) / sum of LANDAREA over all district
rows of that tract. Land-area allocation is the convention the program
already uses for district-to-tract allocated statistics. One caveat is
recorded on the table: elementary and secondary districts overlay the
same territory, so in dual-district regions the denominator counts the
tract roughly twice; a district's own territory has a consistent
regime, so weighted district aggregates are essentially unaffected.

DIRECTION OF USE. Built for aggregating tract-level context UP to
districts (e.g. Opportunity Atlas surfaces), weighting by
share x tract population. It is never used to assign a student to a
tract or a district.
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
ZIP = os.path.join(GEO, "GRF17.zip")
XLSX = os.path.join(GEO, "grf17_lea_tract.xlsx")


def build() -> pd.DataFrame:
    d = pd.read_excel(XLSX, dtype=str)
    d.columns = [c.strip().upper() for c in d.columns]
    out = pd.DataFrame({
        "leaid": d["LEAID"].str.strip().str.zfill(7),
        "lea_name": d["NAME_LEA17"].str.strip(),
        "geoid_2010": d["TRACT"].str.strip().str.zfill(11),
        "landarea_sqmi": pd.to_numeric(d["LANDAREA"], errors="coerce"),
    })
    out = out[out.geoid_2010.str.fullmatch(r"\d{11}", na=False)]
    out = out[out.landarea_sqmi.notna() & (out.landarea_sqmi >= 0)]
    tract_total = out.groupby("geoid_2010").landarea_sqmi.transform("sum")
    out["share"] = out.landarea_sqmi / tract_total.where(tract_total > 0)
    return out.dropna(subset=["share"])


def main() -> int:
    d = build()
    per_tract = d.groupby("geoid_2010").share.sum()
    print(f"pairs: {len(d):,}  tracts: {d.geoid_2010.nunique():,}  "
          f"LEAs: {d.leaid.nunique():,}", flush=True)
    print(f"per-tract share sums: min {per_tract.min():.3f} "
          f"max {per_tract.max():.3f} (1.000 expected)", flush=True)
    bexar = d[d.geoid_2010.str.startswith("48029")]
    print(f"Bexar County tracts: {bexar.geoid_2010.nunique():,} across "
          f"{bexar.leaid.nunique()} districts", flush=True)

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw_xwalk.lea_tract_frac CASCADE")
        cur.execute("""
            CREATE TABLE raw_xwalk.lea_tract_frac (
                leaid text, lea_name text, geoid_2010 text,
                landarea_sqmi double precision, share double precision,
                tract_vintage text NOT NULL DEFAULT '2010',
                grf_vintage text NOT NULL DEFAULT '2017 (SY 2015-16)')""")
        buf = io.StringIO()
        d.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            "COPY raw_xwalk.lea_tract_frac (leaid,lea_name,geoid_2010,"
            "landarea_sqmi,share) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
            buf)
        cur.execute("CREATE INDEX ON raw_xwalk.lea_tract_frac (leaid)")
        cur.execute("CREATE INDEX ON raw_xwalk.lea_tract_frac (geoid_2010)")
        cur.execute("""
            COMMENT ON TABLE raw_xwalk.lea_tract_frac IS
            'Census tract (2010) -> school district land-area shares from
             NCES EDGE GRF17 (TIGER 2017; boundaries represent school
             year 2015-16 per NCES). Built for aggregating
             tract-level context UP to districts, weighting by
             share x tract population; never used to assign a student to
             a tract or district. Elementary and secondary districts
             overlay the same territory, so per-tract shares are
             normalized over all district rows of the tract.'""")

        blob = open(ZIP, "rb").read()
        cur.execute("""
            INSERT INTO core.source_file (dataset, vintage, rel_path, sha256,
                                          bytes, source_url, n_rows)
            VALUES ('edge_grf_lea_tract','2017 (SY 2015-16)','geo/GRF17.zip',%s,%s,
                    'https://nces.ed.gov/programs/edge/data/GRF17.zip',%s)
            ON CONFLICT (dataset, vintage, rel_path) DO UPDATE
               SET sha256=EXCLUDED.sha256, loaded_at=now()""",
            (hashlib.sha256(blob).hexdigest(), len(blob), len(d)))

    with db.connect() as c:
        print()
        print(pd.read_sql(
            "SELECT count(*) AS pairs, count(DISTINCT leaid) AS leas, "
            "count(DISTINCT geoid_2010) AS tracts "
            "FROM raw_xwalk.lea_tract_frac", c).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
