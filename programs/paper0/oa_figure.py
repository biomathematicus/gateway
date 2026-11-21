"""figAlgebraIIOA: district Algebra II access on the Opportunity Atlas
income surface.

Reproducible rebuild of the proposal's co-location claim. Opportunity
Atlas tract values (median household income 2016, context_tract.oa_tract,
2010 tract definitions) are aggregated up to school districts through
the NCES EDGE GRF17 tract-to-district land-area shares
(raw_xwalk.lea_tract_frac, registered source edge_grf_lea_tract),
weighting each tract by share x Atlas child count. The district value
joins mart.alg2_poverty (CRDC 2017-18 x SAIPE 2017) on LEAID under the
robust frame of pipeline report 024 (pop_5_17 >= 200). Bexar County
districts are highlighted as in figAlgebraIIPoverty; the broken vertical
axis matches that figure.

Analysis uses SQL for cross-referencing and lists / numpy arrays for
computation; no dataframes. Writes vector PDF, 300-DPI PNG, TeX snippet,
and backing CSV into code/figures/paper0.
"""
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gateway import db  # noqa: E402

FIG_DIR = HERE.parent / "figures" / "paper0"

RED, GRAY = "#e34948", "#c3c2b7"
INK, INK_MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"

CYCLE = "2017-18"
MIN_POP = 200
BREAK = 0.15

plt.rcParams.update({"pdf.fonttype": 42, "font.family": "sans-serif",
                     "text.color": INK})

SQL = """
with oa as (
  select x.leaid,
         sum(o.med_hhinc2016 * o.pooled_pooled_count * x.share)
           / nullif(sum(o.pooled_pooled_count * x.share), 0) as med_hhinc
  from raw_xwalk.lea_tract_frac x
  join context_tract.oa_tract o on o.geoid_2010 = x.geoid_2010
  where o.med_hhinc2016 is not null and o.pooled_pooled_count is not null
  group by x.leaid)
select a.leaid, a.name, a.alg2_per_child, a.pop_5_17, oa.med_hhinc
from mart.alg2_poverty a join oa on oa.leaid = a.leaid
where a.cycle = %s and a.pop_5_17 >= %s
  and a.alg2_per_child is not null and oa.med_hhinc is not null
"""

SQL_BEXAR = """
select leaid
from (select leaid, avg((cnty = '48029')::int) as f
      from raw_xwalk.edge_school where cycle = %s group by leaid) t
where f > 0.5
"""


def _short(name: str) -> str:
    return (name.replace("Independent School District", "ISD")
                .replace("School District", "SD").strip())


def _wcorr(a, b, w):
    am, bm = np.average(a, weights=w), np.average(b, weights=w)
    cov = np.average((a - am) * (b - bm), weights=w)
    return cov / np.sqrt(np.average((a - am) ** 2, weights=w)
                         * np.average((b - bm) ** 2, weights=w))


