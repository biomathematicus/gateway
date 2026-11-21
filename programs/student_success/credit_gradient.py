"""
Report 013 — how pre-college mathematics credit is delivered, by district poverty.

Processes student records LOCALLY and publishes AGGREGATE CELLS ONLY
(>= 10 students each) to GATEWAY, per the PI's governance instruction.

THE RESULT. Total pre-college math credit RISES with district poverty, which
looks wrong until it is decomposed. It is two opposite gradients:

    AP   collapses      5.0% -> 1.1%   as district poverty rises
    DUAL climbs         5.0% -> 17.5%

Aggregating them hides both. And this is not positive selection into UTSA:
SAT/ACT mathematics falls monotonically across the same quintiles (586 -> 523),
so these are lower-scoring students holding MORE credit — of a different kind.
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

setup()
OUT: dict = {}

TYPE_SQL = """
SELECT IDENTIFIER,
  MAX(CASE WHEN MAT1073_AP_GRDE IS NOT NULL OR MAT1093_AP_GRDE IS NOT NULL
            OR MAT1214_AP_GRDE IS NOT NULL OR MAT1224_AP_GRDE IS NOT NULL
           THEN 1 ELSE 0 END) AS ap,
  MAX(CASE WHEN MAT1073_DUAL_GRDE IS NOT NULL OR MAT1093_DUAL_GRDE IS NOT NULL
            OR MAT1214_DUAL_GRDE IS NOT NULL OR MAT1224_DUAL_GRDE IS NOT NULL
           THEN 1 ELSE 0 END) AS dual,
  MAX(CASE WHEN MAT1073_CLEP_GRDE IS NOT NULL OR MAT1093_CLEP_GRDE IS NOT NULL
            OR MAT1214_CLEP_GRDE IS NOT NULL OR MAT1224_CLEP_GRDE IS NOT NULL
           THEN 1 ELSE 0 END) AS clep
FROM OIR2 GROUP BY IDENTIFIER
"""


def frame() -> pd.DataFrame:
    t = db.cached_query("gateway-credit-type", TYPE_SQL)
    for c in ("ap", "dual", "clep"):
        t[c] = pd.to_numeric(t[c], errors="coerce").fillna(0).astype(int)
    d = gl.joined().merge(t, on="IDENTIFIER", how="left")
    return d[d.pov_rate.notna()].copy()


def cells(s: pd.DataFrame) -> pd.DataFrame:
    s = s.copy()
    s["pov_quintile"] = pd.qcut(
        s.pov_rate, 5, labels=["Q1 lowest", "Q2", "Q3", "Q4", "Q5 highest"])
    g = s.groupby("pov_quintile", observed=True).agg(
        n_students=("ap", "size"),
        pct_ap=("ap", lambda x: 100 * x.mean()),
        pct_dual=("dual", lambda x: 100 * x.mean()),
        pct_clep=("clep", lambda x: 100 * x.mean()),
        pct_any=("any_math_credit", lambda x: 100 * x.mean()),
        mean_satact_math=("satact_math", "mean"),
        mean_pov_rate=("pov_rate", "mean"),
        n_districts=("leaid", "nunique"),
    ).reset_index()
    g["pov_quintile"] = g["pov_quintile"].astype(str)
    return g.round(3)


def fig(g: pd.DataFrame) -> str:
    x = np.arange(len(g))
    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    w = 0.36
    ax.bar(x - w / 2, g.pct_ap, w * 0.92, color=SERIES[0], label="AP", zorder=3)
    ax.bar(x + w / 2, g.pct_dual, w * 0.92, color=SERIES[1],
           label="Dual enrolment", zorder=3)
    for i, (a, d) in enumerate(zip(g.pct_ap, g.pct_dual)):
        ax.text(i - w / 2, a + 0.4, f"{a:.1f}", ha="center", fontsize=9,
                color=SERIES[0], fontweight="bold")
        ax.text(i + w / 2, d + 0.4, f"{d:.1f}", ha="center", fontsize=9,
                color=SERIES[1], fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(g.pov_quintile)
    ax.set_xlabel("district child-poverty quintile (SAIPE, at high-school entry)")
    ax.set_ylabel("% of UTSA entrants with\npre-college math credit")
    ax.legend(loc="upper left")
    return finish(fig, ax, "013_credit_type_gradient",
                  "AP collapses and dual enrolment climbs as district poverty rises",
                  "UTSA entrants with any pre-college credit for MAT 1073/1093/"
                  "1214/1224. Aggregating the two hides both gradients. "
                  "SAT/ACT mathematics falls 586→523 across the same quintiles, "
                  "so this is not positive selection.")


def main() -> int:
    s = frame()
    g = cells(s)
    OUT["n_students_with_district"] = int(len(s))
    OUT["ap_q1"] = float(g.pct_ap.iloc[0])
    OUT["ap_q5"] = float(g.pct_ap.iloc[-1])
    OUT["dual_q1"] = float(g.pct_dual.iloc[0])
    OUT["dual_q5"] = float(g.pct_dual.iloc[-1])
    OUT["ap_ratio_q1_q5"] = round(float(g.pct_ap.iloc[0] / g.pct_ap.iloc[-1]), 2)
    OUT["dual_ratio_q5_q1"] = round(float(g.pct_dual.iloc[-1] / g.pct_dual.iloc[0]), 2)
    OUT["satact_q1"] = float(g.mean_satact_math.iloc[0])
    OUT["satact_q5"] = float(g.mean_satact_math.iloc[-1])
    OUT["figures"] = [fig(g)]

    gl.publish(g, "utsa_credit_by_poverty", ["pov_quintile"])
    g.to_csv(os.path.join(FIGDIR, "013_credit_gradient.csv"), index=False)
    with open(os.path.join(FIGDIR, "013_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(g.to_string(index=False))
    print()
    print(json.dumps(OUT, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
