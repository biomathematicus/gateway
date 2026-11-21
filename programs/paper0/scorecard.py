"""figScorecardLocator: national position of UTSA (Paper 0, Appendix A1).

Four-panel locator from the College Scorecard, read from the project
PostgreSQL database (scorecard.institution, loaded by load_scorecard.py).
Analysis uses SQL for cross-referencing and lists / numpy arrays for
computation - no dataframes.

Two explicit vintages, one per row:
  top    "2019_20" - pre-perturbation baseline vintage: the last data
                     year whose 150%-time completion cohorts closed
                     before Fall 2019.
  bottom "2024_25" - the CURRENT position: most recent data year with
                     populated completion outcomes in the June 2026
                     release.

Left column : completion within 150% of normal time (C150_4) vs
              undergraduate enrollment (UGDS), log-x. Locator by size.
Right column: C150_4 vs share of Pell recipients (PCTPELL) with a
              lowess national expectation. Locator by who is served.

Population: institutions with PREDDEG = 3 (predominantly bachelor's),
UGDS > 0, non-null C150_4. UTSA (UNITID 229027) starred; UT System /
Texas peers labeled with official short names.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

import pg

HERE = Path(__file__).resolve().parent
FIG_DIR = HERE.parent / "figures" / "paper0"
UTSA_UNITID = 229027

VINTAGE_SHORT = {
    "2019_20": "2019-20 baseline",
    "2024_25": "2024-25 current",
}

BLUE, RED, GRAY, YELLOW = "#2a78d6", "#e34948", "#c3c2b7", "#eda100"
INK, INK_MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"

# name -> (short label, dx pt, dy pt, ha) - offsets tuned to avoid the
# tight UT-System cluster around 25-38k undergraduates
TX_PEERS = {
    "The University of Texas at Austin": ("UT Austin", 6, 5, "left"),
    "Texas A & M University-College Station": ("Texas A&M", 6, 5, "left"),
    "University of Houston": ("U. Houston", 8, -4, "left"),
    "Texas State University": ("Texas State U", -6, 10, "right"),
    "The University of Texas at El Paso": ("UT El Paso", -10, -16, "right"),
    "The University of Texas Rio Grande Valley":
        ("UT Rio Grande Valley", 2, 14, "left"),
    "Texas Tech University": ("Texas Tech", 6, 6, "left"),
}

plt.rcParams.update({"pdf.fonttype": 42, "font.family": "sans-serif",
                     "text.color": INK})

SQL = """
select unitid, instnm, stabbr, control, ugds, c150_4, pctpell
from scorecard.institution
where data_year = %s and preddeg = 3 and ugds > 0
  and c150_4 is not null
