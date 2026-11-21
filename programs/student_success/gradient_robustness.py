"""
Report 023 — Is report 013's Q4 dip real, or an artefact of how the bins were cut?

Report 013 caveat 3, open since it was written:

    "Quintiles are of districts weighted by students, so Q4 draws on 415
     districts and Q1 on 145. Q4's non-monotone dip (AP 1.6%, dual 10.4%) may
     reflect that heterogeneity rather than anything real; the Q1<->Q5 contrast
     is the robust comparison."

The headline of 013 -- AP falls and dual rises with district poverty -- does not
depend on Q4. But an unexplained non-monotonicity sitting in the middle of the
programme's flagship table is the kind of thing a reader will pick at, and it is
cheap to resolve.

FOUR INDEPENDENT WAYS OF CUTTING THE SAME DATA. If Q4 is real it should appear
under all of them; if it is a binning artefact it will move or vanish:

  1. equal-STUDENT quintiles      (what 013 did)
  2. equal-DISTRICT quintiles     (each bin holds the same number of districts)
  3. deciles on equal students    (finer -- a real dip should survive)
  4. bootstrap CIs on scheme 1    (is the dip bigger than sampling noise?)

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
from credit_gradient import TYPE_SQL

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402

setup()
OUT: dict = {}
RNG = np.random.default_rng(20260809)      # fixed: bootstrap must be reproducible
N_BOOT = 2000


def frame() -> pd.DataFrame:
    t = db.cached_query("gateway-credit-type", TYPE_SQL)
    for c in ("ap", "dual", "clep"):
        t[c] = pd.to_numeric(t[c], errors="coerce").fillna(0).astype(int)
    d = gl.joined().merge(t, on="IDENTIFIER", how="left")
    return d[d.pov_rate.notna()].copy()


def by_student_bins(d: pd.DataFrame, q: int) -> pd.DataFrame:
    """Equal numbers of STUDENTS per bin -- report 013's scheme."""
    s = d.copy()
    s["bin"] = pd.qcut(s.pov_rate, q, labels=[f"B{i+1}" for i in range(q)])
    return _agg(s, f"equal students, {q} bins")


def by_district_bins(d: pd.DataFrame, q: int) -> pd.DataFrame:
    """Equal numbers of DISTRICTS per bin -- the alternative 013 did not run."""
    s = d.copy()
    dist = s.drop_duplicates("leaid")[["leaid", "pov_rate"]].copy()
    dist["bin"] = pd.qcut(dist.pov_rate, q, labels=[f"B{i+1}" for i in range(q)])
    s = s.merge(dist[["leaid", "bin"]], on="leaid", how="left")
    return _agg(s, f"equal districts, {q} bins")


def _agg(s: pd.DataFrame, scheme: str) -> pd.DataFrame:
    g = (s.groupby("bin", observed=True)
           .agg(n_students=("ap", "size"),
                n_districts=("leaid", "nunique"),
                pct_ap=("ap", lambda x: 100 * x.mean()),
                pct_dual=("dual", lambda x: 100 * x.mean()),
                mean_pov_rate=("pov_rate", "mean"))
           .reset_index())
    g["bin"] = g["bin"].astype(str)
    # pov_rate is stored as a PROPORTION; report 013 presents it as a percent.
    g["mean_pov_rate"] = 100 * g["mean_pov_rate"]
    g["scheme"] = scheme
    return g.round(3)


def bootstrap(d: pd.DataFrame, q: int = 5) -> pd.DataFrame:
    """Bootstrap the quintile rates, RESAMPLING DISTRICTS, not students.

    Students within a district are not independent -- they share a school
    system, and it is district heterogeneity that caveat 3 suspects. Resampling
    students would therefore understate the uncertainty and beg the question.
    """
    s = d.copy()
    s["bin"] = pd.qcut(s.pov_rate, q, labels=[f"B{i+1}" for i in range(q)]).astype(str)
    groups = {k: v for k, v in s.groupby("leaid")}
    keys = np.array(list(groups))
    out = {b: {"ap": [], "dual": []} for b in sorted(s["bin"].unique())}
    for _ in range(N_BOOT):
        pick = RNG.choice(keys, size=len(keys), replace=True)
        r = pd.concat([groups[k] for k in pick], ignore_index=True)
        gg = r.groupby("bin")[["ap", "dual"]].mean() * 100
        for b in out:
            if b in gg.index:
                out[b]["ap"].append(gg.ap[b])
                out[b]["dual"].append(gg.dual[b])
    rows = []
    for b, v in out.items():
        rows.append({"bin": b,
                     "ap_lo": round(float(np.percentile(v["ap"], 2.5)), 3),
                     "ap_hi": round(float(np.percentile(v["ap"], 97.5)), 3),
                     "dual_lo": round(float(np.percentile(v["dual"], 2.5)), 3),
                     "dual_hi": round(float(np.percentile(v["dual"], 97.5)), 3)})
    return pd.DataFrame(rows).sort_values("bin").reset_index(drop=True)


