"""
Report 005 — How good a proxy is "first known ZIP" for the childhood home?

The Opportunity Atlas is about WHERE A CHILD GREW UP. `dbo.OIR.ZIPCODE` is
documented as "first known zip code of the student", which is probably the
application address and therefore probably the parental home — but that is an
assumption, and the OA linkage rests entirely on it.

The PI's test, implemented here: compare the student's home ZIP to the ZIP of
the high school they graduated from. If the home ZIP really is the childhood
address, the two should usually be close, because students mostly attend a high
school near home. The threshold is NOT prescribed — the distribution is plotted
and the cut is chosen from it.

WHAT THIS CAN AND CANNOT SHOW
  A SHORT distance is consistent with the home ZIP being the childhood address.
  A LONG distance is ambiguous by construction: the student may have moved after
  high school (proxy fails), OR may have commuted to a magnet/charter/private
  school far from home (proxy fine, school is just distant). This check
  therefore bounds the problem; it does not diagnose individual cases.

PRIVACY
  Only an aggregate ZIP-pair contingency is pulled -- (home ZIP, high school ZIP,
  count of students). No student rows leave the server.
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
from gateway import paths  # noqa: E402
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402

setup()
GEO = paths.data_dir("geo")
OUT: dict = {}

SQL = """
SELECT  RIGHT('00000' + LTRIM(RTRIM(ZIPCODE)), 5)        AS home_zip,
        RIGHT('00000' + LTRIM(RTRIM(HIGHSCHOOLZIP)), 5)  AS hs_zip,
        COUNT(DISTINCT IDENTIFIER)                       AS n_students
FROM dbo.OIR
WHERE ZIPCODE IS NOT NULL AND LTRIM(RTRIM(ZIPCODE)) <> ''
  AND HIGHSCHOOLZIP IS NOT NULL AND LTRIM(RTRIM(HIGHSCHOOLZIP)) <> ''
GROUP BY RIGHT('00000' + LTRIM(RTRIM(ZIPCODE)), 5),
         RIGHT('00000' + LTRIM(RTRIM(HIGHSCHOOLZIP)), 5)
