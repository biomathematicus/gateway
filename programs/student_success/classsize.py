"""Reproduction of Figure 2.3-15 (figClassSizeUTSA) of the report
"Correlates of Student Success, 2020 Preliminary Report".

Python port of aClassSize.m ('%' branch): section-level mean GPA vs class
size from `exec ClassRoomSize` (sections with more than 10 students). For
each subject, section sizes are binned in 5-student increments; the binned
means are interpolated on a 10..500 grid and smoothed with the same
Hodrick-Prescott filter (lambda = HP_LAMBDA below). As lambda grows the
filter converges to a straight line (equivalent to a linear regression);
lambda = 1e4 keeps enough flexibility to show the trend's curvature. One curve per
subject; line width = 10 x enrollment share as in MATLAB; MAT in red.
Bubbles show the binned means, area ~ (distinct sizes in bin)^2 * 10.
"""
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config
from db import cached_query, term_str
from texout import save_figure

HP_LAMBDA = 1e4
BIN = 5
X_MAX = 500
MIN_SECTIONS = 5     # subjects with fewer size bins are skipped (MATLAB >5)
MIN_STUDENTS = 10    # a section enters with more students than this
REFERENCE_SIZE = 200  # section size at which the text reads the MAT curve
LABEL_ALL = True     # MATLAB labels every subject at its curve's end


def hodrick_prescott(y: np.ndarray, w: float = HP_LAMBDA) -> np.ndarray:
    """Direct port of the pentadiagonal HP solve in aClassSize.m."""
    y = np.asarray(y, dtype=float)
    t = len(y)
    if t < 3:
        return y
    m = np.diag(np.full(t, 6 * w + 1))
    m += np.diag(np.full(t - 1, -4 * w), 1) + np.diag(np.full(t - 1, -4 * w), -1)
    m += np.diag(np.full(t - 2, w), 2) + np.diag(np.full(t - 2, w), -2)
    m[0, 0] = 1 + w;         m[0, 1] = -2 * w
    m[1, 0] = -2 * w;        m[1, 1] = 5 * w + 1
    m[t - 2, t - 2] = 5 * w + 1
    m[t - 2, t - 1] = -2 * w
    m[t - 1, t - 2] = -2 * w
    m[t - 1, t - 1] = 1 + w
    return np.linalg.solve(m, y)


def _binned(x: pd.DataFrame):
    """MATLAB PlotCS binning: per-size mean, then 5-wide bin means/weights."""
    per_size = x.groupby("students")["gpa"].mean()
    edges = np.arange(BIN, per_size.index.max() + BIN + 1, BIN)
    rows = []
    for e in edges:
        sel = per_size[(per_size.index > e - BIN) & (per_size.index <= e)]
        if len(sel):
            rows.append((e, sel.mean(), len(sel) ** 2))
    return pd.DataFrame(rows, columns=["size", "gpa", "w"])


