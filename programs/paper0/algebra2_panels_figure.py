"""figAlgebraIIPanels: district Algebra II enrollment per high-school
student against child poverty (panel A) and household income (panel B).

Replaces figAlgebraIIPoverty and figAlgebraIIOA in the manuscript. The
earlier figures divided Algebra II enrollees by all resident children
aged 5-17; the course comparison (course_gradient_figure.py) showed that
measure follows high-school enrollment per resident child. Algebra II is
a high-school course, so the denominator here is estimated high-school
enrollment: total enrollment of the schools serving grades 9-12,
prorated by grade span (code/ingest/crdc_courses.py).

Frame: the districts of the course comparison (SAIPE-matched, at least
200 children aged 5-17, Algebra II reported, no missing-coded course
item). District income is the covariate of oa_figure.py, read from its
backing file figAlgebraIIOA_data.csv (Atlas tract income aggregated to
districts through the EDGE GRF17 land-area shares).

SQL for cross-referencing, lists / numpy arrays for computation, no
dataframes. Writes vector PDF, 300-DPI PNG, TeX snippet with the
canonical caption, backing CSV, and a stats JSON into code/figures/paper0.
"""
import csv
import json
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
GREEN, ORANGE = "#1baf7a", "#eb6834"
INK, INK_MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"
CYCLE, MIN_POP, MIN_STATE_DISTRICTS = "2017-18", 200, 5
Y_MAX = 0.45
NL = "\n"

plt.rcParams.update({"pdf.fonttype": 42, "font.family": "sans-serif",
                     "text.color": INK})

SQL = """
select leaid, state_pc, name, pop_5_17, pov_rate, hs_enr_est, subject,
       enrollees, n_reported, n_missing
from mart.course_poverty
where cycle = %s and pop_5_17 >= %s and pov_rate is not null
"""
SQL_BEXAR = """
select leaid
from (select leaid, avg((cnty = '48029')::int) as f
      from raw_xwalk.edge_school where cycle = %s group by leaid) t
where f > 0.5
"""
# landmark Bexar districts: label offsets (points) in panels A and B
LABELS = {
    "Alamo Heights ISD": ((6, 12, "left"), (8, 10, "left")),
    "Edgewood ISD": ((8, 20, "left"), (-9, 5, "right")),
    "San Antonio ISD": ((10, -18, "left"), (-9, -16, "right")),
    "Northside ISD": ((-7, 10, "right"), (10, 12, "left")),
    "North East ISD": ((-7, -34, "right"), (12, -34, "left")),
}


def _short(name: str) -> str:
    return (name.replace("Independent School District", "ISD")
                .replace("School District", "SD").strip())


def _wls(x, y, w):
    X = np.column_stack([np.ones(len(x)), x])
    b = np.linalg.solve(X.T @ (w[:, None] * X), X.T @ (w * y))
    return float(b[0]), float(b[1])


def _cluster_se(x, y, w, cluster):
    X = np.column_stack([np.ones(len(x)), x])
    A = X.T @ (w[:, None] * X)
    b = np.linalg.solve(A, X.T @ (w * y))
    e = y - X @ b
    groups = np.unique(cluster)
    meat = np.zeros((2, 2))
    for g in groups:
        m = cluster == g
        u = (w[m, None] * X[m]).T @ e[m]
        meat += np.outer(u, u)
    Ai = np.linalg.inv(A)
    V = Ai @ meat @ Ai
    G, N = len(groups), len(x)
    V *= (G / (G - 1)) * ((N - 1) / (N - 2))
    return float(np.sqrt(V[1, 1]))


def _wcorr(x, y, w):
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    return float((w * (x - mx) * (y - my)).sum() / np.sqrt(
        (w * (x - mx) ** 2).sum() * (w * (y - my) ** 2).sum()))


def _spearman(x, y):
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    return float(np.corrcoef(rx, ry)[0, 1])


