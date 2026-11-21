"""
Report 014 — Does the credit INSTRUMENT (AP vs dual) predict UTSA math outcomes?

Report 013 showed AP and dual enrolment are distributed oppositely by district
poverty. The obvious next question is whether they are equivalent preparation.

THE DESIGN PROBLEM, and why a naive comparison is worthless.
  A student with AP Calculus credit SKIPS Calculus I, so their first UTSA maths
  course is a HIGHER one. Comparing "grade in first maths course" across
  instruments therefore compares different courses, and AP students would look
  worse simply for starting further along.

  So the comparison is made WITHIN COURSE: among students who sat the SAME UTSA
  course, does prior AP credit predict a different outcome from prior dual
  credit? Only the first attempt at each course counts, so repeats do not
  double-count a struggling student.

  Even within course the groups differ on preparation (report 013: SAT/ACT maths
  586 vs 523 across poverty quintiles), so results are also reported stratified
  by SAT/ACT mathematics band. Any residual gap is still not causal — instrument
  is chosen by district and family, not assigned.

Processed LOCALLY; only aggregate cells (n >= 10) are published.
"""

from __future__ import annotations

import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config
import db
import gateway_link as gl
from courses import canon

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402

setup()
OUT: dict = {}
DFW = {"D", "D+", "D-", "F", "W", "IN", "NC", "NR"}

COURSE_SQL = """
SELECT IDENTIFIER, SHRTCKN_CRSE_TITLE AS title, CURRENTTERMCODE AS term,
       SHRTCKG_GRDE_CODE_FINAL AS grade
FROM OIR2
WHERE SHRTCKN_SUBJ_CODE = 'MAT'
  AND SHRTCKG_GRDE_CODE_FINAL IS NOT NULL
"""

CREDIT_SQL = """
SELECT IDENTIFIER,
  MAX(CASE WHEN MAT1073_AP_GRDE IS NOT NULL OR MAT1093_AP_GRDE IS NOT NULL
            OR MAT1214_AP_GRDE IS NOT NULL OR MAT1224_AP_GRDE IS NOT NULL
           THEN 1 ELSE 0 END) AS ap,
  MAX(CASE WHEN MAT1073_DUAL_GRDE IS NOT NULL OR MAT1093_DUAL_GRDE IS NOT NULL
            OR MAT1214_DUAL_GRDE IS NOT NULL OR MAT1224_DUAL_GRDE IS NOT NULL
           THEN 1 ELSE 0 END) AS dual,
  MAX(HIGHEST_SATACT_MATH) AS satact_math
FROM OIR2 GROUP BY IDENTIFIER
"""


#: `SHRTCKN_CRSE_TITLE` is truncated free text whose spelling drifts, so one
#: course appears under several titles. Canonicalisation lives in `courses.py`;
#: grouping on the raw title splits courses into fragments. See that module.
norm_title = canon


def frame() -> pd.DataFrame:
    c = db.cached_query("mat-course-attempts", COURSE_SQL)
    cr = db.cached_query("gateway-credit-type-sat", CREDIT_SQL)
    for k in ("ap", "dual"):
        cr[k] = pd.to_numeric(cr[k], errors="coerce").fillna(0).astype(int)
    cr["satact_math"] = pd.to_numeric(cr.satact_math, errors="coerce")

    c["course"] = c.title.map(norm_title)
    c["term_n"] = pd.to_numeric(c.term, errors="coerce")
    c = c.sort_values(["IDENTIFIER", "course", "term_n"])
    first = c.drop_duplicates(subset=["IDENTIFIER", "course"], keep="first")
    first = first.assign(
        dfw=first.grade.astype(str).str.strip().str.upper().isin(DFW).astype(int))

    d = first.merge(cr, on="IDENTIFIER", how="left")
    # mutually exclusive instrument groups
    d["instrument"] = np.select(
        [(d.ap == 1) & (d.dual == 0), (d.dual == 1) & (d.ap == 0),
         (d.ap == 1) & (d.dual == 1)],
        ["AP only", "Dual only", "Both"], default="No credit")
    return d


