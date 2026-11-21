"""
Report 001 — Is the school district a stable unit of exposure?

The question this answers is a MEASUREMENT-VALIDITY question, not a substantive
one: may the program use an averaged district-year, or must it use the specific
year a student was actually enrolled?

It is deliberately split in two, because the two halves can disagree and only
the second one licenses averaging the RELATIONSHIP:

  (a) Are district poverty LEVELS/RANKS stable?  -> ICC, Spearman rho(k),
      decile transition matrices.
  (b) Is the poverty -> outcome RELATIONSHIP stable?  -> report 003.

A district that enters or leaves the panel looks exactly like instability, so
rank persistence is computed on the BALANCED panel and the churn is reported
separately rather than absorbed.
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
from analysis.style import FIGDIR, SERIES, finish, setup  # noqa: E402

setup()
OUT = {}


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    full = db.read_sql("""
        SELECT vintage, leaid, state_fips, pop_5_17, pov_5_17, pov_rate
        FROM mart.district_year
        WHERE pov_rate IS NOT NULL AND pop_5_17 > 0
    """)
    bal = db.read_sql("""
        SELECT vintage, leaid, state_fips, pop_5_17, pov_rate
        FROM mart.lea_panel_balanced
        WHERE pov_rate IS NOT NULL AND pop_5_17 > 0
    """)
    return full, bal


def churn(full: pd.DataFrame) -> pd.DataFrame:
    """District entry/exit — administrative change that mimics instability."""
    per = full.groupby("vintage")["leaid"].apply(set)
    years = sorted(per.index)
    rows = []
    for i, y in enumerate(years):
        prev = per[years[i - 1]] if i else set()
        rows.append({"vintage": y, "n": len(per[y]),
                     "entered": len(per[y] - prev) if i else np.nan,
                     "exited": len(prev - per[y]) if i else np.nan})
    d = pd.DataFrame(rows)
    ever = set().union(*per.values)
    always = set.intersection(*per.values)
    OUT["n_leaid_ever"] = len(ever)
    OUT["n_leaid_all_years"] = len(always)
    OUT["pct_leaid_persistent"] = round(100 * len(always) / len(ever), 1)
    return d


def icc(bal: pd.DataFrame) -> float:
    """Share of poverty-rate variance that is BETWEEN districts.

    Two-way decomposition: pov_rate = district effect + year effect + residual.
    The year effect is removed first, because a national recession moves every
    district together and is not evidence that districts differ.
    """
    d = bal.copy()
    d["yr_mean"] = d.groupby("vintage")["pov_rate"].transform("mean")
    d["dm"] = d["pov_rate"] - d["yr_mean"]           # year-demeaned
    grand = d["dm"].mean()
    between = d.groupby("leaid")["dm"].mean()
    n_per = d.groupby("leaid").size().mean()
    var_between = ((between - grand) ** 2).mean()
    var_within = d.groupby("leaid")["dm"].transform("mean").rsub(d["dm"]).pow(2).mean()
    OUT["var_between"] = float(var_between)
    OUT["var_within"] = float(var_within)
    OUT["mean_years_per_district"] = float(n_per)
    return float(var_between / (var_between + var_within))


def rank_persistence(bal: pd.DataFrame) -> pd.DataFrame:
    """Spearman rho between a district's poverty rank at t and at t+k."""
    w = bal.pivot(index="leaid", columns="vintage", values="pov_rate").dropna()
    years = sorted(w.columns)
    r = w.rank(axis=0)
    rows = []
    for k in range(1, len(years)):
        vals = []
        for i in range(len(years) - k):
            a, b = r[years[i]], r[years[i + k]]
            vals.append(np.corrcoef(a, b)[0, 1])
        rows.append({"lag": k, "rho_mean": float(np.mean(vals)),
                     "rho_min": float(np.min(vals)), "n_pairs": len(vals)})
    df = pd.DataFrame(rows)
    OUT["rho_lag1"] = round(df.loc[df.lag == 1, "rho_mean"].iloc[0], 4)
    for k in (5, 10, 20):
        if (df.lag == k).any():
            OUT[f"rho_lag{k}"] = round(df.loc[df.lag == k, "rho_mean"].iloc[0], 4)
    OUT[f"rho_lag_max"] = round(df.rho_mean.iloc[-1], 4)
    OUT["max_lag"] = int(df.lag.iloc[-1])
    return df