def class_size_utsa() -> str:
    # Section size counts every student with a row in the section; the
    # section mean uses only rows the registrar counts in the grade
    # average (SHRGRDE_GPA_IND = 'Y'). The stored procedure ClassRoomSize
    # averaged withdrawals and credit / no-credit rows in as zeros, so
    # the query is written out here and the procedure is no longer called.
    tag = f"aClassSizeGraded-{config.S_START}-{config.S_END}"
    o = cached_query(
        tag,
        "select CURRENTTERM, SHRTCKN_SUBJ_CODE, CT_SUBJECT, "
        "SHRTCKN_SEQ_NUMB, count(distinct IDENTIFIER) as STUDENTS, "
        "avg(case when SHRGRDE_GPA_IND = 'Y' "
        "then SHRGRDE_QUALITY_POINTS end) as GPA "
        "from OIR "
        f"where CURRENTTERM >= {config.S_START} "
        f"and CURRENTTERM <= {config.S_END} "
        "group by CURRENTTERM, SHRTCKN_SUBJ_CODE, CT_SUBJECT, "
        "SHRTCKN_SEQ_NUMB having count(distinct IDENTIFIER) > "
        f"{MIN_STUDENTS}",
        ["term", "subject", "course", "section", "students", "gpa"])
    o["students"] = pd.to_numeric(o["students"], errors="coerce")
    o["gpa"] = pd.to_numeric(o["gpa"], errors="coerce")
    o = o.dropna(subset=["students", "gpa"])
    served = cached_query(
        f"aClassSizeServed-{config.S_START}-{config.S_END}",
        "select SHRTCKN_SUBJ_CODE, count(distinct IDENTIFIER) as n from OIR "
        f"where CURRENTTERM >= {config.S_START} "
        f"and CURRENTTERM <= {config.S_END} "
        "group by SHRTCKN_SUBJ_CODE",
        ["subject", "n"]).set_index("subject")["n"]
    n_max = served.max()

    fig, ax = plt.subplots(figsize=(12, 7.5))
    grid = np.arange(10, X_MAX + BIN, BIN)
    for subject, g in o.groupby("subject"):
        if len(g) <= MIN_SECTIONS or subject not in served.index:
            continue
        b = _binned(g)
        if len(b) < 3:
            continue
        share = served[subject] / n_max
        ax.scatter(b["size"], b["gpa"], s=b["w"] * 10, facecolors="white",
                   edgecolors="#898781", linewidths=0.5, alpha=0.6, zorder=1)
        yi = np.interp(grid, b["size"], b["gpa"],
                       left=np.nan, right=np.nan)
        ok = ~np.isnan(yi)
        if ok.sum() < 3:
            continue
        xs, ys = grid[ok], hodrick_prescott(yi[ok])
        is_mat = subject == "MAT"
        if is_mat:
            # the two readings of the mathematics curve that the text
            # quotes: at the smallest size of the curve and at the
            # reference size
            mat_curve = {
                "smallest_size": int(xs[0]),
                "gpa_at_smallest_size": float(ys[0]),
                "reference_size": REFERENCE_SIZE,
                "gpa_at_reference_size": float(
                    np.interp(REFERENCE_SIZE, xs, ys)),
                "largest_size": int(xs[-1])}
        ax.plot(xs, ys,
                color=config.ROSE_HARMFUL if is_mat else "#2a78d6",
                lw=max(0.3, 10 * share), alpha=1.0 if is_mat else 0.55,
                zorder=3 if is_mat else 2,
                solid_capstyle="round")
        ax.annotate(subject, (xs[-1], ys[-1]),
                    xytext=(4, 0), textcoords="offset points",
                    fontsize=13, va="center",
                    color=config.ROSE_HARMFUL if is_mat else config.INK)
    ax.set_xlim(0, X_MAX)
    ax.set_ylim(0, 4)
    ax.set_xlabel("# of Students", fontsize=17, color=config.INK)
    ax.set_ylabel("GPA", fontsize=17, color=config.INK)
    ax.grid(color=config.GRID, linewidth=0.6)
    from matplotlib.lines import Line2D
    ax.legend(handles=[
        Line2D([], [], marker="o", ls="none", markerfacecolor="white",
               markeredgecolor="#898781", label="Raw Data"),
        Line2D([], [], color="#2a78d6", lw=2,
               label="Hodrick-Prescott Filter"),
    ], loc="lower right", fontsize=13, frameon=True, edgecolor=config.GRID)
    ax.tick_params(labelsize=15, color=config.INK_MUTED)
    for s in ax.spines.values():
        s.set_color(config.INK_MUTED)
    (config.IMG_DIR / "figClassSizeUTSA_stats.json").write_text(
        json.dumps({"min_students": MIN_STUDENTS, "bin": BIN,
                    "hp_lambda": HP_LAMBDA, "mat_curve": mat_curve},
                   indent=1), encoding="utf-8")
    return save_figure(
        fig, "figClassSizeUTSA",
        "Mean section GPA (rows that count in the grade average) vs.\\ "
        "class size, all subjects, "
        f"{term_str(config.S_START)}--{term_str(config.S_END)} "
        "(reproduction of Figure 2.3-15 of the 2020 preliminary report). "
        "Each curve is one subject: section sizes are binned in 5-student "
        "increments, interpolated, and smoothed with a Hodrick--Prescott "
        f"filter ($\\lambda={HP_LAMBDA:g}$; as $\\lambda \\to \\infty$ the "
        "filter converges to a straight line, equivalent to a linear "
        "regression, and this lower value retains the curvature of the "
        "trend); line width is proportional to students "
        "served; MAT is drawn in red. Bubbles are the binned means, area "
        "$\\propto$ (distinct sizes in bin)$^2$. Only sections with more "
        f"than {MIN_STUDENTS} students enter the analysis.")


def generate() -> None:
    print(" ", class_size_utsa())


if __name__ == "__main__":
    generate()