def figure() -> str:
    with db.connect() as cn, cn.cursor() as cur:
        cur.execute(SQL, (CYCLE, MIN_POP))
        rows = cur.fetchall()
        cur.execute(SQL_BEXAR, (CYCLE,))
        bexar = {r[0] for r in cur.fetchall()}
    d = {}
    for leaid, st, name, pop, pov, hs, subj, enr, nrep, nmiss in rows:
        r = d.setdefault(leaid, {"st": st, "name": name, "pop": float(pop),
                                 "pov": float(pov), "hs": hs, "ok": True,
                                 "alg2": None})
        if nmiss and nmiss > 0:
            r["ok"] = False
        if subj == "alg2" and nrep and nrep > 0:
            r["alg2"] = float(enr)
    keep = [k for k, r in d.items()
            if r["ok"] and r["alg2"] is not None and r["hs"] and r["hs"] > 0]
    leaid = keep
    name = [_short(d[k]["name"]) for k in keep]
    st = np.array([d[k]["st"] for k in keep])
    pop = np.array([d[k]["pop"] for k in keep])
    pov = np.array([d[k]["pov"] for k in keep])
    hs = np.array([float(d[k]["hs"]) for k in keep])
    alg2 = np.array([d[k]["alg2"] for k in keep])
    y = alg2 / hs
    isb = np.array([k in bexar for k in keep])
    n, nb = len(keep), int(isb.sum())

    inc = {}
    with open(FIG_DIR / "figAlgebraIIOA_data.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            inc[r["leaid"]] = float(r["med_hhinc2016_k"])
    income = np.array([inc.get(k, np.nan) for k in keep])
    hasinc = np.isfinite(income)

    # panel A statistics: per high-school student, weights = enrollment
    b0, slope = _wls(pov, y, hs)
    se = _cluster_se(pov, y, hs, st)
    mean = float(alg2.sum() / hs.sum())
    rel10 = 10 * slope / mean
    # the per-resident-child slope on the same frame, for comparison
    c0, cslope = _wls(pov, alg2 / pop, pop)
    cse = _cluster_se(pov, alg2 / pop, pop, st)
    part = {}
    for s in np.unique(st):
        m = st == s
        if int(m.sum()) >= MIN_STATE_DISTRICTS:
            part[s] = float(alg2[m].sum() / hs[m].sum())
    hi, lo = max(part, key=part.get), min(part, key=part.get)
    # panel B statistics: child-weighted correlation, as in the income
    # table of the course comparison
    r_w = _wcorr(income[hasinc], y[hasinc], pop[hasinc])
    r_s = _spearman(income[hasinc], y[hasinc])
    i0, islope = _wls(income[hasinc], y[hasinc], pop[hasinc])
    above = int((y > Y_MAX).sum())
    # quantities cited in the text beside the figure
    ones = np.ones(n)
    _, uslope = _wls(pov, y, ones)
    use = _cluster_se(pov, y, ones, st)
    umean = float(y.mean())
    r_child = _wcorr(income[hasinc], (alg2 / pop)[hasinc], pop[hasinc])
    r_incpov = float(np.corrcoef(income[hasinc], pov[hasinc])[0, 1])

    fig, (axa, axb) = plt.subplots(1, 2, figsize=(16, 7.4), sharey=True,
                                   gridspec_kw={"wspace": 0.05})
    for ax, x, mask, xl in (
            (axa, 100 * pov, np.ones(n, bool),
             "district child poverty rate, ages 5-17 (%)"),
            (axb, income, hasinc,
             "district median household income (thousand dollars)")):
        ax.scatter(x[mask & ~isb], y[mask & ~isb], s=11, color=GRAY,
                   alpha=0.4, edgecolors="none", zorder=2,
                   label=f"U.S. school districts (N={int((mask & ~isb).sum()):,})"
                   if ax is axa else None)
        ax.scatter(x[mask & isb], y[mask & isb], s=75, color=RED,
                   edgecolors="white", linewidths=0.8, zorder=4,
                   label=f"Bexar County (San Antonio) districts (N={nb})"
                   if ax is axa else None)
        ax.set_xlabel(xl, fontsize=17)
        ax.tick_params(labelsize=15, color=INK_MUTED)
        ax.grid(color=GRID, linewidth=0.6, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(INK_MUTED)
    xs = np.linspace(pov.min(), pov.max(), 50)
    axa.plot(100 * xs, b0 + slope * xs, color=INK, lw=2.2, zorder=3,
             label="U.S., enrollment-weighted fit")
    lines = [(hi, GREEN, "highest"), (lo, ORANGE, "lowest")]
    if "TX" not in (hi, lo):
        lines.insert(1, ("TX", BLUE, None))
    for s, col, tag in lines:
        m = st == s
        s0, s1 = _wls(pov[m], y[m], hs[m])
        sx = np.linspace(np.percentile(pov[m], 2), np.percentile(pov[m], 98),
                         40)
        lab = f"{s} ({part[s]:.2f} per student" + (f", {tag})" if tag else ")")
        axa.plot(100 * sx, s0 + s1 * sx, color=col, lw=2.2, zorder=3,
                 label=lab)
    xi = np.linspace(np.percentile(income[hasinc], 0.5),
                     np.percentile(income[hasinc], 99.5), 50)
    axb.plot(xi, i0 + islope * xi, color=INK, lw=2.2, zorder=3)
    axb.set_xlim(0, 155)
    axb.set_xticks([20, 40, 60, 80, 100, 120, 140])
    axa.set_ylim(0, Y_MAX)
    axa.set_ylabel("Algebra II enrollees per high-school student",
                   fontsize=17)
    for ax, k, tag in ((axa, 0, "A"), (axb, 1, "B")):
        ax.text(0.015, 0.975, tag, transform=ax.transAxes, fontsize=22,
                fontweight="bold", va="top", ha="left")
        xv = 100 * pov if k == 0 else income
        for i in np.flatnonzero(isb):
            if name[i] in LABELS and np.isfinite(xv[i]) and y[i] <= Y_MAX:
                dx, dy, ha = LABELS[name[i]][k]
                ax.annotate(name[i], (xv[i], y[i]), xytext=(dx, dy),
                            textcoords="offset points", fontsize=14,
                            color=INK, ha=ha, zorder=5)
    axa.legend(loc="upper right", fontsize=13.5, frameon=True,
               facecolor="white", edgecolor="none", framealpha=0.9)
    axb.text(0.985, 0.975,
             f"child-weighted r = {r_w:.2f}" + NL + f"Spearman = {r_s:.2f}",
             transform=axb.transAxes, fontsize=15, va="top", ha="right")
    fig.subplots_adjust(left=0.065, right=0.99, bottom=0.11, top=0.98)

    pdf = FIG_DIR / "figAlgebraIIPanels.pdf"
    fig.savefig(pdf)
    fig.savefig(FIG_DIR / "figAlgebraIIPanels.png", dpi=300)
    plt.close(fig)

    with open(FIG_DIR / "figAlgebraIIPanels_data.csv", "w", newline="",
              encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["leaid", "name", "pov_rate", "med_hhinc2016_k",
                      "alg2_per_hs_student", "hs_enrollment_est",
                      "pop_5_17", "bexar"])
        for i in range(n):
            out.writerow([leaid[i], name[i], f"{pov[i]:.4f}",
                          "" if not hasinc[i] else f"{income[i]:.2f}",
                          f"{y[i]:.5f}", int(round(hs[i])), int(pop[i]),
                          int(isb[i])])
    stats = {"cycle": CYCLE, "n_districts": n, "n_bexar": nb,
             "n_with_income": int(hasinc.sum()),
             "per_hs_student": {"mean": mean, "slope": slope,
                                "se_state_cluster": se, "z": slope / se,
                                "rel10_pct": rel10},
             "per_resident_child_same_frame": {
                 "slope": cslope, "se_state_cluster": cse,
                 "z": cslope / cse},
             "per_hs_student_unweighted": {
                 "mean": umean, "slope": uslope, "se_state_cluster": use,
                 "z": uslope / use, "rel10_pct": 10 * uslope / umean,
                 "max_ratio": float(y.max()),
                 "n_ratio_above_1": int((y > 1).sum()),
                 "enrollment_share_above_display":
                     float(hs[y > Y_MAX].sum() / hs.sum())},
             "income": {"weighted_pearson": r_w, "spearman": r_s},
             "income_per_resident_child_weighted_pearson": r_child,
             "income_poverty_pearson_unweighted": r_incpov,
             "state_intensity_per_hs_student": {
                 "highest": [hi, part[hi]], "lowest": [lo, part[lo]],
                 "TX": part.get("TX")},
             "districts_above_display": above}
    (FIG_DIR / "figAlgebraIIPanels_stats.json").write_text(
        json.dumps(stats, indent=1), encoding="utf-8")

    tex = [
        "% Canonical caption for figAlgebraIIPanels.pdf",
        "% Generated by: code/paper0/algebra2_panels_figure.py from",
        "% mart.course_poverty (GATEWAY) and figAlgebraIIOA_data.csv.",
        r"\begin{figure}[tbp]",
        r"  \centering",
        r"  \includegraphics[width=\textwidth]{figAlgebraIIPanels.pdf}",
        r"  \caption{District Algebra~II enrollment per high-school student",
        "    (CRDC 2017--18) against (A) the district child poverty rate",
        "    (SAIPE 2017) and (B) district median household income (ACS",
        "    2012--16, the tract covariate distributed with the Opportunity",
        f"    Atlas, aggregated to districts), for the {n:,} districts of the",
        f"    common frame (matched, at least {MIN_POP} children aged 5--17,",
        "    Algebra~II reported, no missing-coded course item). The",
        "    denominator is estimated high-school enrollment: total",
        "    enrollment of the schools serving grades 9--12, prorated by",
        "    grade span. (A) The black line is the U.S. enrollment-weighted",
        f"    least-squares fit, slope ${slope:+.3f}$ per unit of the poverty",
        f"    rate (state-clustered standard error {se:.3f}), which is",
        f"    ${rel10:+.1f}\\%$ of the national mean ({mean:.3f}) per ten",
        "    points of child poverty. Colored lines are the same fit within",
        "    Texas (blue) and within the states with the highest and lowest",
        "    enrollment per high-school student among states with at least",
        f"    {MIN_STATE_DISTRICTS} districts: {hi} ({part[hi]:.2f}, green)",
        f"    and {lo} ({part[lo]:.2f}, orange); Texas holds",
        f"    {part['TX']:.2f}. (B) The {int(hasinc.sum()):,} districts with",
        f"    an income value; the child-weighted correlation is {r_w:.2f}",
        f"    (Spearman {r_s:.2f}). Red: the school districts of Bexar",
        f"    County, Texas ({nb} in the frame, landmark districts labeled).",
        f"    {above} districts above the displayed range are not shown.",
        "    Districts are the units; enrollment counts seats within one",
        "    cycle, with no completion or outcome content.}",
        r"  \label{figAlgebraIIPanels}",
        r"\end{figure}", ""]
    (FIG_DIR / "figAlgebraIIPanels.tex").write_text(NL.join(tex),
                                                    encoding="utf-8")
    print(f"n={n:,} bexar={nb}; per HS student: mean {mean:.4f}, slope "
          f"{slope:+.4f} (SE {se:.4f}), {rel10:+.2f}% per 10 points; per "
          f"child on the same frame: {cslope:+.4f} (SE {cse:.4f}); income "
          f"r={r_w:.3f}, Spearman {r_s:.3f}; above display {above}; "
          f"states hi {hi} {part[hi]:.3f} lo {lo} {part[lo]:.3f} "
          f"TX {part['TX']:.3f}")
    print(f"   unweighted per HS student: mean {umean:.4f}, slope "
          f"{uslope:+.4f} (SE {use:.4f}), {10 * uslope / umean:+.2f}% per "
          f"10 points; max ratio {y.max():.3f}, above 1: "
          f"{int((y > 1).sum())}; income r per resident child "
          f"{r_child:.3f}; income-poverty r (unweighted) {r_incpov:.3f}")
    for i in np.flatnonzero(isb):
        if name[i] in LABELS:
            print(f"   {name[i]:20s} pov {100 * pov[i]:5.1f}% income "
                  f"{income[i]:6.1f}k  per HS student {y[i]:.3f}")
    return str(pdf)


if __name__ == "__main__":
    print(" ", figure())
