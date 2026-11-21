"""figAlgebraIIPoverty: district Algebra II access vs child poverty.

Context exhibit for Paper 0 Section 4 (Module D: source-specific,
standalone, no person-level joins). Reads the pre-joined district view
mart.alg2_poverty in the GATEWAY database (CRDC 2017-18 district
aggregation x SAIPE 2017), applies the robust specification of pipeline
report 024 (pop_5_17 >= 200), fits the population-weighted line with the
report's headline slope, and highlights the school districts of Bexar
County, Texas (San Antonio). District-to-county assignment is the modal
county of the district's schools in the NCES EDGE 2017-18 directory.

Analysis uses SQL for cross-referencing and lists / numpy arrays for
computation; no dataframes. Writes vector PDF, 300-DPI PNG, TeX snippet
with the canonical caption, and the backing CSV into code/figures/paper0.
"""
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gateway import db  # noqa: E402

FIG_DIR = HERE.parent / "figures" / "paper0"

BLUE, RED, GRAY = "#2a78d6", "#e34948", "#c3c2b7"
INK, INK_MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"

CYCLE = "2017-18"
MIN_POP = 200          # report 024 pre-treatment denominator filter
LABEL_TOP = 9          # Bexar districts labeled, by child population

plt.rcParams.update({"pdf.fonttype": 42, "font.family": "sans-serif",
                     "text.color": INK})

SQL_DISTRICTS = """
select leaid, name, pov_rate, alg2_per_child, pop_5_17, state_pc
from mart.alg2_poverty
where cycle = %s and pop_5_17 >= %s
  and pov_rate is not null and alg2_per_child is not null
"""

MIN_STATE_DISTRICTS = 5   # a state fit needs a real district sample
GREEN, ORANGE = "#1baf7a", "#eb6834"

SQL_BEXAR = """
select leaid
from (select leaid, avg((cnty = '48029')::int) as f
      from raw_xwalk.edge_school where cycle = %s group by leaid) t
where f > 0.5
"""


def _short(name: str) -> str:
    return (name.replace("Independent School District", "ISD")
                .replace("School District", "SD").strip())