def decile_transition(bal: pd.DataFrame, k: int) -> pd.DataFrame:
    w = bal.pivot(index="leaid", columns="vintage", values="pov_rate").dropna()
    years = sorted(w.columns)
    y0, y1 = years[0], years[min(len(years) - 1, years.index(years[0]) + k)]
    if y1 == y0:
        y1 = years[-1]
    q0 = pd.qcut(w[y0], 10, labels=False, duplicates="drop")
    q1 = pd.qcut(w[y1], 10, labels=False, duplicates="drop")
    t = pd.crosstab(q0, q1, normalize="index") * 100
    OUT[f"diag_share_{y0}_{y1}"] = round(float(np.diag(t).mean()), 1)
    OUT[f"within1_share_{y0}_{y1}"] = round(float(sum(
        t.values[i, j] for i in range(t.shape[0]) for j in range(t.shape[1])
        if abs(i - j) <= 1) / t.shape[0]), 1)
    OUT["transition_years"] = [int(y0), int(y1)]
    return t


def fig_rank(df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(df.lag, df.rho_mean, color=SERIES[0], lw=2, zorder=3)
    ax.fill_between(df.lag, df.rho_min, df.rho_mean, color=SERIES[0],
                    alpha=0.15, lw=0, zorder=2)
    ax.axhline(0.9, color="#9a9a94", lw=1, ls=(0, (4, 3)), zorder=1)
    ax.text(df.lag.max(), 0.902, "ρ = 0.90", ha="right", va="bottom",
            fontsize=9, color="#52514e")
    ax.set_xlabel("lag (years)")
    ax.set_ylabel("Spearman ρ of district poverty rank")
    ax.set_ylim(0.5, 1.005)
    ax.set_xlim(0, df.lag.max())
    return finish(fig, ax, "001_rank_persistence",
                  "District poverty ranks persist for decades",
                  "Balanced panel of districts present in every SAIPE vintage, "
                  "1995–2024. Band spans the worst observed pair at each lag.")


def fig_transition(t: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(6.0, 5.2))
    im = ax.imshow(t.values, cmap="Blues", vmin=0, vmax=max(60, t.values.max()))
    ax.set_xlabel(f"poverty decile in {OUT['transition_years'][1]}")
    ax.set_ylabel(f"poverty decile in {OUT['transition_years'][0]}")
    ax.set_xticks(range(t.shape[1])); ax.set_xticklabels(range(1, t.shape[1] + 1))
    ax.set_yticks(range(t.shape[0])); ax.set_yticklabels(range(1, t.shape[0] + 1))
    for i in range(t.shape[0]):
        for j in range(t.shape[1]):
            v = t.values[i, j]
            if v >= 5:
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8,
                        color="#ffffff" if v > 35 else "#0b0b0b")
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("% of origin decile", fontsize=9)
    cb.outline.set_visible(False)
    return finish(fig, ax, "001_decile_transition",
                  "Where a district's poverty decile goes over three decades",
                  "Row-normalised: each row sums to 100%. Diagonal = stayed put.",
                  grid=False)


def fig_churn(d: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(d.vintage, d.n, color=SERIES[0], lw=2, zorder=3)
    ax.set_xlabel("SAIPE vintage")
    ax.set_ylabel("districts reported")
    ax.set_ylim(0, d.n.max() * 1.12)
    return finish(fig, ax, "001_district_count",
                  "The district universe shrinks steadily — consolidation, not noise",
                  f"{OUT['n_leaid_ever']:,} LEAIDs appear at least once; "
                  f"{OUT['n_leaid_all_years']:,} ({OUT['pct_leaid_persistent']}%) "
                  f"appear in every vintage.")


def main() -> int:
    full, bal = load()
    OUT["n_rows_full"] = len(full)
    OUT["n_rows_balanced"] = len(bal)
    OUT["vintages"] = [int(full.vintage.min()), int(full.vintage.max())]
    OUT["n_vintages"] = int(full.vintage.nunique())

    ch = churn(full)
    OUT["icc"] = round(icc(bal), 4)
    rp = rank_persistence(bal)
    tr = decile_transition(bal, 30)

    figs = [fig_rank(rp), fig_transition(tr), fig_churn(ch)]
    OUT["figures"] = figs

    ch.to_csv(os.path.join(FIGDIR, "001_district_count.csv"), index=False)
    rp.to_csv(os.path.join(FIGDIR, "001_rank_persistence.csv"), index=False)
    tr.round(1).to_csv(os.path.join(FIGDIR, "001_decile_transition.csv"))

    with open(os.path.join(FIGDIR, "001_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(json.dumps(OUT, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
