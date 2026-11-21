"""
Reports 002 and 003 — poverty and Algebra II access at district level.

002 hardens the AISES slide "Poverty is a Strong Predictor of Absence of Algebra
II in High School". The original plotted CRDC 2017 Algebra II enrollees against
SAIPE children in poverty, one dot per district, with a y=x reference line and
the observation that districts below it have more children in poverty than
children taking Algebra II. Three things are added here:

  * sentinel-safe totals (the CRDC reserve codes are removed, not summed);
  * the share of districts below the line is COUNTED, not eyeballed;
  * a rate view, because a count scatter is dominated by district size and will
    look like a strong relationship even if the rate relationship is weak.

003 asks the question that actually licenses averaging: is the poverty ->
Algebra II RELATIONSHIP stable between cycles, and does Texas differ? Report 001
shows poverty LEVELS are persistent; that is not the same claim.
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
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402

setup()
OUT: dict = {}


def load() -> pd.DataFrame:
    return db.read_sql("""
        SELECT cycle, vintage, leaid, state_pc, pop_5_17, pov_5_17, pov_rate,
               alg2_enrollees, enr_total, n_schools, n_alg2_reported,
               n_alg2_missing, below_parity, alg2_per_poor_child, alg2_per_child
        FROM mart.alg2_poverty
        WHERE alg2_enrollees IS NOT NULL AND pov_5_17 IS NOT NULL
          AND pop_5_17 > 0
    """)


def fig_parity(d: pd.DataFrame, cycle: str) -> str:
    s = d[d.cycle == cycle]
    fig, ax = plt.subplots(figsize=(7.0, 5.4))
    ax.scatter(s.pov_5_17, s.alg2_enrollees, s=7, color=SERIES[1],
               alpha=0.28, linewidths=0, zorder=3)
    hi = float(np.nanpercentile(
        pd.concat([s.pov_5_17, s.alg2_enrollees]), 99.9))
    ax.plot([0, hi], [0, hi], color=SERIES[0], lw=2, zorder=4)
    ax.text(hi * 0.97, hi * 0.99, "parity (y = x)", ha="right", va="bottom",
            fontsize=9, color=SERIES[0], fontweight="bold")
    pct = OUT[f"pct_below_parity_{cycle}"]
    ax.set_xlim(0, hi); ax.set_ylim(0, hi)
    ax.set_xlabel("children 5–17 in poverty (SAIPE)")
    ax.set_ylabel("Algebra II enrollees (CRDC)")
    ax.set_aspect("equal")
    return finish(fig, ax, f"002_parity_{cycle.replace('-', '')}",
                  f"{pct}% of districts sit below parity, {cycle}",
                  f"One dot per school district ({len(s):,} districts). Below the "
                  f"line a district has more children in poverty than children "
                  f"enrolled in Algebra II. Axes clipped at the 99.9th percentile.")


def fig_rate(d: pd.DataFrame) -> str:
    """The rate view. A count scatter mostly measures district size."""
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for i, cycle in enumerate(sorted(d.cycle.unique())):
        s = d[(d.cycle == cycle) & d.alg2_per_child.notna()]
        s = s[(s.pov_rate <= 0.6) & (s.alg2_per_child <= 0.6)]
        b = pd.cut(s.pov_rate, np.arange(0, 0.62, 0.04))
        g = s.groupby(b, observed=True)["alg2_per_child"].median()
        ctr = [iv.mid for iv in g.index]
        ax.plot(ctr, g.values, color=SERIES[i], lw=2, marker="o", ms=5,
                label=cycle, zorder=3)
    ax.set_xlabel("district child poverty rate (SAIPE, ages 5–17)")
    ax.set_ylabel("Algebra II enrollees per child 5–17")
    ax.legend(loc="upper right")
    return finish(fig, ax, "002_rate_gradient",
                  "Algebra II access falls as district poverty rises",
                  "Median within 4-point poverty bins; both cycles shown. "
                  "Rates, not counts, so district size is divided out.")


def ols(x: np.ndarray, y: np.ndarray, w: np.ndarray | None = None):
    """(W)LS slope with a correct variance.

    The first version normalised the weights to sum to 1 before forming
    s^2 = sum(w e^2)/(1 - k/n), which is dimensionally inconsistent with
    (X'WX)^-1 and produced a standard error ~6x the slope. Weighted least
    squares uses the RAW weights throughout:
        beta = (X'WX)^-1 X'Wy ,  s^2 = sum(w e^2)/(n-k) ,  Var = s^2 (X'WX)^-1
    """
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    w = None if w is None else np.asarray(w, float)[m]
    n, k = len(y), 2
    X = np.column_stack([np.ones_like(x), x])
    if w is None:
        w = np.ones(n)
    m2 = np.isfinite(w) & (w > 0)
    X, y, w = X[m2], y[m2], w[m2]
    n = len(y)
    XtW = X.T * w
    XtWX = XtW @ X
    beta = np.linalg.solve(XtWX, XtW @ y)
    resid = y - X @ beta
    s2 = float((w * resid ** 2).sum() / (n - k))
    cov = s2 * np.linalg.inv(XtWX)
    se = np.sqrt(np.diag(cov))
    return float(beta[1]), float(se[1]), float(beta[0]), int(n)


def relationship(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cycle in sorted(d.cycle.unique()):
        for scope, sel in (("national", d.cycle == cycle),
                           ("Texas", (d.cycle == cycle) & (d.state_pc == "TX"))):
            s = d[sel & d.alg2_per_child.notna() & d.pov_rate.notna()]
            if len(s) < 30:
                continue
            b, se, a, n = ols(s.pov_rate.values, s.alg2_per_child.values,
                              s.pop_5_17.values)
            rows.append({"cycle": cycle, "scope": scope, "slope": b, "se": se,
                         "intercept": a, "n": n})
    r = pd.DataFrame(rows)
    for _, x in r.iterrows():
        OUT[f"slope_{x.scope}_{x.cycle}"] = round(x.slope, 4)
        OUT[f"se_{x.scope}_{x.cycle}"] = round(x.se, 4)
    for scope in ("national", "Texas"):
        sub = r[r.scope == scope].sort_values("cycle")
        if len(sub) == 2:
            d1, d2 = sub.iloc[0], sub.iloc[1]
            diff = d2.slope - d1.slope
            sed = float(np.hypot(d1.se, d2.se))
            OUT[f"slope_change_{scope}"] = round(diff, 4)
            OUT[f"slope_change_z_{scope}"] = round(diff / sed, 2) if sed else None
    return r


def fig_slopes(r: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    scopes = ["national", "Texas"]
    cycles = sorted(r.cycle.unique())
    xpos = np.arange(len(scopes))
    width = 0.34
    for i, cycle in enumerate(cycles):
        vals, errs = [], []
        for sc in scopes:
            row = r[(r.scope == sc) & (r.cycle == cycle)]
            vals.append(float(row.slope.iloc[0]) if len(row) else np.nan)
            errs.append(1.96 * float(row.se.iloc[0]) if len(row) else np.nan)
        pos = xpos + (i - 0.5) * width
        ax.bar(pos, vals, width * 0.92, color=SERIES[i], label=cycle, zorder=3)
        ax.errorbar(pos, vals, yerr=errs, fmt="none", ecolor=INK2,
                    elinewidth=1.2, capsize=3, zorder=4)
        for p, v in zip(pos, vals):
            ax.text(p, v - 0.012, f"{v:.3f}", ha="center", va="top",
                    fontsize=9, color="#ffffff", fontweight="bold")
    ax.axhline(0, color=MUTED, lw=1)
    ax.set_xticks(xpos); ax.set_xticklabels(scopes)
    ax.set_ylabel("slope: Δ Algebra II per child\nper unit poverty rate")
    ax.legend(loc="lower left")
    return finish(fig, ax, "003_slope_stability",
                  "The poverty→Algebra II slope is stable across cycles — and flatter in Texas",
                  "Population-weighted OLS, one observation per district. Bars are "
                  "95% CI. A more negative slope = access falls faster as poverty "
                  "rises. Texas is about half the national gradient in both cycles.")


def main() -> int:
    d = load()
    OUT["n_districts_matched"] = int(d.leaid.nunique())
    for cycle in sorted(d.cycle.unique()):
        s = d[d.cycle == cycle]
        OUT[f"n_{cycle}"] = int(len(s))
        OUT[f"pct_below_parity_{cycle}"] = round(100 * s.below_parity.mean(), 1)
        OUT[f"median_alg2_per_poor_child_{cycle}"] = round(
            float(s.alg2_per_poor_child.median()), 3)
        OUT[f"total_alg2_{cycle}"] = int(s.alg2_enrollees.sum())
        OUT[f"total_pov_{cycle}"] = int(s.pov_5_17.sum())

    figs = [fig_parity(d, "2017-18"), fig_parity(d, "2021-22"), fig_rate(d)]
    r = relationship(d)
    figs.append(fig_slopes(r))
    OUT["figures"] = figs

    r.to_csv(os.path.join(FIGDIR, "003_slopes.csv"), index=False)
    d.groupby("cycle").agg(
        districts=("leaid", "nunique"),
        alg2=("alg2_enrollees", "sum"),
        pov=("pov_5_17", "sum"),
        pct_below=("below_parity", "mean"),
    ).to_csv(os.path.join(FIGDIR, "002_summary.csv"))

    with open(os.path.join(FIGDIR, "002_003_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(json.dumps(OUT, indent=1))
    print()
    print(r.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
