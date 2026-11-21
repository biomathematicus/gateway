"""
Report 008 — the 005 distance diagnostic, redone against REAL school coordinates.

Report 005 measured home-ZIP centroid -> high-school-ZIP centroid, and flagged
its own artefact: a large rural ZIP containing both home and school reads as
0 miles, while a dense San Antonio ZIP splits a 2-mile trip across two ZIPs. So
the 38% "same ZIP" spike was partly ZIP geometry, not proximity, and the measure
understated variation in rural areas while overstating it in urban ones.

The crosswalk (report 006) now resolves 88.1% of students to an NCES school, and
EDGE carries that school's LAT/LON. So the school end of the measurement can be
a POINT instead of a polygon centroid. The home end is still a ZIP centroid --
that cannot be improved without student addresses, which are not extracted.

WHAT THIS CHANGES AND WHAT IT DOES NOT
  It removes the school-side geometry artefact. It does NOT make the home end
  precise, so the residual measurement error is now one-sided rather than
  two-sided. Distances should shift UP slightly (a school is rarely at its ZIP's
  centroid) and the 0-mile spike should collapse, because a point and a centroid
  almost never coincide exactly.
"""

from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402
from gateway import paths  # noqa: E402
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402

setup()
GEO = paths.data_dir("geo")
OUT: dict = {}

SQL = """
SELECT  RIGHT('00000' + LTRIM(RTRIM(ZIPCODE)), 5)   AS home_zip,
        LTRIM(RTRIM(HIGHSCHOOLNAME))                AS hs_name,
        LTRIM(RTRIM(HIGHSCHOOLCITY))                AS hs_city,
        COUNT(DISTINCT IDENTIFIER)                  AS n_students
FROM dbo.OIR
WHERE HIGHSCHOOLSTATE='TX'
  AND ZIPCODE IS NOT NULL AND LTRIM(RTRIM(ZIPCODE)) <> ''
  AND HIGHSCHOOLNAME IS NOT NULL AND LTRIM(RTRIM(HIGHSCHOOLNAME)) <> ''
GROUP BY RIGHT('00000' + LTRIM(RTRIM(ZIPCODE)), 5),
         LTRIM(RTRIM(HIGHSCHOOLNAME)), LTRIM(RTRIM(HIGHSCHOOLCITY))
"""


def pairs() -> pd.DataFrame:
    import pyodbc
    cn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};"
                        "SERVER=localhost;DATABASE=UTSA;Trusted_Connection=yes;")
    try:
        return pd.read_sql(SQL, cn)
    finally:
        cn.close()


def zcta() -> pd.DataFrame:
    g = pd.read_csv(os.path.join(GEO, "Gaz_zcta_national.txt"), sep="\t",
                    dtype={"GEOID": str})
    g.columns = [c.strip() for c in g.columns]
    g["GEOID"] = g["GEOID"].str.strip().str.zfill(5)
    for a, b in (("INTPTLAT", "h_lat"), ("INTPTLONG", "h_lon")):
        g[b] = pd.to_numeric(g[a], errors="coerce")
    return g[["GEOID", "h_lat", "h_lon"]].dropna()


def schools() -> pd.DataFrame:
    with db.connect() as c:
        x = pd.read_sql("""
            SELECT x.hs_name, x.hs_city, x.ncessch, x.leaid, x.decision,
                   e.lat AS s_lat, e.lon AS s_lon
            FROM core.hs_crosswalk x
            JOIN raw_xwalk.edge_school e
              ON e.ncessch = x.ncessch AND e.cycle = '2017-18'
            WHERE x.decision = 'auto'
        """, c)
    return x.dropna(subset=["s_lat", "s_lon"])


def haversine(lat1, lon1, lat2, lon2):
    R = 3958.7613
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin((p2 - p1) / 2) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(a))


def wq(v, w, q):
    i = np.argsort(v)
    v, w = v[i], w[i]
    c = (np.cumsum(w) - 0.5 * w) / w.sum()
    return float(np.interp(q, c, v))


def fig_compare(d: pd.DataFrame) -> str:
    cap = 25.0
    w = d.n_students.values.astype(float)
    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    bins = np.arange(0, cap + 0.5, 0.5)
    ax.hist(np.clip(d.miles_pt.values, 0, cap), bins=bins, weights=w,
            color=SERIES[0], alpha=0.85, label="to school COORDINATES", zorder=3)
    ax.hist(np.clip(d.miles_zip.values, 0, cap), bins=bins, weights=w,
            histtype="step", linewidth=1.8, color=SERIES[1],
            label="to school ZIP centroid (report 005)", zorder=4)
    for m in (5.0, 10.0):
        ax.axvline(m, color=MUTED, lw=1.2, ls=(0, (3, 3)), zorder=2)
    ax.set_xlabel("miles from home ZIP centroid")
    ax.set_ylabel("students")
    ax.set_xlim(0, cap)
    ax.legend(loc="upper right")
    return finish(fig, ax, "008_coords_vs_zip",
                  "Using real school coordinates collapses the same-ZIP spike",
                  f"{OUT['n_students']:,} students on auto-matched schools. The "
                  f"0-mile spike was ZIP geometry: a point and a polygon centroid "
                  f"almost never coincide.")


def main() -> int:
    p = pairs()
    s = schools()
    z = zcta()
    d = (p.merge(s, on=["hs_name", "hs_city"], how="inner")
           .merge(z, left_on="home_zip", right_on="GEOID", how="inner"))
    # school ZIP centroid, for the like-for-like comparison
    with db.connect() as c:
        ez = pd.read_sql("SELECT ncessch, zip5 FROM raw_xwalk.edge_school "
                         "WHERE cycle='2017-18'", c)
    d = d.merge(ez, on="ncessch", how="left").merge(
        z.rename(columns={"GEOID": "zip5", "h_lat": "z_lat", "h_lon": "z_lon"}),
        on="zip5", how="left")
    d = d.dropna(subset=["s_lat", "z_lat"])

    d["miles_pt"] = haversine(d.h_lat, d.h_lon, d.s_lat, d.s_lon)
    d["miles_zip"] = haversine(d.h_lat, d.h_lon, d.z_lat, d.z_lon)
    w = d.n_students.values.astype(float)
    OUT["n_students"] = int(w.sum())
    OUT["n_pairs"] = int(len(d))

    for tag, col in (("pt", "miles_pt"), ("zip", "miles_zip")):
        v = d[col].values
        for q in (0.25, 0.50, 0.75, 0.90):
            OUT[f"{tag}_p{int(q*100)}"] = round(wq(v, w, q), 2)
        OUT[f"{tag}_pct_zero"] = round(100 * w[v < 0.25].sum() / w.sum(), 1)
        for m in (5, 10):
            OUT[f"{tag}_pct_within_{m}mi"] = round(100 * w[v <= m].sum() / w.sum(), 1)

    OUT["figures"] = [fig_compare(d)]
    # Internal file (pairs of ZIP code and school with their counts): it is
    # read by module_c/mc_data.py and is never released. The query returns
    # the pairs in no fixed order, so they are sorted here and two runs
    # write the same file.
    d[["home_zip", "hs_name", "hs_city", "ncessch", "leaid",
       "n_students", "miles_pt", "miles_zip"]].sort_values(
        ["home_zip", "hs_name", "hs_city", "ncessch"]).to_csv(
        os.path.join(FIGDIR, "008_coord_distances.csv"), index=False)
    with open(os.path.join(FIGDIR, "008_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(json.dumps(OUT, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
