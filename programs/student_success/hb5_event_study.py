"""
Report 019 — HB5 at student level: an event study with a real control group.

Report 010 CLOSED the district-level HB5 question, and not by finding a null:
randomization inference showed the noise floor was 4x the estimate (placebo SD
0.0487 against a DiD of 0.0116). The structural problem was ONE TREATED CLUSTER
-- Texas -- which no standard error can rescue.

The student-level design fixes exactly that. HB5 made the Foundation plan the
default for students ENTERING Texas high school in 2014-15, so within a single
UTSA admissions pipeline we observe:
  * TREATED   students who entered a TEXAS high school in 2014 or 2015
  * CONTROL   students who entered a high school in ANOTHER US STATE, admitted
              by the same university under the same criteria in the same years
  * NINE PRE-PERIODS (2005-2013) on which parallel trends is TESTABLE

That last point is what report 010 never had. A design with nine pre-periods can
be disbelieved on evidence rather than on principle.

CONTROL GROUP DEFINITION. `hs_state` carries non-state codes: FR (foreign, 1,574
students -- the single largest non-Texas code) and AE (Armed Forces Europe).
Foreign-schooled students are not a credible counterfactual for a Texas
graduation-requirement change, so the control is restricted to the 50 US states
plus DC. This is a decision that moves the answer and is therefore stated, not
buried.

WHAT HB5 PREDICTS. It removed Algebra II from the default graduation plan, so
post-2014 Texas cohorts should arrive with LESS mathematics: lower pre-college
credit rates, lower SAT/ACT mathematics, higher DFW in their first UTSA course.

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
from courses import canon
from instrument_outcome import COURSE_SQL, CREDIT_SQL, DFW

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402

setup()
OUT: dict = {}

HB5_FIRST = 2014          # first treated high-school entry cohort
BASE_YEAR = 2013          # omitted reference period in the event study

#: the 50 states + DC. `hs_state` also carries FR (foreign) and AE (forces).
US_STATES = set("""AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME
MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT
VA WA WV WI WY""".split())

OUTCOMES = [("any_math_credit", "any pre-college math credit"),
            ("ap", "AP credit"),
            ("dual", "dual-enrolment credit"),
            ("satact_math", "SAT/ACT mathematics"),
            ("first_dfw", "D/F/W in first UTSA maths course")]


def frame() -> pd.DataFrame:
    s = gl.students()
    cr = db.cached_query("gateway-credit-type-sat", CREDIT_SQL)
    for k in ("ap", "dual"):
        cr[k] = pd.to_numeric(cr[k], errors="coerce").fillna(0).astype(int)

    # first UTSA mathematics course attempted, and whether it was failed
    c = db.cached_query("mat-course-attempts", COURSE_SQL)
    c["course"] = c.title.map(canon)
    c["term_n"] = pd.to_numeric(c.term, errors="coerce")
    first = (c.sort_values(["IDENTIFIER", "term_n"])
               .drop_duplicates("IDENTIFIER", keep="first"))
    first = first.assign(first_dfw=first.grade.astype(str).str.strip()
                         .str.upper().isin(DFW).astype(int))[
        ["IDENTIFIER", "first_dfw"]]

    d = (s.merge(cr[["IDENTIFIER", "ap", "dual"]], on="IDENTIFIER", how="left")
          .merge(first, on="IDENTIFIER", how="left"))
    d = d[d.hs_entry_year.notna() & d.hs_state.isin(US_STATES)].copy()
    d["year"] = d.hs_entry_year.astype(int)
    d["tx"] = (d.hs_state == "TX").astype(int)
    d["post"] = (d.year >= HB5_FIRST).astype(int)
    for k in ("ap", "dual"):
        d[k] = pd.to_numeric(d[k], errors="coerce").fillna(0).astype(int)
    d["any_math_credit"] = pd.to_numeric(
        d.any_math_credit, errors="coerce").fillna(0).astype(float)
    d["satact_math"] = pd.to_numeric(d.satact_math, errors="coerce")
    return d


def _ols(X: np.ndarray, y: np.ndarray, g: np.ndarray) -> tuple:
    """OLS with cluster-robust (Liang-Zeger) covariance on `g`."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for i in pd.DataFrame({"g": g}).groupby("g").indices.values():
        u = X[i].T @ r[i]
        meat += np.outer(u, u)
    G = len(np.unique(g))
    V = XtX_inv @ meat @ XtX_inv * (G / max(G - 1, 1))
    return beta, np.sqrt(np.diag(V)), G


def event_study(d: pd.DataFrame, col: str) -> pd.DataFrame:
    """TX x year interactions, 2013 omitted. Clustered on high school."""
    s = d.dropna(subset=[col]).copy()
    years = sorted(y for y in s.year.unique() if y != BASE_YEAR)
    parts = [pd.get_dummies(s.year, prefix="y", drop_first=False).astype(float)]
    inter = pd.DataFrame(
        {f"tx_{y}": (s.tx * (s.year == y)).astype(float).values for y in years},
        index=s.index)
    X = pd.concat([parts[0], pd.Series(s.tx.astype(float).values,
                                       index=s.index, name="tx"), inter], axis=1)
    beta, se, G = _ols(X.values, s[col].astype(float).values,
                       s.hs_name.fillna("?").values)
    names = list(X.columns)
    rows = [{"year": y,
             "beta": round(float(beta[names.index(f"tx_{y}")]), 4),
             "se": round(float(se[names.index(f"tx_{y}")]), 4)}
            for y in years]
    rows.append({"year": BASE_YEAR, "beta": 0.0, "se": 0.0})
    out = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    out["outcome"] = col
    out["n"] = len(s)
    out["n_clusters"] = G
    return out


