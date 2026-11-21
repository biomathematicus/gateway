"""
Report 017 — Does the grade earned in the dual course carry any signal?

Reports 014-016 showed dual-credit students underperform AP students by ~8-9
points, within school and within SAT band, and that the gap is carried forward
rather than being a one-off mis-placement. The open question is whether the dual
credit is uninformative as a whole, or whether it discriminates internally --
whether a dual A means something a dual C does not.

WHAT MAKES THIS TESTABLE. `MAT{1073,1093,1214,1224}_AP_GRDE` is *always* the
literal 'CR' -- AP credit records no letter grade, so AP has no internal
gradient to read. `MAT*_DUAL_GRDE` DOES carry A / B / C. So the dual instrument
can be split by its own grade and each level compared against AP.

TWO OUTCOMES, both informative:
  - If dual A >> dual C, the grade is a real signal that placement ignores. The
    fix is to use it: treat a dual C as not conferring credit.
  - If dual A ~ dual C, the grade carries little information about readiness,
    and no placement rule built on it can work.
  - Either way, comparing dual A against AP asks whether the BEST dual outcome
    reaches the AP baseline.

THE PRIOR COURSE IS CHOSEN TO MATCH. For a student sitting UTSA Calculus II, the
relevant prior credit is Calculus I (MAT1214), not some highest-grade summary.
PRIOR maps each UTSA course to the dual course immediately beneath it.

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
from courses import canon
from instrument_outcome import COURSE_SQL, DFW

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from analysis.style import FIGDIR, MUTED, SERIES, finish, setup  # noqa: E402

setup()
OUT: dict = {}

#: UTSA course -> the dual course immediately beneath it
PRIOR = {"Precalculus": "MAT1073",
         "Calculus I": "MAT1093",
         "Calculus II": "MAT1214",
         "Calculus III": "MAT1224"}

#: the dual courses in ladder order, lowest first
LADDER = ["MAT1073", "MAT1093", "MAT1214", "MAT1224"]


def _grade(row, prior: str, fallback: bool) -> str:
    """The dual grade to attribute to this attempt.

    Strict rule (`fallback=False`): the grade in the course immediately beneath
    the one being sat, and nothing else. Clean, but it discards students whose
    dual credit sits elsewhere on the ladder -- 1,499 attempts, every one of
    which DOES carry a dual grade in some course. They are not ungraded awards.

    Fallback rule (`fallback=True`): if that cell is empty, take the highest
    dual grade the student holds at or below `prior`; failing that, the lowest
    they hold anywhere. Recovers the 1,499 at the cost of comparing grades from
    courses of differing distance to the one being sat.
    """
    g = str(row.get(f"dual_{prior}") or "").strip().upper()
    if g in ("A", "B", "C") or not fallback:
        return g
    below = LADDER[:LADDER.index(prior) + 1][::-1]
    for c in below + LADDER:
        g = str(row.get(f"dual_{c}") or "").strip().upper()
        if g in ("A", "B", "C"):
            return g
    return ""

GRADE_SQL = """
SELECT IDENTIFIER,
  MAX(MAT1073_DUAL_GRDE) AS dual_MAT1073, MAX(MAT1093_DUAL_GRDE) AS dual_MAT1093,
  MAX(MAT1214_DUAL_GRDE) AS dual_MAT1214, MAX(MAT1224_DUAL_GRDE) AS dual_MAT1224,
  MAX(CASE WHEN MAT1073_AP_GRDE IS NOT NULL OR MAT1093_AP_GRDE IS NOT NULL
            OR MAT1214_AP_GRDE IS NOT NULL OR MAT1224_AP_GRDE IS NOT NULL
           THEN 1 ELSE 0 END) AS ap,
  MAX(CASE WHEN MAT1073_DUAL_GRDE IS NOT NULL OR MAT1093_DUAL_GRDE IS NOT NULL
            OR MAT1214_DUAL_GRDE IS NOT NULL OR MAT1224_DUAL_GRDE IS NOT NULL
           THEN 1 ELSE 0 END) AS dual,
  MAX(HIGHEST_SATACT_MATH) AS satact_math
