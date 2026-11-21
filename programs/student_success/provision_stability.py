"""
Report 022 — Is school course provision stable enough to use one CRDC cycle?

Report 021 attached CRDC 2017-18 provision to students who entered high school
2005-2015, and defended it in caveat 1 with an ASSUMPTION:

    "defensible only because AP provision is a slow-moving structural feature of
     a school, and that is an assumption, not a finding."

This report tests that assumption instead of resting on it. If provision turns
out to be volatile, report 021's exposure measure is largely noise and its
findings weaken; if it is stable, the caveat downgrades from serious to minor.

WHAT CAN AND CANNOT BE TESTED. `stg.crdc_alg2_panel` holds all five cycles but
only for ALGEBRA II -- it does not carry `apmath`. So this measures the stability
of Algebra II provision and uses it as a proxy for the stability of course
provision generally. That is a real limitation and the report says so: it does
not prove AP provision is stable, it shows that a comparable course offering is.

THE FRAME TRAP, and why a naive answer is wrong. All five cycles are universe
collections, yet the set of schools changes between them (openings,
closings, changed identifiers). A school absent from a cycle has not "stopped
offering Algebra II" -- it is not in that cycle's file. Comparing cycles
without restricting to schools PRESENT IN BOTH would score frame changes as
provision changes and manufacture instability. Every pairwise statistic here
is computed on the intersection.

TWO FINDINGS THAT CHANGED HOW THIS IS MEASURED, both discovered while running it:

  1. THE BINARY "OFFERS ALGEBRA II" IS DEGENERATE and must NOT be used. From
     2013-14 onward only 0.01-0.41% of schools record zero, so cross-cycle
     agreement on it is 99.9-100% TRIVIALLY. That is not evidence of stability;
     it is a constant. Cohen's kappa is ~0 (or undefined) throughout, which is
     the tell. The INTENSITY -- how many students are enrolled -- is what varies
     and is what this report measures.

  2. 2011-12's ZEROS ARE SUSPECT: 26.25% of its schools record zero Algebra II
     against 0.01-0.41% in every later cycle. A 26-point fall in non-provision
     between two cycles is not a real-world change. 2011-12 is already known to
     use a different column vocabulary and to mark missing values with BLANKS
     rather than reserve codes (see report 007 section 4 and PROGRESS), so these
     are almost certainly miscoded missing values being read as genuine zeros.
     Reported as a data-quality flag; 2011-12 rows are kept but never used for a
     binary statistic.

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
CYCLES = ["2011-12", "2013-14", "2015-16", "2017-18", "2021-22"]


def panel() -> pd.DataFrame:
    with gdb.connect() as g:
        p = pd.read_sql(
            "SELECT combokey AS ncessch, cycle, alg2_tot, is_universe "
            "FROM stg.crdc_alg2_panel WHERE alg2_tot IS NOT NULL", g)
    return p


def matched_schools() -> set:
    """The schools report 021 actually used -- UTSA students' own high schools."""
    with gdb.connect() as g:
        xw = pd.read_sql("SELECT DISTINCT ncessch FROM core.hs_crosswalk "
                         "WHERE ncessch IS NOT NULL", g)
    return set(xw.ncessch)


def pairwise(p: pd.DataFrame, restrict: set | None = None) -> pd.DataFrame:
    """Cross-cycle agreement, computed on schools PRESENT IN BOTH cycles."""
    w = p.pivot_table(index="ncessch", columns="cycle", values="alg2_tot",
                      aggfunc="first")
    if restrict is not None:
        w = w[w.index.isin(restrict)]
    rows = []
    for i, a in enumerate(CYCLES):
        for b in CYCLES[i + 1:]:
            if a not in w.columns or b not in w.columns:
                continue
            s = w[[a, b]].dropna()          # <- the intersection; see docstring
            if len(s) < 50:
                continue
            oa, ob = (s[a] > 0), (s[b] > 0)
            agree = float((oa == ob).mean())
            # Cohen's kappa on the binary. Retained ONLY to demonstrate that the
            # binary is degenerate -- kappa ~ 0 alongside 99%+ agreement means
            # the agreement is chance under a near-constant, not stability.
            pe = float(oa.mean() * ob.mean() + (1 - oa.mean()) * (1 - ob.mean()))
            kappa = (agree - pe) / (1 - pe) if pe < 1 else np.nan
            rows.append({
                "cycle_a": a, "cycle_b": b, "gap_years": _gap(a, b),
                "n_schools": int(len(s)),
                # the informative statistics: intensity, not the binary
                "spearman_count": round(float(s[a].corr(s[b], method="spearman")), 3),
                "pearson_log": round(float(np.log1p(s[a]).corr(np.log1p(s[b]))), 3),
                "pct_agree_offers_UNINFORMATIVE": round(100 * agree, 1),
                "kappa": round(float(kappa), 3),
            })
    return pd.DataFrame(rows)


def _gap(a: str, b: str) -> int:
    return int(b[:4]) - int(a[:4])