def figure() -> str:
    with db.connect() as cn, cn.cursor() as cur:
        cur.execute(SQL, (CYCLE, MIN_POP))
        rows = cur.fetchall()
        cur.execute(SQL_BEXAR, (CYCLE,))
        bexar = {r[0] for r in cur.fetchall()}

    leaid = [r[0] for r in rows]
    name = [r[1] for r in rows]
    rate = np.array([float(r[2]) for r in rows])
    kids = np.array([float(r[3]) for r in rows])
    inc = np.array([float(r[4]) for r in rows]) / 1000.0
    isb = np.array([l in bexar for l in leaid])
    n, nb = len(rows), int(isb.sum())

    r_w = float(_wcorr(inc, rate, kids))
    r_u = float(np.corrcoef(inc, rate)[0, 1])
    rho = float(spearmanr(inc, rate).statistic)

    X = np.column_stack([np.ones(n), inc])
    beta = np.linalg.solve(X.T @ (kids[:, None] * X),
                           X.T @ (kids * rate))

    fig, (axt, ax) = plt.subplots(
        2, 1, sharex=True, figsize=(13, 8.5),
        gridspec_kw={"height_ratios": [1, 5], "hspace": 0.06})
    for a in (ax, axt):
        a.scatter(inc[~isb], rate[~isb], s=12, color=GRAY, alpha=0.4,
                  edgecolors="none", zorder=2,
                  label=f"U.S. school districts (N={n - nb:,})"
                        if a is ax else None)
        a.scatter(inc[isb], rate[isb], s=70, color=RED,
                  edgecolors="white", linewidths=0.8, zorder=4,
                  label=f"Bexar County (San Antonio) districts (N={nb})"
                        if a is ax else None)
    xs = np.linspace(np.percentile(inc, 1), np.percentile(inc, 99), 40)
    ax.plot(xs, beta[0] + beta[1] * xs, color=INK, lw=2.2, zorder=3,
            label="U.S., population-weighted fit")
    offs = {
        "Alamo Heights ISD": (8, 10, "left"),
        "Randolph Field ISD": (10, -5, "left"),
        "Northside ISD": (8, 12, "left"),
        "North East ISD": (6, -40, "left"),
        "San Antonio ISD": (8, -8, "left"),
        "Edgewood ISD": (8, -30, "left"),
        "Somerset ISD": (-8, 12, "right"),
    }
    for i in range(n):
        s = _short(name[i])
        if isb[i] and s in offs:
            target = axt if rate[i] > BREAK else ax
            dx, dy, ha = offs[s]
            target.annotate(s, (inc[i], rate[i]), xytext=(dx, dy),
                            textcoords="offset points", fontsize=15,
                            color=INK, ha=ha, zorder=5)
    ax.set_xlabel("district median household income, 2016 "
                  "(thousands of dollars)", fontsize=17)
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
    ax.set_xlim(np.percentile(inc, 0.2), np.percentile(inc, 99.8))
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
    pdf = FIG_DIR / "figAlgebraIIOA.pdf"
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(FIG_DIR / "figAlgebraIIOA.png", dpi=300,
                bbox_inches="tight")
    plt.close(fig)

    with open(FIG_DIR / "figAlgebraIIOA_data.csv", "w", newline="",
              encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["leaid", "name", "med_hhinc2016_k",
                      "alg2_per_child", "pop_5_17", "bexar"])
        for i in range(n):
            out.writerow([leaid[i], name[i], f"{inc[i]:.2f}",
                          f"{rate[i]:.5f}", int(kids[i]), int(isb[i])])

    (FIG_DIR / "figAlgebraIIOA.tex").write_text(
        "% Canonical caption for figAlgebraIIOA.pdf\n"
        "% Generated by: code/paper0/oa_figure.py from\n"
        "% context_tract.oa_tract x raw_xwalk.lea_tract_frac (GRF17)\n"
        "% x mart.alg2_poverty (GATEWAY).\n"
        "% Regenerate: python code/paper0/oa_figure.py\n"
        "\\begin{figure}[tbp]\n"
        "  \\centering\n"
        "  \\includegraphics[width=\\textwidth]{figAlgebraIIOA.pdf}\n"
        "  \\caption{District Algebra II enrollment intensity on the\n"
        "    Opportunity Atlas\n"
        "    income surface: Algebra II enrollees per resident child (CRDC\n"
        "    2017--18) against median household income (an ACS 2012--16\n"
        "    tract covariate distributed with the Opportunity\n"
        "    Atlas), aggregated from 2010 census tracts to school\n"
        "    districts through the NCES EDGE GRF17 land-area shares\n"
        "    (TIGER 2017 boundaries, school year 2015--16),\n"
        "    weighting each tract by its share and Atlas child count;\n"
        f"    {n:,} districts with at least {MIN_POP} children aged 5--17.\n"
        "    The line is the population-weighted least-squares fit. The\n"
        "    association is positive and weak: population-weighted\n"
        f"    correlation {r_w:.2f}, unweighted {r_u:.2f}, Spearman\n"
        f"    {rho:.2f}. Red: the Bexar County (San Antonio) districts\n"
        f"    in the frame ({nb}), landmark districts labeled. The\n"
        "    vertical axis is broken at 0.15 as in\n"
        "    Figure~\\ref{figAlgebraIIPoverty}. Atlas values are\n"
        "    tract-level area statistics; the exhibit is district-level\n"
        "    context, and no student-level quantity appears.}\n"
        "  \\label{figAlgebraIIOA}\n"
        "\\end{figure}\n",
        encoding="utf-8")

    print(f"n={n:,} bexar={nb} weighted_r={r_w:.3f} unweighted_r={r_u:.3f} "
          f"spearman={rho:.3f} slope_per_$10k={10 * beta[1]:.4f}")
    return str(pdf)


if __name__ == "__main__":
    print(" ", figure())
