"""
Report 018 — does dual-A parity survive holding the high school fixed?

Report 017's central claim is a NULL: adjusted for SAT/ACT mathematics, a dual A
does not differ significantly from AP credit (+4.0 pp, z = 1.76). Nulls are the
easiest results to manufacture by accident, so it is worth attacking directly.

THE ATTACK. Report 017 used course fixed effects only. Report 015 showed the
POOLED dual penalty is not driven by district quality -- but that was measured on
all dual credit together, where B and C dominate. Dual-A students might come from
better schools than dual-B/C students, in which case 017's parity could be school
quality doing the work rather than the credit being equivalent.

So: re-run the AP-vs-dual-A contrast with district and then high-school fixed
effects. If parity is real it should hold, or move only within noise. If it was
school quality, the estimate should grow when schools are held fixed.

CELL DEPTH IS THE BINDING CONSTRAINT and was checked before writing this:
    district  47 cells carry both AP and dual A  (1,435 students)
    school    52 cells carry both AP and dual A  (  742 students)
Thin. The report says so rather than presenting the estimates as settled.

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
from analysis.style import FIGDIR, MUTED, SERIES, finish, setup  # noqa: E402
from gateway import db as gdb  # noqa: E402

setup()
OUT: dict = {}
LEVELS = ["AP credit", "Dual A", "Dual B", "Dual C"]


def linked() -> pd.DataFrame:
    d = frame()
    stu = gl.students()[["IDENTIFIER", "hs_name", "hs_city"]]
    with gdb.connect() as g:
        xw = pd.read_sql("SELECT hs_name, hs_city, leaid, ncessch "
                         "FROM core.hs_crosswalk WHERE decision LIKE 'auto%%'", g)
    d = (d.merge(stu, on="IDENTIFIER", how="left")
          .merge(xw, on=["hs_name", "hs_city"], how="left"))
    return d[d.group.isin(LEVELS)].copy()


def contrast(d: pd.DataFrame, fe_cols: list[str], treat: str,
             label: str, sat: bool = True) -> dict:
    """AP credit vs one dual grade, fixed effects absorbed, clustered SEs."""
    s = d[d.group.isin(["AP credit", treat])].copy()
    need = (["satact_math"] if sat else []) + fe_cols
    s = s.dropna(subset=need)
    if not len(s):
        return {}
    s["fe"] = s[fe_cols].astype(str).agg("|".join, axis=1)
    both = s.groupby("fe").group.nunique()
    s = s[s.fe.isin(both[both == 2].index)]          # cells holding both arms
    if len(s) < 60:
        return {"design": label, "treat": treat, "n": int(len(s)),
                "note": "too few students in cells holding both arms"}

    cols = ["d", "sat"] if sat else ["d"]
    df = pd.DataFrame({"d": (s.group == treat).astype(float).values,
                       "sat": s.satact_math.astype(float).values if sat
                              else np.zeros(len(s)),
                       "y": s.dfw.astype(float).values,
                       "g": s.fe.values})
    for c in cols + ["y"]:
        df[c] = df[c] - df.groupby("g")[c].transform("mean")
    X, y = df[cols].values, df["y"].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    meat = np.zeros((len(cols), len(cols)))
    for i in df.groupby("g").indices.values():
        u = X[i].T @ r[i]
        meat += np.outer(u, u)
    G = df.g.nunique()
    out = {"design": label, "treat": treat, "n": int(len(s)), "n_groups": int(G),
           "beta_pp": round(float(beta[0]) * 100, 2)}
    if G < 2:
        return {**out, "se_pp": None, "z": None}
    V = XtX_inv @ meat @ XtX_inv * (G / (G - 1))
    se = float(np.sqrt(np.diag(V))[0])
    return {**out, "se_pp": round(se * 100, 2),
            "z": round(float(beta[0]) / se, 2) if se else None}


def fig(res: pd.DataFrame) -> str:
    designs = ["pooled (course FE)", "within district", "within high school"]
    treats = ["Dual A", "Dual B", "Dual C"]
    x = np.arange(len(designs))
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    for j, t in enumerate(treats):
        sub = res[(res.treat == t)].set_index("design")
        ys = [sub.beta_pp.get(k, np.nan) for k in designs]
        es = [1.96 * (sub.se_pp.get(k) if pd.notna(sub.se_pp.get(k)) else np.nan)
              for k in designs]
        ax.errorbar(x + (j - 1) * 0.17, ys, yerr=es, fmt="o", ms=7, capsize=4,
                    lw=1.8, color=SERIES[j + 1], label=t, zorder=3)
    ax.axhline(0, color=SERIES[0], lw=1.6, zorder=2)
    ax.text(len(designs) - 0.55, 1.2, "AP credit baseline", ha="right",
            fontsize=8.5, color=SERIES[0])
    ax.set_xticks(x)
    ax.set_xticklabels(["Pooled\n(course only)", "Within\ndistrict",
                        "Within\nhigh school"], fontsize=9)
    ax.set_xlim(-0.5, len(designs) - 0.45)
    ax.set_ylabel("DFW gap vs AP credit\n(percentage points)")
    ax.legend(loc="upper left", title="prior credit")
    return finish(fig, ax, "018_dual_grade_within",
                  "Holding the school fixed leaves dual B untouched and shrinks dual A",
                  "Linear probability model on first-attempt DFW, adjusted for "
                  "SAT/ACT maths, fixed effects absorbed by demeaning, 95% CI "
                  "from SEs clustered on the fixed-effect unit. Each contrast "
                  "uses only cells containing both arms, so n differs by "
                  "contrast. Cells are thin — see the report. Not causal.")


def main() -> int:
    d = linked()
    designs = [(["course"], "pooled (course FE)"),
               (["course", "leaid"], "within district"),
               (["course", "ncessch"], "within high school")]
    rows = [contrast(d, fe, t, lab)
            for fe, lab in designs for t in ("Dual A", "Dual B", "Dual C")]
    res = pd.DataFrame([r for r in rows if r])
    OUT["models"] = res.to_dict("records")

    cells = (d.dropna(subset=["ncessch"])
              .groupby(["course", "group"], observed=True)
              .agg(n_students=("dfw", "size"),
                   pct_dfw=("dfw", lambda x: 100 * x.mean()))
              .reset_index().round(3))

    OUT["figures"] = [fig(res)]
    gl.publish(cells, "utsa_dual_grade_matched", ["course", "group"])
    res.to_csv(os.path.join(FIGDIR, "018_within_models.csv"), index=False)
    cells.to_csv(os.path.join(FIGDIR, "018_cells.csv"), index=False)
    with open(os.path.join(FIGDIR, "018_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(res.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