def quartile_persistence(p: pd.DataFrame, a: str, b: str,
                         restrict: set | None = None) -> pd.DataFrame:
    w = p.pivot_table(index="ncessch", columns="cycle", values="alg2_tot",
                      aggfunc="first")
    if restrict is not None:
        w = w[w.index.isin(restrict)]
    s = w[[a, b]].dropna()
    s = s[(s[a] > 0) & (s[b] > 0)]
    qa = pd.qcut(s[a].rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
    qb = pd.qcut(s[b].rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
    t = pd.crosstab(qa, qb, normalize="index").round(3) * 100
    t.index.name = f"{a} quartile"
    return t


def fig(nat: pd.DataFrame, utsa: pd.DataFrame) -> str:
    """Rank correlation of Algebra II INTENSITY, by how far apart the cycles are.

    Deliberately NOT the binary agreement rate: that is 99-100% because almost
    every school offers Algebra II, which measures the constant and not the
    stability.
    """
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    # scatter, NOT a line: several cycle pairs share the same gap, so joining
    # them would draw vertical jumps that mean nothing.
    for j, (df, lab) in enumerate([(nat, "all CRDC schools"),
                                   (utsa, "UTSA students' high schools")]):
        ax.scatter(df.gap_years + (j - 0.5) * 0.14, df.spearman_count, s=62,
                   color=SERIES[j], label=lab, zorder=3)
        m = df.groupby("gap_years").spearman_count.mean()
        ax.plot(m.index + (j - 0.5) * 0.14, m.values, lw=1.4, alpha=0.55,
                color=SERIES[j], zorder=2)
    ax.axhline(0.9, color=MUTED, lw=1, ls=":", zorder=1)
    ax.text(10.3, 0.902, "0.90", fontsize=8, color=MUTED, va="bottom", ha="right")
    ax.set_xlabel("years between CRDC cycles")
    ax.set_ylabel("Spearman correlation of school\nAlgebra II enrolment")
    ax.set_ylim(0.78, 1.0)
    ax.set_xticks([2, 4, 6, 8, 10])
    ax.legend(loc="lower left")
    return finish(fig, ax, "022_provision_stability",
                  "How much Algebra II a school teaches barely moves over a decade",
                  "Each point is one pair of CRDC cycles, computed only on "
                  "schools PRESENT IN BOTH — 2011-12 and 2013-14 are samples, so "
                  "a school missing from one is unsurveyed, not un-offering. "
                  "The BINARY 'offers Algebra II' is not plotted: it is ~100% in "
                  "every cycle and so carries no information. Algebra II stands "
                  "proxy for provision generally — the panel has no AP maths.")


def main() -> int:
    p = panel()
    sel = matched_schools()
    OUT["n_school_cycles"] = int(len(p))

    nat = pairwise(p)
    utsa = pairwise(p, restrict=sel)
    OUT["pairwise_all"] = nat.to_dict("records")
    OUT["pairwise_utsa"] = utsa.to_dict("records")

    # the degeneracy diagnostic -- why the binary is not used
    zero = (p.groupby("cycle").alg2_tot
              .agg(n="size", pct_zero=lambda x: round(100 * float((x == 0).mean()), 2))
              .reset_index())
    OUT["zero_rate_by_cycle"] = zero.to_dict("records")
    zero.to_csv(os.path.join(FIGDIR, "022_zero_rate.csv"), index=False)

    # the decade-apart pair is the hardest test of the slow-moving assumption
    far = nat[(nat.cycle_a == "2011-12") & (nat.cycle_b == "2021-22")]
    if len(far):
        OUT["decade_spearman"] = float(far.spearman_count.iloc[0])
        OUT["decade_pearson_log"] = float(far.pearson_log.iloc[0])
    OUT["min_spearman_utsa"] = round(float(utsa.spearman_count.min()), 3)
    OUT["max_spearman_utsa"] = round(float(utsa.spearman_count.max()), 3)

    qt = quartile_persistence(p, "2011-12", "2021-22")
    OUT["quartile_2011_2021"] = qt.to_dict()

    OUT["figures"] = [fig(nat, utsa)]
    pub = utsa.assign(n_students=utsa.n_schools)   # publish floor wants this name
    gl.publish(pub, "crdc_provision_stability", ["cycle_a", "cycle_b"])
    nat.to_csv(os.path.join(FIGDIR, "022_pairwise_all.csv"), index=False)
    utsa.to_csv(os.path.join(FIGDIR, "022_pairwise_utsa.csv"), index=False)
    qt.to_csv(os.path.join(FIGDIR, "022_quartile_transition.csv"))
    with open(os.path.join(FIGDIR, "022_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)

    print("--- all CRDC schools ---")
    print(nat.to_string(index=False))
    print("\n--- UTSA students' high schools ---")
    print(utsa.to_string(index=False))
    print("\n--- quartile transition 2011-12 -> 2021-22 (row %) ---")
    print(qt.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
