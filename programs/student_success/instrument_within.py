"""
Report 015 — Is the AP/dual gap the INSTRUMENT, or the districts that use it?

Report 014 found dual-credit students failing at 2-5x the AP rate within the
same UTSA course, surviving SAT stratification. But AP and dual students come
from systematically different districts (report 013), so the gap could be
district quality wearing an instrument's clothes.

Three nested designs, each holding more constant:

  1. POOLED            course fixed effects only            (= report 014)
  2. WITHIN DISTRICT   course + district fixed effects      district quality fixed
  3. WITHIN SCHOOL     course + high-school fixed effects   the tightest available

If the gap is really district quality, it shrinks toward zero as the fixed
effects absorb it. If it survives within the same high school, the two
instruments differ for students who had access to both.

Estimated as a linear probability model on DFW, absorbing fixed effects by
within-transformation (demeaning), with SAT/ACT mathematics as a covariate.
Standard errors are clustered on the fixed-effect unit.

Processed LOCALLY; only aggregate cells (n >= 10) are published.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

import config
import db
import gateway_link as gl
from instrument_outcome import COURSE_SQL, CREDIT_SQL, DFW, norm_title

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from analysis.style import FIGDIR  # noqa: E402
from gateway import db as gdb  # noqa: E402

OUT: dict = {}


def frame() -> pd.DataFrame:
    c = db.cached_query("mat-course-attempts", COURSE_SQL)
    cr = db.cached_query("gateway-credit-type-sat", CREDIT_SQL)
    for k in ("ap", "dual"):
        cr[k] = pd.to_numeric(cr[k], errors="coerce").fillna(0).astype(int)
    cr["satact_math"] = pd.to_numeric(cr.satact_math, errors="coerce")

    c["course"] = c.title.map(norm_title)
    c["term_n"] = pd.to_numeric(c.term, errors="coerce")
    c = c.sort_values(["IDENTIFIER", "course", "term_n"])
    first = c.drop_duplicates(subset=["IDENTIFIER", "course"], keep="first")
    first = first.assign(
        dfw=first.grade.astype(str).str.strip().str.upper().isin(DFW).astype(int))

    stu = gl.students()[["IDENTIFIER", "hs_name", "hs_city"]]
    with gdb.connect() as g:
        xw = pd.read_sql("SELECT hs_name, hs_city, leaid, ncessch "
                         "FROM core.hs_crosswalk WHERE decision LIKE 'auto%%'", g)
    d = (first.merge(cr, on="IDENTIFIER", how="left")
               .merge(stu, on="IDENTIFIER", how="left")
               .merge(xw, on=["hs_name", "hs_city"], how="left"))
    for k in ("ap", "dual"):
        d[k] = pd.to_numeric(d[k], errors="coerce").fillna(0).astype(int)
    d = d[(d.ap + d.dual) == 1]                       # mutually exclusive
    d["dual_only"] = (d.dual == 1).astype(float)
    return d


def within_lpm(d: pd.DataFrame, fe_cols: list[str], label: str,
               sat: bool = True) -> dict:
    """LPM on DFW with fixed effects absorbed by demeaning; clustered SEs."""
    need = (["satact_math"] if sat else []) + fe_cols
    s = d.dropna(subset=need).copy()
    if not len(s):
        return {}
    s["fe"] = s[fe_cols].astype(str).agg("|".join, axis=1)
    # keep only cells with BOTH instruments present -- otherwise the fixed
    # effect absorbs the very contrast we are trying to estimate
    both = s.groupby("fe").dual_only.nunique()
    s = s[s.fe.isin(both[both == 2].index)]
    if len(s) < 100:
        return {"n": int(len(s)), "note": "too few cells with both instruments"}

    cols = ["d", "sat"] if sat else ["d"]
    df = pd.DataFrame({"d": s.dual_only.astype(float).values,
                       "sat": s.satact_math.astype(float).values if sat
                              else np.zeros(len(s)),
                       "y": s.dfw.astype(float).values,
                       "g": s.fe.values})
    for c in cols + ["y"]:                            # within-transformation
        df[c] = df[c] - df.groupby("g")[c].transform("mean")
    Xd = df[cols].values
    yd = df["y"].values
    beta, *_ = np.linalg.lstsq(Xd, yd, rcond=None)
    resid = yd - Xd @ beta
    # cluster-robust (Liang-Zeger) on the FE unit
    k = len(cols)
    XtX_inv = np.linalg.inv(Xd.T @ Xd)
    meat = np.zeros((k, k))
    for i in df.groupby("g").indices.values():
        u = Xd[i].T @ resid[i]
        meat += np.outer(u, u)
    G = df.g.nunique()
    out = {"design": label, "sat_control": sat, "n": int(len(s)),
           "n_groups": int(G), "beta_dual": round(float(beta[0]) * 100, 2)}
    if G < 2:
        # one cluster -> the Liang-Zeger meat is the outer product of a single
        # score vector, which is singular. No clustered SE exists; report none.
        return {**out, "se": None, "z": None}
    V = XtX_inv @ meat @ XtX_inv * (G / (G - 1))
    se = float(np.sqrt(np.diag(V))[0])
    return {**out, "se": round(se * 100, 2),
            "z": round(float(beta[0]) / se, 2) if se else None}


def fig(res: pd.DataFrame) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from analysis.style import MUTED, SERIES, finish

    short = {"pooled (course FE)": "Pooled\n(course only)",
             "within district (course+district FE)": "Within\ndistrict",
             "within high school (course+school FE)": "Within\nhigh school"}
    order = list(short)
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    for j, (sat, lab) in enumerate([(False, "Unadjusted"),
                                    (True, "Adjusted for SAT/ACT math")]):
        sub = res[res.sat_control == sat].set_index("design")
        xs = np.arange(len(order)) + (j - 0.5) * 0.24
        ys = [sub.beta_dual.get(k, np.nan) for k in order]
        es = [1.96 * (sub.se.get(k) or np.nan) for k in order]
        ax.errorbar(xs, ys, yerr=es, fmt="o", ms=8, capsize=4, lw=2,
                    color=SERIES[j], label=lab, zorder=3)
        for x, y in zip(xs, ys):
            ax.text(x + 0.055, y, f"{y:.1f}", ha="left", va="center",
                    fontsize=9, color=SERIES[j], fontweight="bold")
    ax.axhline(0, color=MUTED, lw=1, zorder=1)
    ax.set_xticks(np.arange(len(order)))
    ax.set_xticklabels([short[k] for k in order], fontsize=9)
    ax.set_ylabel("dual-credit DFW penalty\n(percentage points)")
    ax.set_ylim(bottom=-1)
    ax.legend(loc="upper right")
    return finish(fig, ax, "015_within_ladder",
                  "The dual-credit penalty survives holding the high school fixed",
                  "Linear probability model on first-attempt DFW, fixed effects "
                  "absorbed by demeaning, 95% CI from SEs clustered on the "
                  "fixed-effect unit. Only cells containing both instruments "
                  "contribute. Not causal: instrument is chosen, not assigned.")


def main() -> int:
    d = frame()
    OUT["n_attempts"] = int(len(d))
    OUT["n_with_district"] = int(d.leaid.notna().sum())

    designs = [(["course"], "pooled (course FE)"),
               (["course", "leaid"], "within district (course+district FE)"),
               (["course", "ncessch"], "within high school (course+school FE)")]
    rows = [within_lpm(d, fe, lab, sat=s)
            for fe, lab in designs for s in (False, True)]
    res = pd.DataFrame([r for r in rows if r])
    OUT["models"] = res.to_dict("records")

    # the same ladder restricted to Calculus II -- the large balanced course
    c2 = d[d.course.str.startswith("Calculus II") & ~d.course.str.contains("III")]
    rows2 = [within_lpm(c2, fe, lab, sat=s)
             for fe, lab in designs for s in (False, True)]
    res2 = pd.DataFrame([r for r in rows2 if r])
    OUT["models_calc2"] = res2.to_dict("records")

    # descriptive: districts that supply BOTH instruments
    dd = d.dropna(subset=["leaid"])
    mix = dd.groupby("leaid").dual_only.agg(["mean", "size"])
    OUT["n_districts"] = int(len(mix))
    OUT["n_districts_mixed"] = int(((mix["mean"] > 0.05) & (mix["mean"] < 0.95)).sum())

    cells = (dd.groupby(["course", "dual_only"], observed=True)
               .agg(n_students=("dfw", "size"),
                    pct_dfw=("dfw", lambda x: 100 * x.mean())).reset_index())
    cells["instrument"] = np.where(cells.dual_only == 1, "Dual only", "AP only")
    cells = cells.drop(columns=["dual_only"]).round(3)

    os.makedirs(FIGDIR, exist_ok=True)
    OUT["figures"] = [fig(res)]
    res.to_csv(os.path.join(FIGDIR, "015_within_models.csv"), index=False)
    res2.to_csv(os.path.join(FIGDIR, "015_within_models_calc2.csv"), index=False)
    cells.to_csv(os.path.join(FIGDIR, "015_cells.csv"), index=False)
    gl.publish(cells, "utsa_dfw_instrument_matched", ["course", "instrument"])
    with open(os.path.join(FIGDIR, "015_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print("--- all courses ---")
    print(res.to_string(index=False))
    print("\n--- Calculus II only ---")
    print(res2.to_string(index=False))
    print()
    print(f"districts supplying both instruments: {OUT['n_districts_mixed']} "
          f"of {OUT['n_districts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
