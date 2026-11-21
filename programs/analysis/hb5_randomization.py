"""
Report 010 — Randomization inference for the HB5 difference-in-differences.

WHY THIS IS NEEDED. Report 007 §7 established that neither standard error is
trustworthy: there are ~51 clusters but exactly ONE treated cluster (Texas).
Cluster-robust variance estimation degenerates in that case — the meat matrix
receives a single non-zero contribution from the treated group — and the
resulting test can over- or under-reject severely. That is structural to
comparing one state against the rest and no amount of extra data fixes it.

THE TEST THAT DOES WORK. Randomization inference makes no distributional
assumption at all. Re-run the ENTIRE difference-in-differences 51 times, once
per state, pretending each in turn is the treated unit. Texas's real estimate is
then located in the distribution of placebo estimates, and its rank IS the
p-value:

    p = (# states with |DiD| >= |DiD_Texas|) / 51

This asks the only question the design can answer: is what happened in Texas
unusual relative to what "happened" in states where nothing happened?

FLOOR ON THE P-VALUE. With 51 states the smallest attainable p is 1/51 = 0.0196.
A null result here cannot be rescued by more precision; it would need more
treated units, which do not exist.
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
            SELECT cycle, fall_year, leaid, state_pc,
                   pop_5_17, pov_rate, alg2_per_child
            FROM mart.alg2_panel
            WHERE pov_rate IS NOT NULL AND alg2_per_child IS NOT NULL
              AND pov_rate BETWEEN 0 AND 1 AND alg2_per_child BETWEEN 0 AND 2
              AND pop_5_17 > 0
        """, c)


def did_for_state(d: pd.DataFrame, st: str) -> tuple[float, float]:
    """(DiD, pre-trend change) treating `st` as the treated unit."""
    diffs = {}
    for cycle, g in d.groupby("cycle"):
        t = (g.state_pc.values == st).astype(float)
        if t.sum() < 30:                      # too few districts to identify
            return np.nan, np.nan
        pov = g.pov_rate.values
        X = np.column_stack([np.ones(len(g)), pov, t, t * pov])
        w = g.pop_5_17.values.astype(float)
        XtW = X.T * w
        try:
            beta = np.linalg.solve(XtW @ X, XtW @ g.alg2_per_child.values)
        except np.linalg.LinAlgError:
            return np.nan, np.nan
        diffs[cycle] = beta[3]
    pre = [diffs[c] for c in PRE if c in diffs]
    post = [v for k, v in diffs.items() if k not in PRE]
    if len(pre) < 2 or not post:
        return np.nan, np.nan
    return float(np.mean(post) - np.mean(pre)), float(pre[1] - pre[0])


def fig_null(res: pd.DataFrame) -> str:
    tx = float(res.loc[res.state == "TX", "did"].iloc[0])
    others = res[res.state != "TX"]["did"].dropna().values
    fig, ax = plt.subplots(figsize=(7.8, 4.4))
    ax.hist(others, bins=22, color=SERIES[0], alpha=0.85, zorder=3,
            label="50 placebo states")
    ax.axvline(tx, color=SERIES[1], lw=2.4, zorder=5, label="Texas (actual)")
    ax.axvline(0, color=MUTED, lw=1.2, zorder=2)
    ax.annotate(f"Texas {tx:+.4f}\np = {OUT['p_two_sided']:.3f}",
                (tx, ax.get_ylim()[1] * 0.72), (tx + 0.012, ax.get_ylim()[1] * 0.78),
                fontsize=9, color=SERIES[1], fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=SERIES[1], lw=1.4))
    ax.set_xlabel("difference-in-differences estimate")
    ax.set_ylabel("states")
    ax.legend(loc="upper left")
    return finish(fig, ax, "010_randomization_null",
                  "Texas sits inside the placebo distribution",
                  "Every state treated as the policy unit in turn; the whole "
                  "DiD re-run 51 times. The p-value is Texas's rank among the "
                  "placebos and assumes nothing about the error structure.")


def main() -> int:
    d = load()
    states = sorted(s for s in d.state_pc.dropna().unique() if isinstance(s, str))
    rows = []
    for st in states:
        did, pre = did_for_state(d, st)
        rows.append({"state": st, "did": did, "pre_trend": pre})
    res = pd.DataFrame(rows)
    res = res[res.did.notna()].reset_index(drop=True)

    tx = float(res.loc[res.state == "TX", "did"].iloc[0])
    tx_pre = float(res.loc[res.state == "TX", "pre_trend"].iloc[0])
    n = len(res)
    ge = int((res.did.abs() >= abs(tx)).sum())
    OUT["n_states_estimated"] = n
    OUT["did_texas"] = round(tx, 5)
    OUT["pre_trend_texas"] = round(tx_pre, 5)
    OUT["n_placebos_at_least_as_extreme"] = ge
    OUT["p_two_sided"] = round(ge / n, 4)
    OUT["p_floor"] = round(1 / n, 4)
    OUT["texas_abs_rank"] = int((res.did.abs() > abs(tx)).sum()) + 1
    OUT["placebo_did_sd"] = round(float(res.did.std()), 5)
    OUT["placebo_did_iqr"] = [round(float(res.did.quantile(.25)), 5),
                              round(float(res.did.quantile(.75)), 5)]
    # same test on the PRE-TREND: is Texas's pre-movement unusual?
    gep = int((res.pre_trend.abs() >= abs(tx_pre)).sum())
    OUT["p_pre_trend"] = round(gep / n, 4)

    OUT["figures"] = [fig_null(res)]
    res.sort_values("did").to_csv(
        os.path.join(FIGDIR, "010_randomization.csv"), index=False)
    with open(os.path.join(FIGDIR, "010_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(json.dumps(OUT, indent=1))
    print()
    print("most extreme placebo DiDs:")
    print(res.reindex(res.did.abs().sort_values(ascending=False).index)
             .head(8).round(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