def did(d: pd.DataFrame, col: str) -> dict:
    """Two-way DiD: outcome ~ tx + post + tx:post, clustered on high school."""
    s = d.dropna(subset=[col]).copy()
    X = np.column_stack([np.ones(len(s)), s.tx, s.post, s.tx * s.post]).astype(float)
    beta, se, G = _ols(X, s[col].astype(float).values, s.hs_name.fillna("?").values)
    return {"outcome": col, "n": int(len(s)), "n_clusters": int(G),
            "did": round(float(beta[3]), 4), "se": round(float(se[3]), 4),
            "z": round(float(beta[3] / se[3]), 2) if se[3] else None}


def pretrend(ev: pd.DataFrame) -> dict:
    """Wald-style test that all PRE-period interactions are jointly small.

    Uses the individual SEs rather than the full covariance (which _ols does not
    return), so it is INDICATIVE only -- it ignores covariance between the
    year interactions and will understate the true p-value. Stated in the report.
    """
    pre = ev[(ev.year < HB5_FIRST) & (ev.year != BASE_YEAR) & (ev.se > 0)]
    if not len(pre):
        return {}
    z = (pre.beta / pre.se).abs()
    return {"n_pre": int(len(pre)), "max_abs_z": round(float(z.max()), 2),
            "mean_abs_z": round(float(z.mean()), 2)}


def fig(evs: dict, keys: list[str], pres: dict) -> str:
    fig, axes = plt.subplots(1, len(keys), figsize=(4.5 * len(keys), 4.8))
    axes = np.atleast_1d(axes)
    for ax, k in zip(axes, keys):
        ev = evs[k]
        # a failing pre-trend disqualifies the panel; say so ON the panel
        bad = pres.get(k, {}).get("max_abs_z", 0) > 2.5
        col = MUTED if bad else SERIES[0]
        ax.errorbar(ev.year, ev.beta, yerr=1.96 * ev.se, fmt="o", ms=5,
                    capsize=3, lw=1.5, color=col, zorder=3)
        ax.axhline(0, color=MUTED, lw=1, zorder=1)
        ax.axvline(HB5_FIRST - 0.5, color=SERIES[1], lw=1.6, ls="--", zorder=2)
        lo, hi = ax.get_ylim()
        ax.set_ylim(lo, hi + (hi - lo) * 0.22)
        ax.text(HB5_FIRST - 0.35, hi, "HB5", color=SERIES[1], fontsize=8.5,
                va="top")
        note = ("PRE-TREND FAILS\nnot interpretable" if bad
                else "pre-trend flat")
        ax.text(0.02, 0.98, f"{dict(OUTCOMES)[k]}\n{note}", transform=ax.transAxes,
                va="top", ha="left", fontsize=9,
                color=(SERIES[1] if bad else INK2),
                fontweight=("bold" if bad else "normal"))
        ax.set_xlabel("high-school entry year")
        ax.tick_params(labelsize=8)
    axes[0].set_ylabel("Texas − other US states\n(2013 omitted)")
    fig.subplots_adjust(top=0.82)
    return finish(fig, axes[0], "019_hb5_event_study",
                  "Where parallel trends holds, there is no HB5 break",
                  "Texas × entry-year interactions from a student-level event "
                  "study, 2013 omitted, 95% CI from SEs clustered on high "
                  "school. Control is students from other US states in the same "
                  "UTSA cohorts (foreign-schooled excluded). Nine pre-periods "
                  "make parallel trends testable rather than assumed — and for "
                  "credit outcomes it fails, so no effect can be read from them.")


def main() -> int:
    d = frame()
    OUT["n_students"] = int(len(d))
    OUT["n_tx"] = int(d.tx.sum())
    OUT["n_control"] = int((1 - d.tx).sum())
    OUT["n_post_tx"] = int(((d.tx == 1) & (d.post == 1)).sum())

    evs, dids, pres = {}, [], {}
    for col, _ in OUTCOMES:
        evs[col] = event_study(d, col)
        dids.append(did(d, col))
        pres[col] = pretrend(evs[col])
    ev_all = pd.concat(evs.values(), ignore_index=True)
    dd = pd.DataFrame(dids)
    OUT["did"] = dd.to_dict("records")
    OUT["pretrend"] = pres

    cells = (d.groupby(["year", "tx"], observed=True)
               .agg(n_students=("ap", "size"),
                    pct_ap=("ap", lambda x: 100 * x.mean()),
                    pct_dual=("dual", lambda x: 100 * x.mean()),
                    mean_satact_math=("satact_math", "mean"))
               .reset_index().round(3))
    cells["group"] = np.where(cells.tx == 1, "Texas", "other US states")
    cells = cells.drop(columns=["tx"])

    OUT["figures"] = [fig(evs, ["any_math_credit", "satact_math", "first_dfw"], pres)]
    gl.publish(cells, "utsa_hb5_cohort", ["year", "group"])
    ev_all.to_csv(os.path.join(FIGDIR, "019_event_study.csv"), index=False)
    dd.to_csv(os.path.join(FIGDIR, "019_did.csv"), index=False)
    cells.to_csv(os.path.join(FIGDIR, "019_cohort_cells.csv"), index=False)
    with open(os.path.join(FIGDIR, "019_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)

    print(f"TX {OUT['n_tx']:,} | control {OUT['n_control']:,} | "
          f"TX post {OUT['n_post_tx']:,}")
    print("\n--- DiD (TX x post), clustered on high school ---")
    print(dd.to_string(index=False))
    print("\n--- pre-trend |z| on the 8 pre-period interactions ---")
    print(json.dumps(pres, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