def figure() -> str:
    with db.connect() as cn, cn.cursor() as cur:
        cur.execute(SQL_DISTRICTS, (CYCLE, MIN_POP))
        rows = cur.fetchall()
        cur.execute(SQL_BEXAR, (CYCLE,))
        bexar = {r[0] for r in cur.fetchall()}

    leaid = [r[0] for r in rows]
    name = [r[1] for r in rows]
    pov = np.array([float(r[2]) for r in rows])
    rate = np.array([float(r[3]) for r in rows])
    kids = np.array([float(r[4]) for r in rows])
    state = np.array([r[5] for r in rows])
    isb = np.array([l in bexar for l in leaid])
    n, nb = len(rows), int(isb.sum())

    def _wls(x, y, w):
        """population-weighted least squares (report 024 headline spec)"""
        X = np.column_stack([np.ones(len(x)), x])
        beta = np.linalg.solve(X.T @ (w[:, None] * X), X.T @ (w * y))
        return float(beta[0]), float(beta[1])

    def _cluster_se(x, y, w, cluster):
        """cluster-robust (sandwich) SE of the WLS slope, with the
        standard G/(G-1) * (N-1)/(N-K) small-sample correction"""
        X = np.column_stack([np.ones(len(x)), x])
        XtWX = X.T @ (w[:, None] * X)
        beta = np.linalg.solve(XtWX, X.T @ (w * y))
        e = y - X @ beta
        groups = np.unique(cluster)
        meat = np.zeros((2, 2))
        for g in groups:
            m = cluster == g
            ug = (w[m, None] * X[m]).T @ e[m]
            meat += np.outer(ug, ug)
        bread = np.linalg.inv(XtWX)
        V = bread @ meat @ bread
        G, N, K = len(groups), len(x), 2
        V *= (G / (G - 1)) * ((N - 1) / (N - K))
        return float(np.sqrt(V[1, 1]))

    b0, slope = _wls(pov, rate, kids)
    se = _cluster_se(pov, rate, kids, state)

    # state Algebra II participation: population-weighted mean enrollees
    # per child; fit lines for Texas and the extreme states
    part = {}
    for s in np.unique(state):
        m = state == s
        if int(m.sum()) >= MIN_STATE_DISTRICTS:
            part[s] = float(np.average(rate[m], weights=kids[m]))
    hi = max(part, key=part.get)
    lo = min(part, key=part.get)

    # broken vertical axis: main panel to BREAK, narrow top band holding
    # the sparse high-ratio tail (Randolph Field ISD at 0.29)
    BREAK = 0.15
    fig, (axt, ax) = plt.subplots(
        2, 1, sharex=True, figsize=(13, 8.5),
        gridspec_kw={"height_ratios": [1, 5], "hspace": 0.06})
    for a in (ax, axt):
        a.scatter(100 * pov[~isb], rate[~isb], s=12, color=GRAY,
                  alpha=0.4, edgecolors="none", zorder=2,
                  label=f"U.S. school districts (N={n - nb:,})"
                        if a is ax else None)
        a.scatter(100 * pov[isb], rate[isb], s=70, color=RED,
                  edgecolors="white", linewidths=0.8, zorder=4,
                  label=f"Bexar County (San Antonio) districts (N={nb})"
                        if a is ax else None)
    xs = np.linspace(pov.min(), pov.max(), 50)
    ax.plot(100 * xs, b0 + slope * xs, color=INK, lw=2.2, zorder=3,
            label="U.S., population-weighted fit")
    lines = [(hi, GREEN, "highest intensity"),
             (lo, ORANGE, "lowest intensity")]
    if "TX" not in (hi, lo):
        lines.insert(1, ("TX", BLUE, None))
    for s, col, tag in lines:
        m = state == s
        sb0, sb1 = _wls(pov[m], rate[m], kids[m])
        sx = np.linspace(np.percentile(pov[m], 2),
                         np.percentile(pov[m], 98), 40)
        lab = f"{s} ({part[s]:.3f} per child"
        lab += f", {tag})" if tag else ")"
        ax.plot(100 * sx, sb0 + sb1 * sx, color=col, lw=2.2, zorder=3,
                label=lab)
    # curated landmark labels with hand-set offsets; the full district
    # list lives in the backing CSV
    offs = {
        "Alamo Heights ISD": (8, 10, "left"),
        "Randolph Field ISD": (10, -5, "left"),
        "Northside ISD": (8, 14, "left"),
        "North East ISD": (2, -26, "left"),
        "San Antonio ISD": (10, -34, "left"),
        "Edgewood ISD": (10, 14, "left"),
        "Somerset ISD": (8, 10, "left"),
    }
    for i in range(n):
        s = _short(name[i])
        if isb[i] and s in offs:
            target = axt if rate[i] > BREAK else ax
            dx, dy, ha = offs[s]
            target.annotate(s, (100 * pov[i], rate[i]), xytext=(dx, dy),
                            textcoords="offset points", fontsize=15,
                            color=INK, ha=ha, zorder=5)
    ax.set_xlabel("district child poverty rate, ages 5-17 (%)", fontsize=17)
    fig.supylabel("Algebra II enrollees per child, ages 5-17",
                  fontsize=17)
    for a in (ax, axt):
        a.tick_params(labelsize=15, color=INK_MUTED)
        a.grid(color=GRID, linewidth=0.6, zorder=0)
        a.set_axisbelow(True)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            a.spines[side].set_color(INK_MUTED)
    ax.set_ylim(0, BREAK)
    ax.set_yticks([0, 0.05, 0.10])
    axt.set_ylim(BREAK, 0.70)
    axt.set_yticks([0.3, 0.5, 0.7])
    axt.spines["bottom"].set_visible(False)
    axt.tick_params(axis="x", length=0)
    # axis-break marks at the join
    d = 0.6
    marks = dict(marker=[(-1, -d), (1, d)], markersize=12,
                 linestyle="none", color=INK_MUTED, mec=INK_MUTED,
                 mew=1.2, clip_on=False)
    axt.plot([0, 1], [0, 0], transform=axt.transAxes, **marks)
    ax.plot([0, 1], [1, 1], transform=ax.transAxes, **marks)
    h, l = ax.get_legend_handles_labels()
    ax.legend(h, l, loc="upper right", fontsize=15, frameon=True,
              facecolor="white", edgecolor="none", framealpha=0.85)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    pdf = FIG_DIR / "figAlgebraIIPoverty.pdf"
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(FIG_DIR / "figAlgebraIIPoverty.png", dpi=300,
                bbox_inches="tight")
    plt.close(fig)

    with open(FIG_DIR / "figAlgebraIIPoverty_data.csv", "w", newline="",
              encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["leaid", "name", "pov_rate", "alg2_per_child",
                      "pop_5_17", "bexar"])
        for i in range(n):
            out.writerow([leaid[i], name[i], f"{pov[i]:.4f}",
                          f"{rate[i]:.5f}", int(kids[i]), int(isb[i])])

    (FIG_DIR / "figAlgebraIIPoverty.tex").write_text(
        "% Canonical caption for figAlgebraIIPoverty.pdf\n"
        "% Generated by: code/paper0/algebra2_figure.py from\n"
        "% mart.alg2_poverty (GATEWAY); spec of pipeline report 024.\n"
        "% Regenerate: python code/paper0/algebra2_figure.py\n"
        "\\begin{figure}[tbp]\n"
        "  \\centering\n"
        "  \\includegraphics[width=\\textwidth]{figAlgebraIIPoverty.pdf}\n"
        "  \\caption{District Algebra II enrollment intensity and child\n"
        "    poverty: Algebra\n"
        "    II enrollees per resident child (CRDC 2017--18 district\n"
        "    aggregation)\n"
        "    against the child poverty rate (SAIPE 2017), for the\n"
        f"    {n:,} matched districts with at least {MIN_POP} children aged\n"
        "    5--17 (the denominator filter of the robust specification;\n"
        "    in smaller districts the CRDC and SAIPE frames mismatch and\n"
        "    ratios exceed one). The\n"
        "    intensity measure counts enrollment relative to all resident\n"
        "    children, mixing grade spans, retakes, and cross-district\n"
        "    attendance. The\n"
        "    black line is the U.S. population-weighted least-squares\n"
        f"    fit, slope ${slope:.3f}$ enrollees per child over the full\n"
        f"    poverty range (state-clustered standard error {se:.3f},\n"
        "    computed alongside the fit).\n"
        "    Colored lines are the same fit within Texas (blue) and\n"
        "    within the states with the highest and lowest Algebra II\n"
        f"    enrollment intensity among states with at least\n"
        f"    {MIN_STATE_DISTRICTS} districts in the frame:\n"
        f"    {hi} ({part[hi]:.3f} enrollees per child, green) and\n"
        f"    {lo} ({part[lo]:.3f}, orange); Texas holds\n"
        f"    {part['TX']:.3f}. Each state line spans its own districts'\n"
        "    poverty range. The vertical axis is broken at 0.15, with the\n"
        "    sparse high-ratio tail compressed into the narrow upper\n"
        "    band. Red: the school\n"
        f"    districts of Bexar County, Texas ({nb} districts present in\n"
        "    the filtered frame, landmark districts labeled), which places\n"
        "    San Antonio on the national\n"
        "    gradient. Districts are the units; no student-level quantity\n"
        "    appears, and enrollment counts seats within a cycle, with no\n"
        "    completion or outcome content.}\n"
        "  \\label{figAlgebraIIPoverty}\n"
        "\\end{figure}\n",
        encoding="utf-8")

    print(f"n={n:,} bexar={nb} slope={slope:.4f} se_cluster={se:.4f} "
          f"z={slope / se:.2f} (report 024 weighted: -0.0524, SE 0.014)")
    return str(pdf)


if __name__ == "__main__":
    print(" ", figure())