def cells(d: pd.DataFrame, courses: list[str]) -> pd.DataFrame:
    s = d[d.course.isin(courses) & d.instrument.isin(["AP only", "Dual only"])]
    g = (s.groupby(["course", "instrument"], observed=True)
           .agg(n_students=("dfw", "size"),
                pct_dfw=("dfw", lambda x: 100 * x.mean()),
                mean_satact_math=("satact_math", "mean"))
           .reset_index())
    return g.round(3)


def fig(g: pd.DataFrame, courses: list[str]) -> str:
    x = np.arange(len(courses))
    w = 0.36
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    for i, inst in enumerate(["AP only", "Dual only"]):
        vals, ns = [], []
        for c in courses:
            r = g[(g.course == c) & (g.instrument == inst)]
            vals.append(float(r.pct_dfw.iloc[0]) if len(r) else np.nan)
            ns.append(int(r.n_students.iloc[0]) if len(r) else 0)
        pos = x + (i - 0.5) * w
        ax.bar(pos, vals, w * 0.92, color=SERIES[i], label=inst, zorder=3)
        for p, v, n in zip(pos, vals, ns):
            if np.isfinite(v):
                ax.text(p, v + 0.6, f"{v:.0f}", ha="center", fontsize=9,
                        color=SERIES[i], fontweight="bold")
                ax.text(p, -2.2, f"n={n:,}", ha="center", fontsize=7.5, color=MUTED)
    ax.set_xticks(x)
    ax.set_xticklabels([c.replace(" for ", "\nfor ") for c in courses], fontsize=9)
    ax.set_ylabel("% D / F / W in first attempt")
    ax.set_ylim(bottom=-4)
    ax.legend(loc="upper right")
    return finish(fig, ax, "014_instrument_dfw",
                  "Within the same course, dual-credit students fail more often than AP students",
                  "First attempt only. Groups are mutually exclusive (students "
                  "holding both are excluded). Not causal: the instrument is "
                  "chosen by district and family, not assigned.")


def main() -> int:
    d = frame()
    OUT["n_attempts"] = int(len(d))
    top = (d[d.instrument.isin(["AP only", "Dual only"])]
           .groupby("course").size().sort_values(ascending=False))
    courses = [c for c in top.index[:5]]
    OUT["courses"] = courses

    g = cells(d, courses)
    for _, r in g.iterrows():
        OUT[f"dfw_{r.course}_{r.instrument}".replace(" ", "_")] = float(r.pct_dfw)

    # SAT-stratified check on the largest course
    c0 = courses[0]
    s = d[(d.course == c0) & d.instrument.isin(["AP only", "Dual only"])
          & d.satact_math.notna()].copy()
    s["sat_band"] = pd.cut(s.satact_math, [0, 500, 550, 600, 900],
                           labels=["<500", "500-549", "550-599", "600+"])
    strat = (s.groupby(["sat_band", "instrument"], observed=True)
               .agg(n_students=("dfw", "size"),
                    pct_dfw=("dfw", lambda x: 100 * x.mean())).reset_index())
    strat["sat_band"] = strat.sat_band.astype(str)
    OUT["strat_course"] = c0

    OUT["figures"] = [fig(g, courses)]
    gl.publish(g, "utsa_dfw_by_instrument", ["course", "instrument"])
    g.to_csv(os.path.join(FIGDIR, "014_instrument_dfw.csv"), index=False)
    strat.round(3).to_csv(os.path.join(FIGDIR, "014_sat_stratified.csv"), index=False)
    with open(os.path.join(FIGDIR, "014_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(g.to_string(index=False))
    print()
    print(f"--- SAT-stratified, {c0} ---")
    print(strat.round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
