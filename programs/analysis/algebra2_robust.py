"""
Report 024 — S11: the robustness report 003 said had to be run before publishing.

Report 003 caveat 2, written when 003 was written and open ever since:

    "Population-weighted OLS lets large districts dominate; an unweighted fit
     and a district-fixed-effects specification should both be run before this
     is published. Not yet done."

This runs them, and adds a third thing 003 did not anticipate: state-CLUSTERED
standard errors. Report 007 section 7 established that districts within a state
are correlated and that naive SEs are roughly 1.6x too narrow, so 003's z = 0.20
stability test is computed against an SE that is too small.

THREE SPECIFICATIONS, ANSWERING TWO DIFFERENT QUESTIONS.

  1. WEIGHTED OLS    (003's) -- between-district, large districts dominate
  2. UNWEIGHTED OLS           -- between-district, every district counts once
  3. DISTRICT FIXED EFFECTS   -- WITHIN-district: when a district's own poverty
                                 moves, does its Algebra II provision move?

Specifications 1-2 and specification 3 are NOT competing estimates of one
parameter. The cross-sectional slope says "districts with more poverty offer
less Algebra II", which is mostly a statement about which districts are poor.
The fixed-effects slope removes every time-invariant district characteristic and
asks a causal-flavoured question about change. They can differ by a lot without
either being wrong; the report says which one answers which question.

FIXED EFFECTS USES THE 5-CYCLE PANEL, NOT 003's TWO CYCLES -- within-district
identification needs as many periods as possible. **2011-12 IS EXCLUDED**:
report 022 found 26.25% of its schools record zero Algebra II against 0.01-0.41%
in every later cycle, anomalous explicit zeros of unverified provenance, and a
spurious zero would enter the within-district variance as a huge false swing.
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
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402
from gateway import db  # noqa: E402

setup()
OUT: dict = {}
DROP_CYCLE = "2011-12"      # report 022: anomalous explicit zeros, untrustworthy

#: Minimum children 5-17 for a district to enter the regressions.
#:
#: WHY THIS EXISTS, and why it is on the DENOMINATOR rather than the outcome.
#: `alg2_per_child` is a ratio whose denominator comes from SAIPE and whose
#: numerator comes from CRDC. In very small districts the two are mismatched --
#: seven districts in 2017-18 record MORE Algebra II enrollees than children
#: aged 5-17 (max 31.3, median district size 35 children), which is impossible
#: and reflects a school serving a wider area than its LEA. Unfiltered, those
#: seven districts INVERT the unweighted slope: +0.030 instead of -0.052.
#:
#: Filtering the outcome (clipping the ratio) would condition on the dependent
#: variable. Filtering `pop_5_17` conditions on a pre-treatment characteristic
#: instead. At >= 200 the maximum ratio falls to 0.68 -- physically plausible --
#: and the weighted and unweighted slopes agree to within 0.003. The full
#: sensitivity ladder is reported rather than hidden behind this constant.
MIN_POP = 200
POP_LADDER = [0, 50, 100, 200, 500, 1000]


def load() -> pd.DataFrame:
    with db.connect() as g:
        d = pd.read_sql("""
            SELECT cycle, leaid, state_pc, pop_5_17, pov_rate, alg2_per_child
            FROM mart.alg2_panel
            WHERE alg2_per_child IS NOT NULL AND pov_rate IS NOT NULL
              AND pop_5_17 > 0
        """, g)
    return d


def fit(x, y, w=None, cluster=None):
    """(W)LS slope, optionally cluster-robust. Returns slope, se, n, n_clusters.

    Weighted least squares uses RAW weights throughout -- normalising them
    before forming s^2 is dimensionally inconsistent with (X'WX)^-1 and was the
    bug behind an SE ~6x the slope in the first version of `algebra2.py`.
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    w = np.ones_like(x) if w is None else np.asarray(w, float)
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    x, y, w = x[m], y[m], w[m]
    cl = None if cluster is None else np.asarray(cluster)[m]
    X = np.column_stack([np.ones_like(x), x])
    XtW = X.T * w
    XtWX = XtW @ X
    beta = np.linalg.solve(XtWX, XtW @ y)
    r = y - X @ beta
    n, k = len(y), 2
    inv = np.linalg.inv(XtWX)
    if cl is None:
        cov = float((w * r ** 2).sum() / (n - k)) * inv
        G = None
    else:
        meat = np.zeros((k, k))
        for idx in pd.DataFrame({"g": cl}).groupby("g").indices.values():
            u = (X[idx] * w[idx, None]).T @ r[idx]
            meat += np.outer(u, u)
        G = len(np.unique(cl))
        cov = inv @ meat @ inv * (G / (G - 1))
    return (float(beta[1]), float(np.sqrt(np.diag(cov))[1]), int(n),
            None if G is None else int(G))


def pop_ladder(d: pd.DataFrame) -> pd.DataFrame:
    """The diagnostic that found the defect: slope vs minimum district size."""
    rows = []
    for cycle in ["2017-18", "2021-22"]:
        s0 = d[d.cycle == cycle]
        for cut in POP_LADDER:
            t = s0[s0.pop_5_17 >= cut]
            bu, seu, n, _ = fit(t.pov_rate, t.alg2_per_child, None)
            bw, sew, _, _ = fit(t.pov_rate, t.alg2_per_child, t.pop_5_17)
            rows.append({"cycle": cycle, "min_pop_5_17": cut, "n": n,
                         "slope_unweighted": round(bu, 4), "se_unweighted": round(seu, 4),
                         "slope_weighted": round(bw, 4), "se_weighted": round(sew, 4),
                         "max_alg2_per_child": round(float(t.alg2_per_child.max()), 2)})
    return pd.DataFrame(rows)


def cross_section(d: pd.DataFrame) -> pd.DataFrame:
    """003's between-district slope, under weighting x clustering."""
    d = d[d.pop_5_17 >= MIN_POP]
    rows = []
    for cycle in ["2017-18", "2021-22"]:
        for scope, sel in (("national", d.cycle == cycle),
                           ("Texas", (d.cycle == cycle) & (d.state_pc == "TX"))):
            s = d[sel]
            if len(s) < 30:
                continue
            for wt_name, wt in (("population-weighted", s.pop_5_17.values),
                                ("unweighted", None)):
                # Texas is one state, so state clustering is meaningless there
                cl = s.state_pc.values if scope == "national" else None
                b, se, n, G = fit(s.pov_rate.values, s.alg2_per_child.values,
                                  wt, cluster=cl)
                b0, se0, _, _ = fit(s.pov_rate.values, s.alg2_per_child.values, wt)
                rows.append({"cycle": cycle, "scope": scope, "weighting": wt_name,
                             "slope": round(b, 4), "se_naive": round(se0, 4),
                             "se_clustered": round(se, 4) if cl is not None else None,
                             "se_ratio": round(se / se0, 2) if cl is not None else None,
                             "n": n, "n_states": G})
    return pd.DataFrame(rows)


def within(d: pd.DataFrame, scope: str, weighted: bool) -> dict:
    """District + cycle fixed effects, absorbed by demeaning. Clustered on district."""
    s = d[(d.cycle != DROP_CYCLE) & (d.pop_5_17 >= MIN_POP)].copy()
    if scope == "Texas":
        s = s[s.state_pc == "TX"]
    # a district must appear in >=2 cycles to contribute within-variation
    keep = s.groupby("leaid").cycle.nunique()
    s = s[s.leaid.isin(keep[keep >= 2].index)]
    if len(s) < 100:
        return {}
    w = s.pop_5_17.astype(float).values if weighted else np.ones(len(s))
    df = pd.DataFrame({"x": s.pov_rate.values, "y": s.alg2_per_child.values,
                       "d": s.leaid.values, "c": s.cycle.values, "w": w})

    # exact two-way within transformation by alternating projections:
    # weighted district and cycle demeaning repeated to convergence. One
    # pass is exact only on a balanced panel; this panel is unbalanced.
    def _demean(v: np.ndarray) -> np.ndarray:
        for _ in range(500):
            shift = 0.0
            for key in ("d", "c"):
                num = pd.Series(v * w).groupby(df[key].values).transform("sum")
                den = pd.Series(w).groupby(df[key].values).transform("sum")
                m = (num / den).values
                v = v - m
                shift = max(shift, float(np.max(np.abs(m))))
            if shift < 1e-12:
                break
        return v

    df["x"] = _demean(df.x.astype(float).values.copy())
    df["y"] = _demean(df.y.astype(float).values.copy())
    b, se, n, G = fit(df.x, df.y, df.w, cluster=df.d.values)
    return {"scope": scope, "weighting": "population-weighted" if weighted
            else "unweighted", "slope": round(b, 4), "se": round(se, 4),
            "z": round(b / se, 2) if se else None, "n": n, "n_districts": G,
            "cycles": sorted(s.cycle.unique())}


def fig(cs: pd.DataFrame, fe: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    labels, vals, errs, cols = [], [], [], []
    for scope in ("national", "Texas"):
        for wt in ("population-weighted", "unweighted"):
            r = cs[(cs.scope == scope) & (cs.weighting == wt)
                   & (cs.cycle == "2017-18")]
            if len(r):
                labels.append(f"{scope}\n{wt.split('-')[0]}\ncross-section")
                vals.append(float(r.slope.iloc[0]))
                e = r.se_clustered.iloc[0]
                errs.append(1.96 * float(e if pd.notna(e) else r.se_naive.iloc[0]))
                cols.append(SERIES[0] if scope == "national" else SERIES[1])
        r = fe[(fe.scope == scope) & (fe.weighting == "population-weighted")]
        if len(r):
            labels.append(f"{scope}\nwithin-district\n(fixed effects)")
            vals.append(float(r.slope.iloc[0]))
            errs.append(1.96 * float(r.se.iloc[0]))
            cols.append(SERIES[2])
    x = np.arange(len(labels))
    ax.errorbar(x, vals, yerr=errs, fmt="o", ms=8, capsize=4, lw=2,
                color="none", ecolor=MUTED, zorder=2)
    for i, (v, c) in enumerate(zip(vals, cols)):
        ax.plot(i, v, "o", ms=9, color=c, zorder=3)
        ax.text(i + 0.13, v, f"{v:+.3f}", ha="left", va="center", fontsize=9,
                color=c, fontweight="bold")
    ax.axhline(0, color=INK2, lw=1.2, zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_xlim(-0.5, len(labels) - 0.35)
    ax.set_ylabel("slope: Algebra II per child\nper unit district poverty rate")
    return finish(fig, ax, "024_algebra2_robustness",
                  "The between-district gradient is robust; the within-district one is not the same thing",
                  "2017-18 for the cross-sections; fixed effects use CRDC "
                  "2013-14 to 2021-22 (2011-12 excluded — report 022 found its "
                  "zeros are miscoded blanks). 95% CI, clustered on state for "
                  "the national cross-section and on district for fixed "
                  "effects. Cross-section and within-district answer DIFFERENT "
                  "questions; see the report.")


def main() -> int:
    d = load()
    OUT["n_rows"] = int(len(d))
    OUT["min_pop_5_17"] = MIN_POP
    OUT["n_dropped_by_min_pop"] = int((d.pop_5_17 < MIN_POP).sum())

    ladder = pop_ladder(d)
    OUT["pop_ladder"] = ladder.to_dict("records")
    ladder.to_csv(os.path.join(FIGDIR, "024_pop_ladder.csv"), index=False)

    cs = cross_section(d)
    OUT["cross_section"] = cs.to_dict("records")

    fe = pd.DataFrame([r for r in
                       (within(d, sc, w) for sc in ("national", "Texas")
                        for w in (True, False)) if r])
    OUT["fixed_effects"] = fe.to_dict("records")

    # does the weighting change 003's stability verdict?
    for wt in ("population-weighted", "unweighted"):
        sub = cs[(cs.scope == "national") & (cs.weighting == wt)].sort_values("cycle")
        if len(sub) == 2:
            a, b = sub.iloc[0], sub.iloc[1]
            se = float(np.hypot(a.se_clustered or a.se_naive,
                                b.se_clustered or b.se_naive))
            OUT[f"stability_z_{wt}"] = round((b.slope - a.slope) / se, 2)

    OUT["figures"] = [fig(cs, fe)]
    cs.to_csv(os.path.join(FIGDIR, "024_cross_section.csv"), index=False)
    fe.to_csv(os.path.join(FIGDIR, "024_fixed_effects.csv"), index=False)
    with open(os.path.join(FIGDIR, "024_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1, default=str)
    print("--- cross-section (between districts) ---")
    print(cs.to_string(index=False))
    print("\n--- district + cycle fixed effects (within districts) ---")
    print(fe.to_string(index=False))
    print("\nstability z (national, 2017-18 -> 2021-22):",
          {k: v for k, v in OUT.items() if k.startswith("stability_z")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