FROM OIR2 GROUP BY IDENTIFIER
"""


def frame(fallback: bool = False) -> pd.DataFrame:
    c = db.cached_query("mat-course-attempts", COURSE_SQL)
    gr = db.cached_query("dual-grades-by-student", GRADE_SQL)
    for k in ("ap", "dual"):
        gr[k] = pd.to_numeric(gr[k], errors="coerce").fillna(0).astype(int)
    gr["satact_math"] = pd.to_numeric(gr.satact_math, errors="coerce")

    c["course"] = c.title.map(canon)
    c["term_n"] = pd.to_numeric(c.term, errors="coerce")
    c = c.sort_values(["IDENTIFIER", "course", "term_n"])
    f = c.drop_duplicates(subset=["IDENTIFIER", "course"], keep="first").copy()
    f["dfw"] = f.grade.astype(str).str.strip().str.upper().isin(DFW).astype(int)
    f = f[f.course.isin(PRIOR)]

    d = f.merge(gr, on="IDENTIFIER", how="left")
    for k in ("ap", "dual"):
        d[k] = pd.to_numeric(d[k], errors="coerce").fillna(0).astype(int)
    d = d[(d.ap + d.dual) == 1]

    pri = d.course.map(PRIOR)
    d["prior_grade"] = [_grade(r, p, fallback)
                        for (_, r), p in zip(d.iterrows(), pri)]
    d["group"] = np.where(
        d.ap == 1, "AP credit",
        np.where(d.prior_grade.isin(["A", "B", "C"]),
                 "Dual " + d.prior_grade, "Dual (off-ladder)"))
    return d


def table(d: pd.DataFrame, by_course: bool) -> pd.DataFrame:
    keys = (["course", "group"] if by_course else ["group"])
    g = (d.groupby(keys, observed=True)
           .agg(n_students=("dfw", "size"),
                pct_dfw=("dfw", lambda x: 100 * x.mean()),
                mean_satact_math=("satact_math", "mean"))
           .reset_index())
    return g.round(3)


def lpm(d: pd.DataFrame, sat: bool) -> pd.DataFrame:
    """DFW ~ dual A/B/C (AP credit is the omitted baseline), course FE, HC1.

    Clustering is on the high school where available; here the fixed effect is
    course, of which there are four, so a clustered estimate is not usable and
    SEs are heteroskedasticity-robust instead.
    """
    s = d[d.group.isin(["AP credit", "Dual A", "Dual B", "Dual C"])].copy()
    if sat:
        s = s.dropna(subset=["satact_math"])
    levels = ["Dual A", "Dual B", "Dual C"]
    cols = list(levels) + (["sat"] if sat else [])
    df = pd.DataFrame({lv: (s.group == lv).astype(float).values for lv in levels})
    if sat:
        df["sat"] = s.satact_math.astype(float).values
    df["y"] = s.dfw.astype(float).values
    df["g"] = s.course.values
    for c in cols + ["y"]:
        df[c] = df[c] - df.groupby("g")[c].transform("mean")
    X, y = df[cols].values, df["y"].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    n, k = X.shape
    V = XtX_inv @ (X.T @ (X * (r ** 2)[:, None])) @ XtX_inv * (n / (n - k))
    se = np.sqrt(np.diag(V))
    return pd.DataFrame({
        "term": levels, "sat_control": sat, "n": n,
        "beta_pp": [round(b * 100, 2) for b in beta[:3]],
        "se_pp": [round(e * 100, 2) for e in se[:3]],
        "z": [round(b / e, 2) for b, e in zip(beta[:3], se[:3])]})


def fig(g: pd.DataFrame, order: list[str]) -> str:
    g = g.set_index("group").reindex(order).dropna(subset=["pct_dfw"])
    x = np.arange(len(g))
    colors = [SERIES[0]] + [SERIES[1]] * (len(g) - 1)
    fig, ax = plt.subplots(figsize=(7.6, 4.7))
    ax.bar(x, g.pct_dfw, 0.52, color=colors, zorder=3)
    for i, (v, n) in enumerate(zip(g.pct_dfw, g.n_students)):
        ax.text(i, v + 0.9, f"{v:.0f}", ha="center", fontsize=10,
                color=colors[i], fontweight="bold")
        ax.text(i, -3.0, f"n={int(n):,}", ha="center", fontsize=7.5, color=MUTED)
    ax.axhline(float(g.pct_dfw.iloc[0]), color=SERIES[0], lw=1.5, ls="--",
               zorder=2, alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(g.index, fontsize=9)
    ax.set_ylabel("% D / F / W, first attempt")
    ax.set_ylim(bottom=-5)
    return finish(fig, ax, "017_dual_grade_signal",
                  "The dual grade is highly informative: A to C spans 30 points",
                  "Grade is the dual grade in the course immediately beneath the "
                  "one being sat. AP credit records no letter grade (always "
                  "'CR'), so it has no internal gradient — the dashed line is "
                  "its single rate. These are raw rates; dual-A students average "
                  "596 on SAT/ACT maths against 679 for AP. Not causal.")


def fig_adj(models: pd.DataFrame) -> str:
    m = models[models.sat_control].set_index("term")
    order = ["Dual A", "Dual B", "Dual C"]
    x = np.arange(len(order))
    ys = [m.beta_pp[k] for k in order]
    es = [1.96 * m.se_pp[k] for k in order]
    fig, ax = plt.subplots(figsize=(7.0, 4.5))
    ax.errorbar(x, ys, yerr=es, fmt="o", ms=9, capsize=5, lw=2,
                color=SERIES[1], zorder=3)
    for xi, y in zip(x, ys):
        ax.text(xi + 0.07, y, f"{y:+.1f}", ha="left", va="center", fontsize=10,
                color=SERIES[1], fontweight="bold")
    ax.axhline(0, color=SERIES[0], lw=1.5, zorder=2)
    ax.text(len(order) - 0.5, 0.9, "AP credit baseline", ha="right", fontsize=8.5,
            color=SERIES[0])
    ax.set_xticks(x)
    ax.set_xticklabels(order, fontsize=10)
    ax.set_xlim(-0.5, len(order) - 0.4)
    ax.set_ylabel("DFW gap vs AP credit\n(percentage points)")
    return finish(fig, ax, "017_dual_grade_adjusted",
                  "Adjusted for SAT/ACT maths, only dual B and C carry a penalty",
                  "Linear probability model on first-attempt DFW with course "
                  "fixed effects and SAT/ACT maths, AP credit omitted as the "
                  "baseline; 95% CI from HC1-robust SEs. Dual A does not differ "
                  "significantly from AP credit (z = 1.76). Not causal.")


def main() -> int:
    d = frame()
    order = ["AP credit", "Dual A", "Dual B", "Dual C"]
    g = table(d, by_course=False)
    gc = table(d, by_course=True)

    OUT["n_attempts"] = int(len(d))
    for _, r in g.iterrows():
        OUT[f"dfw_{r.group}".replace(" ", "_")] = float(r.pct_dfw)
        OUT[f"sat_{r.group}".replace(" ", "_")] = float(r.mean_satact_math)

    # monotonicity within dual: does the grade discriminate at all?
    dual = g[g.group.isin(["Dual A", "Dual B", "Dual C"])].set_index("group")
    if len(dual) == 3:
        OUT["dual_A_to_C_spread"] = round(
            float(dual.pct_dfw["Dual C"] - dual.pct_dfw["Dual A"]), 2)
        OUT["dual_A_vs_AP_gap"] = round(
            float(dual.pct_dfw["Dual A"]
                  - g.set_index("group").pct_dfw["AP credit"]), 2)

    models = pd.concat([lpm(d, False), lpm(d, True)], ignore_index=True)
    OUT["models"] = models.to_dict("records")

    # SENSITIVITY: the fallback rule recovers the off-ladder dual awards
    # (1,499 -> 9). Point estimates barely move, but n grows ~34% and the
    # dual-A contrast becomes significant, so the strict rule's null is partly
    # a power result. Reported, not swapped in.
    dfb = frame(fallback=True)
    fb = lpm(dfb, True).assign(rule="fallback")
    models_fb = pd.concat([models[models.sat_control].assign(rule="strict"), fb],
                          ignore_index=True)
    OUT["models_fallback"] = models_fb.to_dict("records")
    OUT["n_off_ladder_strict"] = int((d.group == "Dual (off-ladder)").sum())
    OUT["n_off_ladder_fallback"] = int((dfb.group == "Dual (off-ladder)").sum())

    # dual A against AP within SAT band -- the tightest comparison available
    s = d[d.group.isin(["AP credit", "Dual A"]) & d.satact_math.notna()].copy()
    s["sat_band"] = pd.cut(s.satact_math, [0, 550, 600, 650, 900],
                           labels=["<550", "550-599", "600-649", "650+"])
    strat = (s.groupby(["sat_band", "group"], observed=True)
               .agg(n_students=("dfw", "size"),
                    pct_dfw=("dfw", lambda x: 100 * x.mean())).reset_index())
    strat["sat_band"] = strat.sat_band.astype(str)
    strat = strat.round(3)

    OUT["figures"] = [fig(g, order), fig_adj(models)]
    gl.publish(g, "utsa_dfw_by_dual_grade", ["group"])
    g.to_csv(os.path.join(FIGDIR, "017_dual_grade.csv"), index=False)
    gc.to_csv(os.path.join(FIGDIR, "017_dual_grade_by_course.csv"), index=False)
    with open(os.path.join(FIGDIR, "017_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    models.to_csv(os.path.join(FIGDIR, "017_models.csv"), index=False)
    models_fb.to_csv(os.path.join(FIGDIR, "017_models_fallback.csv"), index=False)
    strat.to_csv(os.path.join(FIGDIR, "017_sat_stratified.csv"), index=False)
    print(g.to_string(index=False))
    print()
    print(gc.to_string(index=False))
    print("\n--- LPM vs AP baseline, course FE, HC1 robust ---")
    print(models.to_string(index=False))
    print("\n--- Dual A vs AP within SAT band ---")
    print(strat.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
