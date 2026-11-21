"""
Report 020 — What would a dual-credit acceptance threshold actually buy?

Report 017 found the actionable result in this programme: a dual C predicts a
57% failure rate in the next UTSA course, and AP already applies a threshold (a
3 confers credit, a 2 does not) while dual credit applies none. This report
prices that decision instead of merely recommending it.

A CREDIT RULE IS A CLASSIFIER. Accepting a dual award predicts the student is
ready for the next course. So each candidate rule has two costs, and they trade
against each other:

  FALSE POSITIVE   a student is granted credit, is placed into the sequel, and
                   fails it. Cost: a failed course, tuition, and often attrition.
  FALSE NEGATIVE   a student is denied credit and made to repeat a course they
                   would have passed. Cost: a wasted term and tuition, plus the
                   equity cost of doing it disproportionately to the students
                   report 013 showed are routed to dual credit by poverty.

WHY THIS IS COMPUTABLE RATHER THAN SPECULATIVE. The observed data IS the
accept-everything regime: every student here was granted credit and sat the
sequel, so their outcome under acceptance is observed. Any STRICTER rule is
therefore evaluable by subsetting -- no extrapolation and no model. What is NOT
observed is what a denied student would have done in the course they were made
to repeat instead; that limit is stated in the report and not modelled away.

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
import gateway_link as gl
from dual_grade_signal import frame

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402

setup()
OUT: dict = {}

#: candidate acceptance rules, loosest last
RULES = [("Dual A only", ["A"]),
         ("Dual A or B", ["A", "B"]),
         ("Accept all (current)", ["A", "B", "C"])]


def evaluate(d: pd.DataFrame, accept: list[str]) -> dict:
    """Score one acceptance rule against the observed accept-everything data."""
    dual = d[d.group.isin(["Dual A", "Dual B", "Dual C"])].copy()
    dual["grade"] = dual.group.str[-1]
    granted = dual[dual.grade.isin(accept)]
    denied = dual[~dual.grade.isin(accept)]

    prevented = int(denied.dfw.sum())            # denied, would have failed
    unnecessary = int((1 - denied.dfw).sum())    # denied, would have passed
    return {
        "rule": " / ".join(accept),
        "n_granted": int(len(granted)),
        "pct_granted": round(100 * len(granted) / len(dual), 1),
        "pct_dfw_granted": round(100 * granted.dfw.mean(), 1) if len(granted) else None,
        "n_denied": int(len(denied)),
        "failures_prevented": prevented,
        "unnecessary_denials": unnecessary,
        "prevented_per_denial": (round(prevented / unnecessary, 2)
                                 if unnecessary else None),
    }


def fig(res: pd.DataFrame, marginal: pd.DataFrame, ap_rate: float) -> str:
    labels = [r for r, _ in RULES]
    x = np.arange(len(labels))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.0, 4.8))

    ax1.bar(x, res.pct_dfw_granted, 0.46, color=SERIES[1], zorder=3)
    ax1.axhline(ap_rate, color=SERIES[0], lw=1.6, ls="--", zorder=4)
    ax1.text(-0.45, ap_rate + 1.2, f"AP credit {ap_rate:.0f}%", ha="left",
             fontsize=8.5, color=SERIES[0])
    for i, v in enumerate(res.pct_dfw_granted):
        ax1.text(i, v + 0.9, f"{v:.0f}%", ha="center", fontsize=10,
                 color=SERIES[1], fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=8.5)
    ax1.set_ylabel("% D/F/W among students\ngranted credit")
    ax1.set_ylim(0, max(res.pct_dfw_granted) * 1.28)

    # the MARGINAL panel is the decision-relevant one: one tier at a time
    xm = np.arange(len(marginal))
    w = 0.34
    ax2.bar(xm - w / 2, marginal.failures_prevented, w * 0.92, color=SERIES[2],
            label="failures prevented", zorder=3)
    ax2.bar(xm + w / 2, marginal.unnecessary_denials, w * 0.92, color=MUTED,
            label="passes needlessly denied", zorder=3)
    for i, r in marginal.iterrows():
        ax2.text(i - w / 2, r.failures_prevented + 10, f"{int(r.failures_prevented):,}",
                 ha="center", fontsize=9, color=SERIES[2], fontweight="bold")
        ax2.text(i + w / 2, r.unnecessary_denials + 10,
                 f"{int(r.unnecessary_denials):,}", ha="center", fontsize=9,
                 color=INK2)
        good = r.ratio >= 1
        ax2.text(i, -62, f"{r.ratio:.2f} prevented\nper denial",
                 ha="center", fontsize=9,
                 color=(SERIES[2] if good else SERIES[1]),
                 fontweight="bold")
    ax2.set_xticks(xm)
    ax2.set_xticklabels(marginal.step, fontsize=9)
    ax2.set_xlim(-0.6, len(marginal) - 0.4)
    ax2.set_ylim(-120, max(marginal.unnecessary_denials) * 1.22)
    ax2.set_ylabel("students")
    ax2.legend(loc="upper left", fontsize=8.5)

    fig.subplots_adjust(top=0.84, wspace=0.30, bottom=0.18)
    return finish(fig, ax1, "020_credit_threshold",
                  "The threshold belongs between C and B — not between B and A",
                  "Right panel is MARGINAL: each step priced on its own, not "
                  "cumulatively. Evaluated against the observed "
                  "accept-everything regime, so no extrapolation is involved — "
                  "every student here was granted credit and sat the sequel. "
                  "What a DENIED student would have done in the repeated course "
                  "is not observed; see the report.")


def main() -> int:
    d = frame()
    ap_rate = 100 * float(d[d.group == "AP credit"].dfw.mean())
    OUT["ap_dfw"] = round(ap_rate, 2)

    rows = []
    for label, accept in RULES:
        r = evaluate(d, accept)
        r["rule_label"] = label
        rows.append(r)
    res = pd.DataFrame(rows)
    OUT["rules"] = res.to_dict("records")

    # THE DECISION-RELEVANT NUMBERS ARE MARGINAL, NOT CUMULATIVE. The columns
    # above are cumulative against the current accept-everything rule, so the
    # "Dual A only" row bundles the effect of dropping B with that of dropping
    # C. What a decision-maker faces is one tier at a time.
    marg = []
    prev = {"failures_prevented": 0, "unnecessary_denials": 0}
    for lab in ["Dual A or B", "Dual A only"]:      # tightening, one tier at a time
        cur = res.set_index("rule_label").loc[lab]
        dp = int(cur.failures_prevented) - prev["failures_prevented"]
        dd = int(cur.unnecessary_denials) - prev["unnecessary_denials"]
        marg.append({"step": ("stop accepting C" if lab == "Dual A or B"
                              else "also stop accepting B"),
                     "failures_prevented": dp, "unnecessary_denials": dd,
                     "ratio": round(dp / dd, 2) if dd else None})
        prev = {"failures_prevented": int(cur.failures_prevented),
                "unnecessary_denials": int(cur.unnecessary_denials)}
    marginal = pd.DataFrame(marg)
    OUT["marginal"] = marginal.to_dict("records")

    OUT["figures"] = [fig(res, marginal, ap_rate)]
    # `publish` enforces its n < 10 floor on a column named n_students; here a
    # cell is "students granted credit under this rule".
    pub = res[["rule_label", "n_granted", "pct_dfw_granted", "n_denied",
               "failures_prevented", "unnecessary_denials"]].rename(
        columns={"n_granted": "n_students"})
    gl.publish(pub, "utsa_credit_threshold", ["rule_label"])
    res.to_csv(os.path.join(FIGDIR, "020_credit_threshold.csv"), index=False)
    marginal.to_csv(os.path.join(FIGDIR, "020_marginal.csv"), index=False)
    with open(os.path.join(FIGDIR, "020_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(f"AP credit baseline DFW: {ap_rate:.1f}%\n")
    print(res.to_string(index=False))
    print("\n--- MARGINAL effect of each successive tightening ---")
    print(marginal.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
