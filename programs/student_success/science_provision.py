"""
Report 026 — Science provision at the sending high schools (appendix exhibit).

PI decision 2026-08-10: the science direction is approved as an APPENDIX exhibit
for Paper0, not a new analysis arm. Scope is therefore deliberately narrow.

WHAT THIS CAN AND CANNOT BE. `OIR2`'s pre-college credit columns are
MATHEMATICS ONLY (MAT1073/1093/1214/1224 x AP/DUAL/CLEP), so no student-level
science-credit outcome exists and none is constructed. What `HIGHSCHOOLS`
(= the CRDC 2017-18 high-school universe; provenance proven in report 021 §1)
does carry is per-school enrolment in biology, chemistry, physics, geometry,
calculus and AP science. So this is a PROVISION-LANDSCAPE analysis:

  1. What share of schools enrol nobody in each science subject?
  2. Is the "provision desert" a small-school phenomenon, as it was for AP
     mathematics (report 021 §3.5), or does poverty dominate for science?
  3. Are the no-physics schools the same schools as the no-AP-maths schools?
  4. Student-weighted: what share of UTSA entrants came from a school that
     enrolled nobody in physics / chemistry / AP science?

The 021 vintage caveat applies as it did there, softened by report 022's
stability finding (rank persistence of provision, Spearman 0.91 over a decade)
with the same residual: stability was proven for Algebra II, not per subject.

Processed LOCALLY; only aggregate cells (n >= 10) are published.
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

import config
import db
import gateway_link as gl

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402
from gateway import db as gdb  # noqa: E402

setup()
OUT: dict = {}

SUBJECTS = [("bio", "Biology"), ("chem", "Chemistry"), ("phy", "Physics"),
            ("geo", "Geometry"), ("cal", "Calculus"),
            ("apscience", "AP science"), ("apmath", "AP mathematics")]


def schools() -> pd.DataFrame:
    h = db.cached_query("highschools", "SELECT * FROM HIGHSCHOOLS")
    h["ncessch"] = h.leaid.astype(str) + h.schid.astype(str)
    for c, _ in SUBJECTS:
        h[c] = pd.to_numeric(h[c], errors="coerce")
    h["total"] = pd.to_numeric(h.total, errors="coerce")
    h = h[h.total > 0].copy()
    return h


def linked(h: pd.DataFrame) -> pd.DataFrame:
    """UTSA students attached to their school's provision row."""
    stu = gl.students()[["IDENTIFIER", "hs_name", "hs_city"]]
    with gdb.connect() as g:
        xw = pd.read_sql("SELECT hs_name, hs_city, ncessch, leaid "
                         "FROM core.hs_crosswalk WHERE ncessch IS NOT NULL", g)
        # pov_rate computed from counts; label-string trap does not apply here
        pov = pd.read_sql(
            "SELECT leaid, AVG(100.0*pov_5_17/NULLIF(pop_5_17,0)) AS pov_rate "
            "FROM stg.saipe_sd WHERE vintage BETWEEN 2010 AND 2018 "
            "GROUP BY leaid", g)
    # HIGHSCHOOLS also carries `leaid`; drop it so the crosswalk's wins
    return (stu.merge(xw, on=["hs_name", "hs_city"], how="inner")
               .merge(h.drop(columns=["leaid"]), on="ncessch", how="inner")
               .merge(pov, on="leaid", how="left"))


def landscape(h: pd.DataFrame, utsa_ids: set) -> pd.DataFrame:
    """Share of schools enrolling NOBODY in each subject, national and UTSA-sending."""
    rows = []
    hu = h[h.ncessch.isin(utsa_ids)]
    for c, lab in SUBJECTS:
        rows.append({
            "subject": lab,
            "pct_zero_national": round(100 * float((h[c] == 0).mean()), 1),
            "pct_zero_utsa_schools": round(100 * float((hu[c] == 0).mean()), 1),
            "n_national": int(len(h)), "n_utsa_schools": int(len(hu))})
    return pd.DataFrame(rows)


def size_poverty(d: pd.DataFrame) -> pd.DataFrame:
    """Within the UTSA-sending schools: zero-provision by size band, + correlations."""
    s = d.drop_duplicates("ncessch").copy()
    s["size_band"] = pd.cut(s.total, [0, 400, 1000, 2000, 100000],
                            labels=["under 400", "400-999", "1000-1999", "2000+"])
    rows = []
    for c, lab in SUBJECTS:
        r = {"subject": lab}
        for band, grp in s.groupby("size_band", observed=True):
            r[f"pct_zero_{band}"] = round(100 * float((grp[c] == 0).mean()), 1)
        ok = s.dropna(subset=["pov_rate"])
        r["corr_rate_poverty"] = round(
            float((ok[c] / ok.total).corr(ok.pov_rate)), 3)
        r["corr_rate_logsize"] = round(
            float((s[c] / s.total).corr(np.log(s.total))), 3)
        rows.append(r)
    return pd.DataFrame(rows)


