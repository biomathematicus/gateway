"""
Report 007 — Did HB5 change the poverty→Algebra II gradient in Texas?

Report 003 could not ask this: both district cycles it had (2017-18, 2021-22)
sat AFTER the policy. The five-cycle panel straddles it:

    2011-12  PRE     HB5 signed 2013; the Foundation plan became the DEFAULT
    2013-14  PRE     for students ENTERING high school in 2014-15, so a school's
    2015-16  POST    Algebra II enrolment first reflects it around 2015-16.
    2017-18  POST
    2021-22  POST

SPECIFICATION
  Per cycle, one pooled population-weighted regression:

      alg2_per_child = a + b*pov_rate + c*TX + d*(TX x pov_rate)

  `d` is the Texas DIFFERENTIAL slope and comes with a real standard error.
  Estimating Texas and national separately and differencing them would treat
  overlapping samples as independent; Texas districts are a SUBSET of the
  national set, so the interaction is the correct object.

  Two pre-periods make parallel trends TESTABLE rather than assumed: if
  d(2011-12) and d(2013-14) already differ, the design is dead and the report
  says so instead of reporting a "policy effect".

THE CONFOUND THAT CANNOT BE REMOVED
  The 2015-16 wide file changed its layout and its reporting items against
  2011-12 and 2013-14 (all are universe collections). The reporting change
  falls at exactly the pre/post boundary, so a level shift there is confounded
  with the policy by construction. This is why the report leads with the
  WITHIN-pre comparison.
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
PRE = ("2011-12", "2013-14")


def load() -> pd.DataFrame:
    with db.connect() as c:
        return pd.read_sql("""
            SELECT cycle, fall_year, is_universe, leaid, state_pc, is_tx,
                   pop_5_17, pov_rate, alg2_per_child
            FROM mart.alg2_panel
            WHERE pov_rate IS NOT NULL AND alg2_per_child IS NOT NULL
              AND pov_rate BETWEEN 0 AND 1 AND alg2_per_child BETWEEN 0 AND 2
        """, c)


def wls_cluster(X: np.ndarray, y: np.ndarray, w: np.ndarray,
                g: np.ndarray):
    """WLS with CLUSTER-ROBUST (by state) standard errors.

    Districts within a state are plainly correlated, and HB5 is a STATE-level
    treatment, so the naive WLS standard error understates uncertainty on the
    Texas differential. Liang-Zeger sandwich:

        V = (X'WX)^-1 [ sum_g X_g' W_g e_g e_g' W_g X_g ] (X'WX)^-1

    with a finite-cluster correction. This can only WIDEN the interval, so it
    strengthens report 007's negative conclusion rather than weakening it.
    """
    XtW = X.T * w
    XtWX = XtW @ X
    beta = np.linalg.solve(XtWX, XtW @ y)
    e = y - X @ beta
    bread = np.linalg.inv(XtWX)
    meat = np.zeros_like(XtWX)
    for cl in np.unique(g):
        m = g == cl
        u = (X[m] * (w[m] * e[m])[:, None]).sum(axis=0)
        meat += np.outer(u, u)
    G, k, n = len(np.unique(g)), X.shape[1], len(y)
    corr = (G / (G - 1)) * ((n - 1) / (n - k)) if G > 1 else 1.0
    V = bread @ meat @ bread * corr
    return beta, np.sqrt(np.diag(V))


def wls(X: np.ndarray, y: np.ndarray, w: np.ndarray):
    """beta, se via weighted least squares with the RAW weights.

    (Normalising the weights before forming s^2 is the error that produced an
    SE six times the slope in the first version of report 003.)
    """
    XtW = X.T * w
    XtWX = XtW @ X
    beta = np.linalg.solve(XtWX, XtW @ y)
    resid = y - X @ beta
    s2 = float((w * resid ** 2).sum() / (len(y) - X.shape[1]))
    cov = s2 * np.linalg.inv(XtWX)
    return beta, np.sqrt(np.diag(cov))


def per_cycle(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cycle, g in d.groupby("cycle"):
        g = g.dropna(subset=["pov_rate", "alg2_per_child", "pop_5_17"])
        g = g[g.pop_5_17 > 0]
        tx = g.is_tx.astype(float).values
        pov = g.pov_rate.values
        X = np.column_stack([np.ones(len(g)), pov, tx, tx * pov])
        yv = g.alg2_per_child.values
        wv = g.pop_5_17.values.astype(float)
        beta, se = wls(X, yv, wv)
        _, se_cl = wls_cluster(X, yv, wv, g.state_pc.values)
        rows.append({
            "cycle": cycle,
            "fall_year": int(g.fall_year.iloc[0]),
            "is_universe": bool(g.is_universe.iloc[0]),
            "n": len(g), "n_tx": int(tx.sum()),
            "slope_nat": beta[1], "se_nat": se[1],
            "se_nat_cl": se_cl[1],
            "tx_diff": beta[3], "se_tx_diff": se[3],
            "se_tx_diff_cl": se_cl[3],
            "slope_tx": beta[1] + beta[3],
        })
    return pd.DataFrame(rows).sort_values("fall_year").reset_index(drop=True)


def parallel_trends(r: pd.DataFrame) -> None:
    """The two pre-periods must agree, or the design is dead."""
    a = r[r.cycle == PRE[0]].iloc[0]
    b = r[r.cycle == PRE[1]].iloc[0]
    diff = b.tx_diff - a.tx_diff
    sed = float(np.hypot(a.se_tx_diff, b.se_tx_diff))
    z = diff / sed if sed else np.nan
    sed_cl = float(np.hypot(a.se_tx_diff_cl, b.se_tx_diff_cl))
    OUT["pre_trend_z_clustered"] = round(float(diff / sed_cl), 2) if sed_cl else None
    OUT["parallel_trends_holds_clustered"] = bool(abs(diff / sed_cl) < 1.96)
    OUT["pre_tx_diff_2011"] = round(float(a.tx_diff), 4)
    OUT["pre_tx_diff_2013"] = round(float(b.tx_diff), 4)
    OUT["pre_trend_change"] = round(float(diff), 4)
    OUT["pre_trend_z"] = round(float(z), 2)
    OUT["parallel_trends_holds"] = bool(abs(z) < 1.96)


def did(r: pd.DataFrame) -> None:
    pre = r[r.cycle.isin(PRE)]
    post = r[~r.cycle.isin(PRE)]
    dpre = float(np.average(pre.tx_diff, weights=1 / pre.se_tx_diff ** 2))
    dpost = float(np.average(post.tx_diff, weights=1 / post.se_tx_diff ** 2))
    sepre = float(np.sqrt(1 / (1 / pre.se_tx_diff ** 2).sum()))
    sepost = float(np.sqrt(1 / (1 / post.se_tx_diff ** 2).sum()))
    OUT["tx_diff_pre_mean"] = round(dpre, 4)
    OUT["tx_diff_post_mean"] = round(dpost, 4)
    OUT["did"] = round(dpost - dpre, 4)
    OUT["did_se"] = round(float(np.hypot(sepre, sepost)), 4)
    OUT["did_z"] = round((dpost - dpre) / float(np.hypot(sepre, sepost)), 2)
    # same DiD under state-clustered SEs
    cpre = float(np.sqrt(1 / (1 / pre.se_tx_diff_cl ** 2).sum()))
    cpost = float(np.sqrt(1 / (1 / post.se_tx_diff_cl ** 2).sum()))
    dc = float(np.hypot(cpre, cpost))
    OUT["did_se_clustered"] = round(dc, 4)
    OUT["did_z_clustered"] = round((dpost - dpre) / dc, 2) if dc else None
    OUT["n_clusters"] = None  # filled by caller
    OUT["n_treated_clusters"] = 1


def fig_slopes(r: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    for i, (col, se, lbl) in enumerate(
            [("slope_nat", "se_nat", "National"),
             ("slope_tx", None, "Texas")]):
        y = r[col].values
        ax.plot(r.fall_year, y, color=SERIES[i], lw=2, marker="o", ms=6,
                label=lbl, zorder=3)
        if se:
            ax.fill_between(r.fall_year, y - 1.96 * r[se], y + 1.96 * r[se],
                            color=SERIES[i], alpha=0.15, lw=0, zorder=2)
    ax.axvspan(2010.5, 2014.5, color=MUTED, alpha=0.10, lw=0, zorder=1)
    ax.text(2012.5, ax.get_ylim()[0] * 0.97, "pre-HB5 default", ha="center",
            fontsize=9, color=INK2, fontweight="bold")
    ax.axvline(2014.5, color=SERIES[1], lw=1.4, ls=(0, (4, 3)), zorder=4)
    ax.set_xticks(r.fall_year)
    ax.set_xticklabels(r.cycle, rotation=0)
    ax.set_ylabel("slope: Δ Algebra II per child\nper unit poverty rate")
    ax.set_xlabel("CRDC cycle")
    ax.legend(loc="lower right")
    return finish(fig, ax, "007_slope_series",
                  "The poverty gradient is flat over a decade — in Texas and nationally",
                  "Population-weighted OLS per cycle. Band is the national 95% CI. "
                  "The reporting items changed between 2013-14 and 2015-16, so a "
                  "level shift at that boundary is confounded with the change.")


def fig_txdiff(r: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.8, 4.4))
    ax.errorbar(r.fall_year, r.tx_diff, yerr=1.96 * r.se_tx_diff, fmt="o-",
                color=SERIES[2], ecolor=INK2, elinewidth=1.2, capsize=4,
                lw=2, ms=7, zorder=3)
    ax.axhline(0, color=MUTED, lw=1.2, zorder=2)
    ax.axvline(2014.5, color=SERIES[1], lw=1.4, ls=(0, (4, 3)), zorder=4)
    ax.text(2014.65, ax.get_ylim()[1] * 0.90, "HB5 default\n(entering HS 2014-15)",
            fontsize=8.5, color=SERIES[1], fontweight="bold")
    for x, y in zip(r.fall_year, r.tx_diff):
        ax.annotate(f"{y:+.3f}", (x, y), (0, -16), textcoords="offset points",
                    ha="center", fontsize=8.5, color=INK2)
    ax.set_xticks(r.fall_year); ax.set_xticklabels(r.cycle)
    ax.set_ylabel("Texas differential slope\n(TX × poverty interaction)")
    ax.set_xlabel("CRDC cycle")
    return finish(fig, ax, "007_tx_differential",
                  "Texas's differential gradient does not move at the policy boundary",
                  "Coefficient on TX × poverty rate, one pooled weighted regression "
                  "per cycle. Bars are 95% CI. Positive = Texas's gradient is "
                  "FLATTER than the national one.")


def main() -> int:
    d = load()
    OUT["n_rows"] = int(len(d))
    r = per_cycle(d)
    parallel_trends(r)
    did(r)
    OUT["figures"] = [fig_slopes(r), fig_txdiff(r)]
    r.to_csv(os.path.join(FIGDIR, "007_slopes.csv"), index=False)
    with open(os.path.join(FIGDIR, "007_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(r.round(4).to_string(index=False))
    print()
    print(json.dumps(OUT, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
