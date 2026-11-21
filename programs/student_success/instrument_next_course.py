"""
Report 016 — placement error, or preparation deficit?

Reports 014/015 established that dual-credit students fail their first UTSA
mathematics attempt far more often than AP students, and that the gap survives
holding the high school and SAT/ACT mathematics fixed.

TWO EXPLANATIONS REMAIN, and they have opposite policy implications.

  PLACEMENT ERROR. Dual credit put the student in a course they were not ready
  for. It is a one-off mis-seating. Once the student is through that course --
  having actually passed it -- they are at the right level and should perform
  like anyone else. THE GAP SHOULD CLOSE.

  PREPARATION DEFICIT. The dual course taught less mathematics, and the student
  carries that hole forward into everything built on top of it. THE GAP SHOULD
  PERSIST, even among students who passed.

THE TEST. Take students who PASSED their first course on the ladder, then look
at how they do in the NEXT rung. Conditioning on passing is what separates the
two stories: it discards the mis-seated students, so whatever gap remains is
carried, not inherited from the placement.

This conditioning is itself a selection -- passing is easier for the
better-prepared, so the surviving dual students are positively selected relative
to the surviving AP students. That biases the residual gap DOWNWARD, which means
a gap that survives is a conservative reading of the preparation story. Stated
in the report rather than corrected for.

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
from courses import SEQUENCE, canon, next_in_sequence
from instrument_outcome import COURSE_SQL, CREDIT_SQL, DFW

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from analysis.style import FIGDIR, MUTED, SERIES, finish, setup  # noqa: E402

setup()
OUT: dict = {}


def attempts() -> pd.DataFrame:
    """First attempt at each (student, canonical course), with instrument."""
    c = db.cached_query("mat-course-attempts", COURSE_SQL)
    cr = db.cached_query("gateway-credit-type-sat", CREDIT_SQL)
    for k in ("ap", "dual"):
        cr[k] = pd.to_numeric(cr[k], errors="coerce").fillna(0).astype(int)
    cr["satact_math"] = pd.to_numeric(cr.satact_math, errors="coerce")

    c["course"] = c.title.map(canon)
    c["term_n"] = pd.to_numeric(c.term, errors="coerce")
    c = c.sort_values(["IDENTIFIER", "course", "term_n"])
    f = c.drop_duplicates(subset=["IDENTIFIER", "course"], keep="first").copy()
    f["dfw"] = f.grade.astype(str).str.strip().str.upper().isin(DFW).astype(int)
    f = f[f.course.isin(SEQUENCE)]
    f["rung"] = f.course.map(SEQUENCE.index)

    d = f.merge(cr, on="IDENTIFIER", how="left")
    for k in ("ap", "dual"):
        d[k] = pd.to_numeric(d[k], errors="coerce").fillna(0).astype(int)
    d = d[(d.ap + d.dual) == 1]
    d["instrument"] = np.where(d.dual == 1, "Dual only", "AP only")
    return d


def pairs(d: pd.DataFrame) -> pd.DataFrame:
    """(entry rung passed) -> (next rung attempted) transitions per student."""
    first = (d.sort_values(["IDENTIFIER", "rung", "term_n"])
               .drop_duplicates("IDENTIFIER", keep="first")
               [["IDENTIFIER", "course", "dfw", "instrument", "satact_math",
                 "term_n"]]
               .rename(columns={"course": "entry", "dfw": "entry_dfw",
                                "term_n": "entry_term"}))
    first["next_course"] = first.entry.map(next_in_sequence)
    nxt = d[["IDENTIFIER", "course", "dfw", "term_n"]].rename(
        columns={"course": "next_course", "dfw": "next_dfw",
                 "term_n": "next_term"})
    p = first.merge(nxt, on=["IDENTIFIER", "next_course"], how="inner")
    # the next rung must be attempted AFTER the entry rung, not before
    return p[p.next_term > p.entry_term].copy()


def table(p: pd.DataFrame) -> pd.DataFrame:
    g = (p.groupby(["entry", "next_course", "instrument"], observed=True)
           .agg(n_students=("next_dfw", "size"),
                pct_dfw_next=("next_dfw", lambda x: 100 * x.mean()),
                mean_satact_math=("satact_math", "mean"))
           .reset_index())
    return g.round(3)


def stratified(p: pd.DataFrame, step: tuple) -> pd.DataFrame:
    """Next-course DFW by SAT/ACT band, within one ladder step."""
    s = p[(p.entry == step[0]) & (p.next_course == step[1])
          & p.satact_math.notna()].copy()
    s["sat_band"] = pd.cut(s.satact_math, [0, 550, 600, 650, 900],
                           labels=["<550", "550-599", "600-649", "650+"])
    g = (s.groupby(["sat_band", "instrument"], observed=True)
           .agg(n_students=("next_dfw", "size"),
                pct_dfw_next=("next_dfw", lambda x: 100 * x.mean()))
           .reset_index())
    g["sat_band"] = g.sat_band.astype(str)
    return g.round(3)


def lpm_step_fe(p: pd.DataFrame, steps: list[tuple], sat: bool) -> dict:
    """Next-course DFW ~ dual (+ SAT), step fixed effects, HC1 robust SE.

    SEs are heteroskedasticity-robust rather than clustered: there are only two
    usable ladder steps, and a two-cluster variance estimate is not usable.
    """
    s = p[p.set_index(["entry", "next_course"]).index.isin(steps)].copy()
    if sat:
        s = s.dropna(subset=["satact_math"])
    if len(s) < 50:
        return {}
    cols = ["d", "sat"] if sat else ["d"]
    df = pd.DataFrame({"d": (s.instrument == "Dual only").astype(float).values,
                       "sat": s.satact_math.astype(float).values if sat
                              else np.zeros(len(s)),
                       "y": s.next_dfw.astype(float).values,
                       "g": s.entry.values})
    for c in cols + ["y"]:
        df[c] = df[c] - df.groupby("g")[c].transform("mean")
    Xd, yd = df[cols].values, df["y"].values
    beta, *_ = np.linalg.lstsq(Xd, yd, rcond=None)
    r = yd - Xd @ beta
    XtX_inv = np.linalg.inv(Xd.T @ Xd)
    n, k = Xd.shape
    V = XtX_inv @ (Xd.T @ (Xd * (r ** 2)[:, None])) @ XtX_inv * (n / (n - k))
    se = float(np.sqrt(np.diag(V))[0])
    return {"sat_control": sat, "n": int(n),
            "beta_dual": round(float(beta[0]) * 100, 2),
            "se": round(se * 100, 2),
            "z": round(float(beta[0]) / se, 2) if se else None}


def fig(g: pd.DataFrame, first_g: pd.DataFrame, steps: list[tuple]) -> str:
    labels = [f"{a.replace('Calculus','Calc')}\n→ {b.replace('Calculus','Calc')}"
              for a, b in steps]
    x = np.arange(len(steps))
    w = 0.20
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    for j, inst in enumerate(["AP only", "Dual only"]):
        vals, ns = [], []
        for a, b in steps:
            r = g[(g.entry == a) & (g.next_course == b) & (g.instrument == inst)]
            vals.append(float(r.pct_dfw_next.iloc[0]) if len(r) else np.nan)
            ns.append(int(r.n_students.iloc[0]) if len(r) else 0)
        pos = x + (j - 0.5) * w
        ax.bar(pos, vals, w * 0.92, color=SERIES[j], label=inst, zorder=3)
        for px, v, n in zip(pos, vals, ns):
            if np.isfinite(v):
                ax.text(px, v + 0.8, f"{v:.0f}", ha="center", fontsize=9,
                        color=SERIES[j], fontweight="bold")
                ax.text(px, -3.0, f"n={n:,}", ha="center", fontsize=7.5,
                        color=MUTED)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_xlim(-0.55, len(steps) - 0.45)
    ax.set_ylabel("% D / F / W in the NEXT course")
    ax.set_ylim(bottom=-5)
    ax.legend(loc="upper right")
    return finish(fig, ax, "016_next_course",
                  "The gap persists in the next course, among students who passed the first",
                  "Students who PASSED their entry rung, then attempted the next "
                  "rung in a later term. Conditioning on passing discards the "
                  "mis-seated, so a surviving gap is carried preparation rather "
                  "than placement. Not causal.")


def main() -> int:
    d = attempts()
    p = pairs(d)
    OUT["n_transitions"] = int(len(p))

    passed = p[p.entry_dfw == 0]
    OUT["n_passed_entry"] = int(len(passed))
    g = table(passed)
    g_all = table(p)

    # keep steps where BOTH instruments clear the publication floor
    ok = (g[g.n_students >= 10].groupby(["entry", "next_course"])
            .instrument.nunique())
    steps = [t for t, v in ok.items() if v == 2]
    steps.sort(key=lambda t: SEQUENCE.index(t[0]))
    OUT["steps"] = [list(s) for s in steps]

    for a, b in steps:
        for inst in ("AP only", "Dual only"):
            r = g[(g.entry == a) & (g.next_course == b) & (g.instrument == inst)]
            if len(r):
                OUT[f"dfw_{a}_to_{b}_{inst}".replace(" ", "_")] = \
                    float(r.pct_dfw_next.iloc[0])

    models = pd.DataFrame([m for m in
                           (lpm_step_fe(passed, steps, s) for s in (False, True))
                           if m])
    OUT["models"] = models.to_dict("records")
    strat = stratified(passed, steps[0]) if steps else pd.DataFrame()
    OUT["strat_step"] = list(steps[0]) if steps else None

    OUT["figures"] = [fig(g, g_all, steps)] if steps else []
    gl.publish(g, "utsa_next_course_dfw", ["entry", "next_course", "instrument"])
    g.to_csv(os.path.join(FIGDIR, "016_next_course.csv"), index=False)
    g_all.to_csv(os.path.join(FIGDIR, "016_next_course_unconditional.csv"),
                 index=False)
    with open(os.path.join(FIGDIR, "016_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)

    print(f"transitions: {len(p):,}  |  passed entry rung: {len(passed):,}")
    print("\n--- conditional on PASSING the entry rung ---")
    print(g.to_string(index=False))
    print("\n--- unconditional (for contrast) ---")
    print(g_all.to_string(index=False))
    print("\n--- LPM, step FE, HC1 robust ---")
    print(models.to_string(index=False))
    print(f"\n--- SAT-stratified, {steps[0][0]} -> {steps[0][1]} ---")
    print(strat.to_string(index=False))
    strat.to_csv(os.path.join(FIGDIR, "016_sat_stratified.csv"), index=False)
    models.to_csv(os.path.join(FIGDIR, "016_models.csv"), index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
