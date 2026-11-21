"""Clustered heatmap: subjects x donor majors, GPA deviation of changers.

Generalizes tables 2.2-2.4 of the report from three subjects to the whole
subject x major matrix. Population: first-time freshmen of the clean cohort
who CHANGED major within the horizon. Cell (subject s, first major m) =
mean over those students of

    GPA in s  -  mean GPA in their other subjects  (leave-one-out)

Red = the subject grades below the student's own norm (a barrier for that
major's leavers); blue = above. Rows and columns are ordered by
hierarchical clustering (Ward on the NaN-neutralized matrix), with
dendrograms showing the cluster structure.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from scipy.cluster.hierarchy import dendrogram, linkage

import config
import data
from db import term_str
from matplotlib.colors import LinearSegmentedColormap
from texout import save_figure

# diverging: red (below own norm) - neutral gray - blue (above)
GPA_CMAP = LinearSegmentedColormap.from_list(
    "gpa_dev", [config.ROSE_HARMFUL, "#f0efec", config.ROSE_BENEFICIAL])

MIN_CELL_N = 15      # cells with fewer changers are blanked
TOP_SUBJECTS = 30
TOP_MAJORS = 30


def deviation_matrix():
    """(matrix, counts): mean leave-one-out GPA deviation per cell."""
    g = data.cohort_subject_gpa()
    changed = data.cohort_major_change()
    majors = data.cohort_majors()
    first = majors.set_index("id")["firstmajor"]
    g = g[g["id"].isin(changed.index[changed])]          # changers only
    g["major"] = first.reindex(g["id"]).values
    g = g.dropna(subset=["major"])
    # leave-one-out deviation: gpa_s - mean(other subjects' gpa)
    stats = g.groupby("id")["gpa"].agg(["sum", "count"])
    g = g.join(stats, on="id")
    other = (g["sum"] - g["gpa"]) / (g["count"] - 1)
    g["dev"] = g["gpa"] - other
    g = g[g["count"] > 1]
    cell = g.groupby(["subject", "major"])["dev"].agg(["mean", "size"])
    m = cell["mean"].unstack()
    n = cell["size"].unstack().fillna(0)
    m = m.where(n >= MIN_CELL_N)
    # keep the biggest rows/columns by changer coverage
    subj = n.sum(axis=1).sort_values(ascending=False).head(TOP_SUBJECTS).index
    maj = n.sum(axis=0).sort_values(ascending=False).head(TOP_MAJORS).index
    return m.loc[subj, maj], n.loc[subj, maj]


def _cluster_order(m: pd.DataFrame):
    filled = m.fillna(0.0).to_numpy()
    row_link = linkage(filled, method="ward")
    col_link = linkage(filled.T, method="ward")
    return row_link, col_link


def heatmap_changers() -> str:
    m, counts = deviation_matrix()
    row_link, col_link = _cluster_order(m)
    fig = plt.figure(figsize=(14.8, 12))
    gs = fig.add_gridspec(2, 3, width_ratios=[0.085, 0.155, 1],
                          height_ratios=[0.10, 1], wspace=0.02, hspace=0.02)
    ax_col = fig.add_subplot(gs[0, 2]); ax_col.axis("off")
    ax_row = fig.add_subplot(gs[1, 0]); ax_row.axis("off")
    ax_sum = fig.add_subplot(gs[1, 1]); ax_sum.axis("off")
    ax = fig.add_subplot(gs[1, 2])
    with plt.rc_context({"lines.linewidth": 0.8}):
        dcol = dendrogram(col_link, ax=ax_col, orientation="top",
                          no_labels=True, color_threshold=0,
                          above_threshold_color=config.INK_MUTED)
        drow = dendrogram(row_link, ax=ax_row, orientation="left",
                          no_labels=True, color_threshold=0,
                          above_threshold_color=config.INK_MUTED)
    mm = m.iloc[drow["leaves"], dcol["leaves"]]
    span = float(np.nanmax(np.abs(mm.to_numpy()))) * 1.02
    norm = Normalize(-span, span)
    vals = np.ma.masked_invalid(mm.to_numpy())
    ax.set_facecolor("#f0efec")          # NaN cells show as neutral gray
    ax.pcolormesh(vals, cmap=GPA_CMAP, norm=norm, edgecolors="white",
                  linewidth=0.5)
    ax.set_xticks(np.arange(len(mm.columns)) + 0.5)
    ax.set_xticklabels(mm.columns, rotation=45, ha="right",
                       rotation_mode="anchor",
                       fontsize=16, color=config.INK)
    ax.set_yticks(np.arange(len(mm.index)) + 0.5)
    ax.set_yticklabels(mm.index, fontsize=17, color=config.INK)
    ax.yaxis.tick_right()
    ax.invert_yaxis()
    ax_row.invert_yaxis()
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    # Row sums (sum of the row's cell values) between dendrogram and matrix
    row_sums = mm.sum(axis=1, skipna=True)
    # aggregate companion: row sums, cell counts, and student-weighted
    # mean deviation per subject (cells with >= MIN_CELL_N students)
    nn = counts.reindex(index=mm.index, columns=mm.columns)
    obs = mm.notna()
    wmean = (mm.where(obs) * nn.where(obs)).sum(axis=1) / nn.where(obs).sum(axis=1)
    # Two row summaries on comparable scales: the student-weighted mean
    # deviation (per mover) and that mean times the movers observed (the
    # total across movers). The plain sum of cell values is kept in the
    # companion file only: it grows with the number of observed cells.
    total = (mm.where(obs) * nn.where(obs)).sum(axis=1)
    pd.DataFrame({"row_sum": row_sums.round(3),
                  "cells_observed": obs.sum(axis=1),
                  "students_in_cells": nn.where(obs).sum(axis=1).astype(int),
                  "weighted_mean_deviation": wmean.round(4),
                  "total_deviation": total.round(1),
                  # full precision, for the totals the text prints as
                  # whole numbers
                  "total_deviation_unrounded": total}
                 ).to_csv(config.IMG_DIR /
                          "figHeatmapSubjectMajor-changers_rows.csv",
                          index_label="subject")
    ax_sum.set_ylim(0, len(mm.index))
    ax_sum.invert_yaxis()
    ax_sum.set_xlim(0, 1)
    for i, (w, t) in enumerate(zip(wmean, total)):
        col = config.ROSE_HARMFUL if w < 0 else config.ROSE_BENEFICIAL
        ax_sum.text(0.37, i + 0.5, f"{w:+.2f}".replace("-", "−"),
                    ha="right", va="center", fontsize=12.5, color=col)
        ax_sum.text(0.97, i + 0.5, f"{t:+,.0f}".replace("-", "−"),
                    ha="right", va="center", fontsize=12.5, color=col)
    ax_sum.text(0.37, -0.2, "per\nmover", ha="right", va="bottom",
                fontsize=10, color=config.INK_MUTED, linespacing=1.0)
    ax_sum.text(0.97, -0.2, "total", ha="right", va="bottom",
                fontsize=10, color=config.INK_MUTED)
    cax = fig.add_axes([0.035, 0.28, 0.016, 0.42])
    cbar = fig.colorbar(ScalarMappable(norm=norm, cmap=GPA_CMAP),
                        cax=cax, orientation="vertical")
    cbar.set_label("mean GPA deviation: subject $-$ student's other"
                   " subjects (GPA points)", fontsize=15, color=config.INK)
    cbar.ax.tick_params(labelsize=13, color=config.INK_MUTED)
    cbar.outline.set_visible(False)
    h = config.COHORT_HORIZON_YEARS
    span_txt = (f"{term_str(config.COHORT_ENTRY_START)}--"
                f"{term_str(config.COHORT_ENTRY_END)}")
    del h  # window wording is fixed by the declared-boundary text below
    return save_figure(
        fig, "figHeatmapSubjectMajor-changers",
        "Differences between grades in one subject and grades in all "
        "other subjects, among students who changed major: "
        f"first-time freshmen entering {span_txt} whose first and last "
        "major within the declared observation window (entry through the "
        "fall term four years after entry, inclusive) differ. Rows are "
        "subjects, and columns are the students' initial majors. Each cell "
        "is the mean, over "
        "students whose initial major is the column, of their GPA in the "
        "row subject minus their mean GPA in all other subjects "
        "(leave-one-out). "
        "Red: these students earned lower grades in the subject than in "
        "their other subjects; blue: higher grades. Cells with fewer than "
        f"{MIN_CELL_N} students are blank; the display keeps the "
        f"{TOP_SUBJECTS} highest-volume subjects and {TOP_MAJORS} initial "
        "majors. The two left columns summarize each subject over its "
        "observed cells: the mean difference (GPA points "
        "per mover) and that mean times the number of movers observed "
        "(GPA points in total across movers). Rows "
        "and columns are ordered by "
        "Ward hierarchical clustering (dendrograms at the margins; "
        "unobserved cells enter the clustering as zero), so "
        "blocks of similar behavior appear as contiguous patches.")


def generate() -> None:
    print(" ", heatmap_changers())


if __name__ == "__main__":
    generate()