def student_exposure(d: pd.DataFrame) -> pd.DataFrame:
    """Share of UTSA entrants whose own school enrolled nobody in each subject."""
    rows = []
    for c, lab in SUBJECTS:
        rows.append({"subject": lab,
                     "n_students": int(len(d)),
                     "pct_students_zero_school":
                         round(100 * float((d[c] == 0).mean()), 2)})
    return pd.DataFrame(rows)


def overlap(h: pd.DataFrame, utsa_ids: set) -> dict:
    """Are the no-physics schools the no-AP-maths schools?"""
    s = h[h.ncessch.isin(utsa_ids)]
    no_phy, no_apm = (s.phy == 0), (s.apmath == 0)
    both = float((no_phy & no_apm).mean())
    pe = float(no_phy.mean() * no_apm.mean()
               + (1 - no_phy.mean()) * (1 - no_apm.mean()))
    agree = float((no_phy == no_apm).mean())
    return {"pct_no_physics": round(100 * float(no_phy.mean()), 1),
            "pct_no_apmath": round(100 * float(no_apm.mean()), 1),
            "pct_both": round(100 * both, 1),
            "kappa_no_phy_no_apmath":
                round((agree - pe) / (1 - pe), 3) if pe < 1 else None,
            "pct_no_phy_given_no_apmath":
                round(100 * float(no_phy[no_apm].mean()), 1) if no_apm.any() else None}


def fig(land: pd.DataFrame, expo: pd.DataFrame) -> str:
    order = ["Biology", "Geometry", "Chemistry", "AP mathematics",
             "Physics", "AP science", "Calculus"]
    l = land.set_index("subject").reindex(order)
    e = expo.set_index("subject").reindex(order)
    x = np.arange(len(order))
    w = 0.27
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.bar(x - w, l.pct_zero_national, w * 0.9, color=MUTED,
           label="all CRDC schools", zorder=3)
    ax.bar(x, l.pct_zero_utsa_schools, w * 0.9, color=SERIES[0],
           label="UTSA-sending schools", zorder=3)
    ax.bar(x + w, e.pct_students_zero_school, w * 0.9, color=SERIES[1],
           label="UTSA entrants (student-weighted)", zorder=3)
    for i, sub in enumerate(order):
        for dx, v, col in [(-w, l.pct_zero_national[sub], INK2),
                           (0, l.pct_zero_utsa_schools[sub], SERIES[0]),
                           (w, e.pct_students_zero_school[sub], SERIES[1])]:
            if np.isfinite(v):
                ax.text(i + dx, v + 0.8, f"{v:.0f}", ha="center", fontsize=8,
                        color=col, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace(" ", "\n") for s in order], fontsize=8.5)
    ax.set_ylabel("% with ZERO enrolment in subject")
    ax.legend(loc="upper left", fontsize=8.5)
    return finish(fig, ax, "026_science_provision",
                  "At the sending schools, core science is universal; advanced coursework is not",
                  "Share of high schools enrolling nobody in each subject, CRDC "
                  "2017-18 (`HIGHSCHOOLS`; provenance in report 021). "
                  "Student-weighted bars attach each UTSA entrant to their own "
                  "school via core.hs_crosswalk. Enrolment, not offering: a "
                  "course offered but not taken counts as zero. Vintage caveat "
                  "as in report 021, softened by report 022.")


def main() -> int:
    h = schools()
    OUT["n_schools_national"] = int(len(h))

    d = linked(h)
    OUT["n_students"] = int(len(d))
    utsa_ids = set(d.ncessch)
    OUT["n_utsa_schools"] = len(utsa_ids)

    land = landscape(h, utsa_ids)
    sp = size_poverty(d)
    expo = student_exposure(d)
    OUT["landscape"] = land.to_dict("records")
    OUT["size_poverty"] = sp.to_dict("records")
    OUT["exposure"] = expo.to_dict("records")
    OUT["overlap_no_phy_no_apmath"] = overlap(h, utsa_ids)

    OUT["figures"] = [fig(land, expo)]
    pub = expo.rename(columns={"n_students": "n_students"})
    gl.publish(pub, "utsa_science_exposure", ["subject"])
    land.to_csv(os.path.join(FIGDIR, "026_landscape.csv"), index=False)
    sp.to_csv(os.path.join(FIGDIR, "026_size_poverty.csv"), index=False)
    expo.to_csv(os.path.join(FIGDIR, "026_exposure.csv"), index=False)
    with open(os.path.join(FIGDIR, "026_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)

    print(land.to_string(index=False))
    print()
    print(sp.to_string(index=False))
    print()
    print(expo.to_string(index=False))
    print()
    print("overlap:", json.dumps(OUT["overlap_no_phy_no_apmath"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