"""


def pairs() -> pd.DataFrame:
    import pyodbc
    cn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};"
                        "SERVER=localhost;DATABASE=UTSA;Trusted_Connection=yes;")
    try:
        return pd.read_sql(SQL, cn)
    finally:
        cn.close()


def centroids() -> pd.DataFrame:
    """2010 ZCTA gazetteer — contemporaneous with the 2009-2019 UTSA window."""
    p = os.path.join(GEO, "Gaz_zcta_national.txt")
    g = pd.read_csv(p, sep="\t", dtype={"GEOID": str})
    g.columns = [c.strip() for c in g.columns]
    g["GEOID"] = g["GEOID"].str.strip().str.zfill(5)
    g = g.rename(columns={"INTPTLAT": "lat", "INTPTLONG": "lon", "POP10": "pop10"})
    for c in ("lat", "lon"):
        g[c] = pd.to_numeric(g[c], errors="coerce")
    return g[["GEOID", "lat", "lon", "pop10"]].dropna(subset=["lat", "lon"])


def haversine(lat1, lon1, lat2, lon2):
    R = 3958.7613  # miles
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def wq(v: np.ndarray, w: np.ndarray, q: float) -> float:
    """Weighted quantile."""
    i = np.argsort(v)
    v, w = v[i], w[i]
    c = np.cumsum(w) - 0.5 * w
    c /= w.sum()
    return float(np.interp(q, c, v))


def fig_hist(d: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    cap = 100.0
    x = np.clip(d.miles.values, 0, cap)
    ax.hist(x, bins=np.arange(0, cap + 2.5, 2.5), weights=d.n_students.values,
            color=SERIES[0], edgecolor=None, zorder=3)
    for q, lbl in ((0.5, "median"), (0.9, "p90")):
        v = OUT[f"miles_p{int(q*100)}"]
        ax.axvline(v, color=SERIES[1], lw=1.6, ls=(0, (4, 3)), zorder=4)
        ax.text(v + 1.2, ax.get_ylim()[1] * 0.92, f"{lbl} {v:.1f} mi",
                color=SERIES[1], fontsize=9, fontweight="bold")
    ax.set_xlabel("miles, home ZIP centroid → high-school ZIP centroid")
    ax.set_ylabel("students")
    ax.set_xlim(0, cap)
    return finish(fig, ax, "005_zip_hs_distance",
                  "Most students' first-known ZIP sits close to their high school",
                  f"{OUT['n_students_matched']:,} students with both ZIPs geocoded. "
                  f"Distances clipped at {cap:.0f} miles for display; "
                  f"{OUT['pct_over_100mi']}% exceed it.")


def fig_cdf(d: pd.DataFrame) -> str:
    v = d.miles.values
    w = d.n_students.values.astype(float)
    i = np.argsort(v)
    v, w = v[i], w[i]
    cum = np.cumsum(w) / w.sum() * 100
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    ax.plot(v, cum, color=SERIES[0], lw=2, zorder=3)
    # staggered label offsets: at 25 and 50 miles the curve is nearly flat, so
    # equal offsets put the two annotations on top of each other
    for m, (dx, dy) in zip((10, 25, 50), ((1.6, -20), (3.0, -34), (60, -12))):
        pct = float(np.interp(m, v, cum))
        OUT[f"pct_within_{m}mi"] = round(pct, 1)
        ax.plot([m, m], [0, pct], color=MUTED, lw=1, ls=(0, (3, 3)), zorder=2)
        ax.plot([0, m], [pct, pct], color=MUTED, lw=1, ls=(0, (3, 3)), zorder=2)
        ax.annotate(f"{pct:.1f}% within {m} mi", (m, pct), (m * dx, pct + dy),
                    fontsize=9, color=INK2,
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.9))
    # the shelf the threshold decision rests on
    ax.axvspan(25, 100, color=SERIES[1], alpha=0.07, lw=0, zorder=1)
    ax.text(46, 42, "shelf:\nlocal population\nexhausted", ha="center",
            fontsize=8.5, color=SERIES[1], fontweight="bold")
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("miles, home ZIP → high-school ZIP (symlog)")
    ax.set_ylabel("cumulative % of students")
    ax.set_ylim(0, 101)
    ax.set_xlim(0, 3000)
    return finish(fig, ax, "005_zip_hs_cdf",
                  "Where to put the threshold: the distribution decides",
                  "Cumulative share of students by home-to-high-school distance. "
                  "The long tail is students who moved after high school OR who "
                  "commuted to a distant school — this check cannot separate them.")


def fig_district_scale(d: pd.DataFrame) -> str:
    """The scale that actually matters: San Antonio has 16+ ISDs, so a few miles
    already crosses a district boundary. A threshold chosen from the SHAPE of the
    national distance distribution (which suggested ~25 mi) is far too coarse for
    district assignment — 25 miles spans most of Bexar County."""
    cap = 25.0
    x = np.clip(d.miles.values, 0, cap)
    w = d.n_students.values.astype(float)
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    ax.hist(x, bins=np.arange(0, cap + 0.5, 0.5), weights=w,
            color=SERIES[0], edgecolor=None, zorder=3)
    tot = w.sum()
    for m, col in ((5.0, SERIES[1]), (10.0, MUTED)):
        pct = 100 * w[d.miles.values <= m].sum() / tot
        OUT[f"pct_within_{int(m)}mi_exact"] = round(pct, 1)
        ax.axvline(m, color=col, lw=1.8, ls=(0, (4, 3)), zorder=4)
        ax.text(m + 0.3, ax.get_ylim()[1] * (0.90 if m == 5 else 0.78),
                f"{m:.0f} mi — {pct:.1f}%", color=col, fontsize=9,
                fontweight="bold")
    ax.set_xlabel("miles, home ZIP centroid → high-school ZIP centroid")
    ax.set_ylabel("students")
    ax.set_xlim(0, cap)
    return finish(fig, ax, "005_district_scale",
                  "At district scale, the mass is inside 5 miles",
                  "0.5-mile bins. San Antonio has 16+ independent school "
                  "districts, so beyond roughly 5 miles a student's home ZIP "
                  "generally falls in a different district from their school.")


def far_mode(d: pd.DataFrame) -> None:
    """What IS the distant mode? Not Houston commuters."""
    far = d[d.miles > 100].copy()
    far["h3"] = far.home_zip.str[:3]
    OUT["n_students_over_100mi"] = int(far.n_students.sum())
    by = far.groupby("h3").n_students.sum().sort_values(ascending=False)
    OUT["far_mode_top_home_prefix"] = str(by.index[0])
    OUT["far_mode_top_home_share"] = round(100 * by.iloc[0] / far.n_students.sum(), 1)
    hou = far[far.hs_zip.str[:3].isin(["770", "773", "774", "775", "772"])]
    OUT["far_mode_houston_hs_students"] = int(hou.n_students.sum())
    OUT["far_mode_houston_hs_share"] = round(
        100 * hou.n_students.sum() / far.n_students.sum(), 1)


def main() -> int:
    p = pairs()
    OUT["n_zip_pairs"] = int(len(p))
    OUT["n_students_pairs"] = int(p.n_students.sum())

    g = centroids()
    d = (p.merge(g.add_prefix("h_"), left_on="home_zip", right_on="h_GEOID", how="left")
           .merge(g.add_prefix("s_"), left_on="hs_zip", right_on="s_GEOID", how="left"))
    ok = d.h_lat.notna() & d.s_lat.notna()
    OUT["n_students_ungeocoded"] = int(d.loc[~ok, "n_students"].sum())
    d = d[ok].copy()
    d["miles"] = haversine(d.h_lat, d.h_lon, d.s_lat, d.s_lon)
    OUT["n_students_matched"] = int(d.n_students.sum())

    v, w = d.miles.values, d.n_students.values.astype(float)
    for q in (0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99):
        OUT[f"miles_p{int(q*100)}"] = round(wq(v, w, q), 2)
    OUT["pct_same_zip"] = round(100 * w[v < 0.001].sum() / w.sum(), 1)
    OUT["pct_over_100mi"] = round(100 * w[v > 100].sum() / w.sum(), 1)
    OUT["mean_miles"] = round(float((v * w).sum() / w.sum()), 2)

    far_mode(d)
    OUT["figures"] = [fig_district_scale(d), fig_hist(d), fig_cdf(d)]

    d[["home_zip", "hs_zip", "n_students", "miles"]].sort_values(
        "n_students", ascending=False).to_csv(
        os.path.join(FIGDIR, "005_zip_hs_pairs.csv"), index=False)
    with open(os.path.join(FIGDIR, "005_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(json.dumps(OUT, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