"""


def load(vintage: str):
    """Rows as parallel lists; cross-referencing stays in SQL."""
    with pg.connect() as cn:
        rows = cn.execute(SQL, (vintage,)).fetchall()
    unitid = [r[0] for r in rows]
    instnm = [r[1] for r in rows]
    control = [r[3] for r in rows]
    ugds = np.array([r[4] for r in rows], dtype=float)
    c150 = np.array([r[5] for r in rows], dtype=float)
    pell = np.array([np.nan if r[6] is None else r[6] for r in rows],
                    dtype=float)
    return unitid, instnm, control, ugds, c150, pell


LOWESS_FRAC = 0.4     # share of the institutions in each local fit


def _lowess(x, y, frac=LOWESS_FRAC):
    from statsmodels.nonparametric.smoothers_lowess import lowess
    fit = lowess(y, x, frac=frac, return_sorted=True)
    return fit[:, 0], fit[:, 1]


def _scatter(ax, x, y, control, logx=False):
    colors = {1: BLUE, 2: YELLOW, 3: GRAY}
    labels = {1: "public", 2: "private nonprofit", 3: "for-profit"}
    ctl = np.array(control)
    for c in (3, 2, 1):
        m = ctl == c
        ax.scatter(x[m], y[m], s=9, color=colors[c], alpha=0.35,
                   edgecolors="none", label=labels[c], zorder=2)
    if logx:
        ax.set_xscale("log")
    ax.grid(color=GRID, linewidth=0.6, zorder=0)
    for s in ax.spines.values():
        s.set_color(INK_MUTED)
    ax.tick_params(labelsize=15, color=INK_MUTED)
    ax.set_ylim(0, 1)
    ax.set_ylabel("completion within 150% of normal time", fontsize=17)


WEIGHTED_CENTROID_LABEL = "UGDS-weighted centroid"
GEOMETRIC_CENTROID_LABEL = "unweighted mean (per institution)"


def _legend_handles(with_lowess: bool) -> list:
    """Custom proxy handles: full-opacity, sized for legibility (the
    plotted points are small and semi-transparent to avoid overplotting;
    the legend swatches are not)."""
    handles = [
        Line2D([], [], marker="o", ls="none", color=GRAY, markersize=9,
              label="for-profit"),
        Line2D([], [], marker="o", ls="none", color=YELLOW, markersize=9,
              label="private nonprofit"),
        Line2D([], [], marker="o", ls="none", color=BLUE, markersize=9,
              label="public"),
    ]
    if with_lowess:
        handles.append(Line2D([], [], color=INK, lw=2.0,
                              label="national expectation (lowess)"))
    handles.append(Line2D([], [], marker="s", ls="none", color="black",
                          markersize=10, markeredgecolor="white",
                          markeredgewidth=1.0, label=WEIGHTED_CENTROID_LABEL))
    handles.append(Line2D([], [], marker="o", ls="none", color="black",
                          markersize=10, markeredgecolor="white",
                          markeredgewidth=1.0, label=GEOMETRIC_CENTROID_LABEL))
    return handles


def _weighted_centroid(x, y, w):
    """Mean position weighted by enrollment (w), i.e. where the average
    STUDENT sits rather than where the average INSTITUTION sits."""
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    if not ok.any():
        return None
    return float(np.average(x[ok], weights=w[ok])), \
        float(np.average(y[ok], weights=w[ok]))


def _geometric_centroid(x, y):
    """Unweighted mean position, one vote per institution regardless of
    enrollment: the geometric centroid of the point cloud."""
    ok = np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        return None
    return float(np.mean(x[ok])), float(np.mean(y[ok]))


def _plot_marker(ax, point, marker, size=130):
    if point is None:
        return
    cx, cy = point
    ax.scatter([cx], [cy], marker=marker, s=size, color="black",
               edgecolors="white", linewidths=1.0, zorder=5)


def _mark(ax, unitid, instnm, x, y):
    """Peer circles + labels and the UTSA star."""
    name_at = {n: i for i, n in enumerate(instnm)}
    for name, (short, dx, dy, ha) in TX_PEERS.items():
        i = name_at.get(name)
        if i is not None and np.isfinite(x[i]):
            ax.scatter(x[i], y[i], s=48, facecolors="none",
                       edgecolors=INK, linewidths=1.1, zorder=4)
            ax.annotate(short, (x[i], y[i]), xytext=(dx, dy),
                        textcoords="offset points", fontsize=13,
                        color=INK, ha=ha, zorder=5)
    try:
        i = unitid.index(UTSA_UNITID)
    except ValueError:
        return
    ax.scatter(x[i], y[i], marker="*", s=340, color=RED,
               edgecolors="white", linewidths=0.8, zorder=6)
    ax.annotate("UT San Antonio", (x[i], y[i]), xytext=(8, -14),
                textcoords="offset points", fontsize=16,
                fontweight="bold", color=RED, zorder=6)


def report(vintage: str) -> dict | None:
    unitid, instnm, control, ugds, c150, pell = load(vintage)
    try:
        i = unitid.index(UTSA_UNITID)
    except ValueError:
        return None
    ok = np.isfinite(pell)
    xs, ys = _lowess(pell[ok], c150[ok])
    expect = float(np.interp(pell[i], xs, ys))
    print(f"[{vintage}] UTSA: UGDS={int(ugds[i]):,} "
          f"C150_4={c150[i]:.3f} PCTPELL={pell[i]:.3f} "
          f"lowess expectation={expect:.3f} "
          f"residual={c150[i] - expect:+.3f}")
    return {"n_institutions": len(unitid), "utsa_ugds": int(ugds[i]),
            "utsa_c150_4": round(float(c150[i]), 3),
            "utsa_pctpell": round(float(pell[i]), 3),
            "lowess_expectation": round(expect, 3),
            "residual": round(float(c150[i]) - expect, 3)}


def _panel_pair(axA, axB, vintage, letterA, letterB, show_legend):
    """One vintage row: size panel (left) + Pell panel (right)."""
    unitid, instnm, control, ugds, c150, pell = load(vintage)
    tag = VINTAGE_SHORT[vintage]

    _scatter(axA, ugds, c150, control, logx=True)
    _mark(axA, unitid, instnm, ugds, c150)
    _plot_marker(axA, _weighted_centroid(ugds, c150, ugds), "s")
    _plot_marker(axA, _geometric_centroid(ugds, c150), "o")
    # fixed range 10^1 .. 10^6.5 so the peer labels sit inside the panel
    axA.set_xlim(10, 10 ** 6.5)
    axA.set_xlabel("undergraduate enrollment (log scale)", fontsize=17)
    axA.set_title(f"{letterA}. By size: {tag}", fontsize=16, color=INK)
    if show_legend:
        axA.legend(handles=_legend_handles(with_lowess=False),
                   loc="upper left", fontsize=12, frameon=False,
                   handletextpad=0.6)

    ok = np.isfinite(pell)
    _scatter(axB, pell[ok], c150[ok], list(np.array(control)[ok]))
    xs, ys = _lowess(pell[ok], c150[ok])
    axB.plot(xs, ys, color=INK, lw=2.0, zorder=3)
    _mark(axB, unitid, instnm, pell, c150)
    _plot_marker(axB, _weighted_centroid(pell, c150, ugds), "s")
    _plot_marker(axB, _geometric_centroid(pell[ok], c150[ok]), "o")
    axB.set_xlabel("share of undergraduates receiving Pell grants",
                   fontsize=17)
    axB.set_title(f"{letterB}. By who is served: {tag}", fontsize=16,
                  color=INK)
    axB.set_ylabel("")
    if show_legend:
        axB.legend(handles=_legend_handles(with_lowess=True),
                   loc="lower left", fontsize=12, frameon=False,
                   handletextpad=0.6)
    return unitid, instnm, control, ugds, c150, pell


def locator() -> str:
    fig, axes = plt.subplots(2, 2, figsize=(13, 11.6))
    rows = {}
    rows["2019_20"] = _panel_pair(axes[0, 0], axes[0, 1], "2019_20",
                                  "A", "B", show_legend=True)
    rows["2024_25"] = _panel_pair(axes[1, 0], axes[1, 1], "2024_25",
                                  "C", "D", show_legend=False)

    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    pdf = FIG_DIR / "figScorecardLocator.pdf"
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(FIG_DIR / "figScorecardLocator.png", dpi=300,
                bbox_inches="tight")
    plt.close(fig)

    with open(FIG_DIR / "figScorecardLocator_data.csv", "w",
              encoding="utf-8") as f:
        f.write("data_year,unitid,instnm,control,ugds,c150_4,pctpell\n")
        for vintage, (unitid, instnm, control, ugds, c150, pell) \
                in rows.items():
            for i in range(len(unitid)):
                nm = instnm[i].replace('"', "'")
                pl = "" if not np.isfinite(pell[i]) else f"{pell[i]:g}"
                f.write(f'{vintage},{unitid[i]},"{nm}",{control[i]},'
                        f'{ugds[i]:g},{c150[i]:g},{pl}\n')

    # persist the headline coordinates and lowess residuals so the
    # declaration's numbers trace to a file rather than to stdout
    import json
    stats = {v: report(v) for v in rows}
    (FIG_DIR / "figScorecardLocator_stats.json").write_text(
        json.dumps(stats, indent=1), encoding="utf-8")

    nb = len(rows["2019_20"][0])
    nc = len(rows["2024_25"][0])
    (FIG_DIR / "figScorecardLocator.tex").write_text(
        "\\begin{figure}[tbp]\n  \\centering\n"
        "    \\includegraphics[width=1\\textwidth]"
        "{figures/paper0/figScorecardLocator.pdf}\n"
        "    \\caption{National position of UTSA among the "
        "predominantly-bachelor's Title IV institutions in the College "
        "Scorecard, at two explicit vintages. Top row (A, B): the "
        f"2019--20 data year ({nb:,} institutions), the pre-perturbation "
        "baseline vintage, whose completion cohorts closed before Fall "
        f"2019. Bottom row (C, D): the 2024--25 data year ({nc:,} "
        "institutions), the most recent completion data in the June 2026 "
        "release; this row reports the legacy pre-merger UTSA reporting "
        "unit. Left column: "
        "first-time full-time completion within 150\\% of normal time "
        "vs.\\ undergraduate "
        "enrollment (log scale). Right column: completion vs.\\ share "
        "of Pell-grant recipients, with the national lowess expectation; "
        "the gap between UT San Antonio and the curve is a "
        "Pell-conditional descriptive residual. Public institutions "
        "blue, private "
        "nonprofit yellow, for-profit gray; Texas public peers circled. "
        "The black square is the UGDS-weighted institutional centroid "
        "(institutions weighted by current undergraduate enrollment; "
        "the completion coordinate remains a first-time full-time "
        "cohort outcome); the black "
        "circle is the unweighted mean across "
        "institutions in raw coordinates, one vote per institution "
        "regardless of size, plotted on the log axis.}\n"
        "    \\label{fig:figScorecardLocator}\n\\end{figure}\n",
        encoding="utf-8")
    return str(pdf)


def generate() -> None:
    print(" ", locator())


if __name__ == "__main__":
    generate()
