"""
Load the NCES EDGE public-school geocode file into GATEWAY.

This is the crosswalk TARGET for UTSA's free-text high school names, and it is
the right target because `NCESSCH` is byte-identical to CRDC's `COMBOKEY`
(LEAID(7) || SCHID(5)). Matching a UTSA high school to an EDGE row therefore
yields the district (LEAID) EXACTLY, with no distance inference — which is the
whole point of abandoning the ZIP-proximity approach.

It also carries LAT/LON, so the "is the home ZIP the childhood address?"
diagnostic can be recomputed against real school coordinates instead of the
school's ZIP centroid, removing the ZIP-size artefact that inflated the
same-ZIP spike in rural areas.
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

CYCLES = {
    "2017-18": ("edge_1718", "EDGE_GEOCODE_PUBLICSCH_1718"),
    "2021-22": ("edge_2122", "EDGE_GEOCODE_PUBLICSCH_2122"),
}

COLS = ["cycle", "ncessch", "leaid", "schid", "name", "street", "city",
        "state", "zip5", "cnty", "nmcnty", "lat", "lon", "cbsa", "nmcbsa"]


def read_cycle(cycle: str) -> pd.DataFrame:
    sub, stem = CYCLES[cycle]
    path = os.path.join(GEO, sub, stem, stem + ".xlsx")
    d = pd.read_excel(path, dtype=str)
    d.columns = [c.strip().upper() for c in d.columns]
    out = pd.DataFrame({
        "cycle": cycle,
        "ncessch": d["NCESSCH"].str.strip().str.zfill(12),
        "name": d["NAME"].str.strip(),
        "street": d.get("STREET", pd.Series(dtype=str)).str.strip(),
        "city": d["CITY"].str.strip(),
        "state": d["STATE"].str.strip(),
        "zip5": d["ZIP"].astype(str).str.strip().str[:5].str.zfill(5),
        "cnty": d.get("CNTY", pd.Series(dtype=str)).str.strip(),
        "nmcnty": d.get("NMCNTY", pd.Series(dtype=str)).str.strip(),
        "lat": pd.to_numeric(d["LAT"], errors="coerce"),
        "lon": pd.to_numeric(d["LON"], errors="coerce"),
        "cbsa": d.get("CBSA", pd.Series(dtype=str)).str.strip(),
        "nmcbsa": d.get("NMCBSA", pd.Series(dtype=str)).str.strip(),
    })
    out["leaid"] = out["ncessch"].str[:7]
    out["schid"] = out["ncessch"].str[7:]
    return out[COLS]


def main() -> int:
    frames = [read_cycle(c) for c in CYCLES]
    df = pd.concat(frames, ignore_index=True)
    print(f"EDGE rows: {len(df):,}  cycles: {sorted(df.cycle.unique())}", flush=True)

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw_xwalk.edge_school CASCADE")
        cur.execute("""
            CREATE TABLE raw_xwalk.edge_school (
                cycle   text NOT NULL,
                ncessch text NOT NULL,
                leaid   text NOT NULL,
                schid   text,
                name    text,
                street  text,
                city    text,
                state   text,
                zip5    text,
                cnty    text,
                nmcnty  text,
                lat     double precision,
                lon     double precision,
                cbsa    text,
                nmcbsa  text,
                PRIMARY KEY (cycle, ncessch)
            )""")
        buf = io.StringIO()
        df.drop_duplicates(subset=["cycle", "ncessch"]).to_csv(
            buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            "COPY raw_xwalk.edge_school (" + ",".join(COLS) +
            ") FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("CREATE INDEX ON raw_xwalk.edge_school (state, city)")
        cur.execute("CREATE INDEX ON raw_xwalk.edge_school (state, zip5)")
        cur.execute("CREATE INDEX ON raw_xwalk.edge_school (leaid)")
        # trigram index on the normalised name is what makes the fuzzy match fast
        cur.execute("""
            CREATE INDEX edge_name_trgm ON raw_xwalk.edge_school
            USING gin (upper(name) gin_trgm_ops)""")

    for cycle in CYCLES:
        sub, stem = CYCLES[cycle]
        p = os.path.join(GEO, sub, stem, stem + ".xlsx")
        blob = open(p, "rb").read()
        db.exec_sql(f"""
            INSERT INTO core.source_file (dataset, vintage, rel_path, sha256,
                                          bytes, source_url, n_rows)
            VALUES ('edge_geocode', '{cycle}',
                    'geo/{sub}/{stem}/{stem}.xlsx',
                    '{hashlib.sha256(blob).hexdigest()}', {len(blob)},
                    'https://nces.ed.gov/programs/edge/data/',
                    {int((df.cycle == cycle).sum())})
            ON CONFLICT (dataset, vintage, rel_path) DO UPDATE
               SET sha256=EXCLUDED.sha256, loaded_at=now()""")

    print(db.read_sql("""
        SELECT cycle, count(*) schools,
               count(*) FILTER (WHERE state='TX') tx_schools,
               count(DISTINCT leaid) leas
        FROM raw_xwalk.edge_school GROUP BY cycle ORDER BY cycle
    """).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