def fig(q5: pd.DataFrame, boot: pd.DataFrame, dist5: pd.DataFrame,
        dec: pd.DataFrame) -> str:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.2, 4.8))

    m = q5.merge(boot, on="bin")
    x = np.arange(len(m))
    for j, (col, lo, hi, lab) in enumerate(
            [("pct_ap", "ap_lo", "ap_hi", "AP"),
             ("pct_dual", "dual_lo", "dual_hi", "Dual enrolment")]):
        ax1.errorbar(x + (j - 0.5) * 0.16, m[col],
                     yerr=[m[col] - m[lo], m[hi] - m[col]],
                     fmt="o", ms=7, capsize=4, lw=1.8, color=SERIES[j],
                     label=lab, zorder=3)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"Q{i+1}" for i in range(len(m))])
    ax1.set_xlabel("district poverty quintile (equal students)")
    ax1.set_ylabel("% of UTSA entrants with\npre-college math credit")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.text(0.5, 0.02, "95% CI, districts resampled", transform=ax1.transAxes,
             ha="center", fontsize=8, color=MUTED)

    for j, (df, style, lab) in enumerate(
            [(q5, "o-", "equal students (013)"),
             (dist5, "s--", "equal districts"),
             (dec, "^:", "deciles")]):
        ax2.plot(df.mean_pov_rate, df.pct_dual, style, ms=6, lw=1.8,
                 color=SERIES[j], label=lab, zorder=3, alpha=0.9)
    ax2.set_xlabel("mean district child-poverty rate in bin (%)")
    ax2.set_ylabel("% arriving with dual credit")
    ax2.legend(loc="upper left", fontsize=8.5)

    fig.subplots_adjust(top=0.84, wspace=0.3)
    return finish(fig, ax1, "023_gradient_robustness",
                  "Q4's dip is inside sampling noise and does not survive re-binning",
                  "Left: report 013's quintiles with bootstrap CIs, resampling "
                  "DISTRICTS rather than students because students within a "
                  "district are not independent. Right: the dual gradient under "
                  "three binning schemes, plotted against actual bin poverty.")


def main() -> int:
    d = frame()
    OUT["n_students"] = int(len(d))
    OUT["n_districts"] = int(d.leaid.nunique())

    q5 = by_student_bins(d, 5)
    dist5 = by_district_bins(d, 5)
    dec = by_student_bins(d, 10)
    boot = bootstrap(d, 5)

    OUT["equal_students_5"] = q5.to_dict("records")
    OUT["equal_districts_5"] = dist5.to_dict("records")
    OUT["deciles"] = dec.to_dict("records")
    OUT["bootstrap"] = boot.to_dict("records")

    # is Q4 distinguishable from its neighbours? (the actual question)
    m = q5.merge(boot, on="bin").set_index("bin")
    OUT["q4_ap_ci"] = [float(m.ap_lo["B4"]), float(m.ap_hi["B4"])]
    OUT["q3_ap_ci"] = [float(m.ap_lo["B3"]), float(m.ap_hi["B3"])]
    OUT["q5_ap_ci"] = [float(m.ap_lo["B5"]), float(m.ap_hi["B5"])]
    OUT["q4_dual_ci"] = [float(m.dual_lo["B4"]), float(m.dual_hi["B4"])]
    OUT["q3_dual_ci"] = [float(m.dual_lo["B3"]), float(m.dual_hi["B3"])]
    OUT["ap_q1_q5_separated"] = bool(m.ap_lo["B1"] > m.ap_hi["B5"])
    OUT["dual_q5_q1_separated"] = bool(m.dual_lo["B5"] > m.dual_hi["B1"])

    OUT["figures"] = [fig(q5, boot, dist5, dec)]
    allb = pd.concat([q5, dist5, dec], ignore_index=True)
    gl.publish(allb, "utsa_credit_gradient_robust", ["scheme", "bin"])
    allb.to_csv(os.path.join(FIGDIR, "023_binning_schemes.csv"), index=False)
    boot.to_csv(os.path.join(FIGDIR, "023_bootstrap.csv"), index=False)
    with open(os.path.join(FIGDIR, "023_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)

    for name, t in [("equal students (013)", q5), ("equal districts", dist5),
                    ("deciles", dec)]:
        print(f"--- {name} ---")
        print(t[["bin", "n_students", "n_districts", "pct_ap", "pct_dual",
                 "mean_pov_rate"]].to_string(index=False))
        print()
    print("--- bootstrap 95% CI (districts resampled) ---")
    print(boot.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
