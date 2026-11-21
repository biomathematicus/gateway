"""figCalculusPanels: district Calculus enrollment per high-school
student against child poverty (panel A) and household income (panel B),
with the school districts of Bexar County marked.

Manuscript Figure 1. It replaces figAlgebraIIPanels: Algebra II was the
subject of an early hypothesis that the course comparison did not bear
out (its enrollment per high-school student is flat in poverty), and
Calculus is the course whose enrollment is graded in poverty.

Frame: the districts of the course comparison (SAIPE-matched, at least
200 children aged 5-17, Algebra II reported, no missing-coded course
item). Denominator: estimated high-school enrollment (total enrollment
of the schools serving grades 9-12, prorated by grade span;
code/ingest/crdc_courses.py). District income is the covariate of
oa_figure.py, read from figAlgebraIIOA_data.csv (Atlas tract income
aggregated to districts through the EDGE GRF17 land-area shares).

SQL for cross-referencing, lists / numpy arrays for computation, no
dataframes. Writes vector PDF, 300-DPI PNG, TeX snippet with the
canonical caption, backing CSV, and a stats JSON into code/figures/paper0.

    python course_panels_figure.py
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
NAME, SUBJECT, COURSE = "figCalculusPanels", "calculus", "Calculus"
BLUE, RED, GRAY = "#2a78d6", "#e34948", "#c3c2b7"
INK, INK_MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"
CYCLE, MIN_POP = "2017-18", 200
Y_MAX = 0.20
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
    "Alamo Heights ISD": ((10, 4, "left"), (10, 4, "left")),
    "Edgewood ISD": ((8, 10, "left"), (-8, 12, "right")),
    "San Antonio ISD": ((10, 12, "left"), (-9, 6, "right")),
    "Northside ISD": ((14, -17, "left"), (12, -17, "left")),
    "North East ISD": ((-2, 26, "left"), (10, 34, "left")),
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


def _robust_se(x, y, w):
    """heteroskedasticity-robust SE of the weighted slope (one state)"""
    X = np.column_stack([np.ones(len(x)), x])
    A = X.T @ (w[:, None] * X)
    b = np.linalg.solve(A, X.T @ (w * y))
    U = X * (w * (y - X @ b))[:, None]
    Ai = np.linalg.inv(A)
    V = Ai @ (U.T @ U) @ Ai * len(x) / (len(x) - 2)
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
                                 "alg2": False, "y": 0.0})
        if nmiss and nmiss > 0:
            r["ok"] = False
        if subj == "alg2" and nrep and nrep > 0:
            r["alg2"] = True               # the frame of the comparison
        if subj == SUBJECT and enr is not None:
            r["y"] = float(enr)
    keep = [k for k, r in d.items()
            if r["ok"] and r["alg2"] and r["hs"] and r["hs"] > 0]
    name = [_short(d[k]["name"]) for k in keep]
    st = np.array([d[k]["st"] for k in keep])
    pop = np.array([d[k]["pop"] for k in keep])
    pov = np.array([d[k]["pov"] for k in keep])
    hs = np.array([float(d[k]["hs"]) for k in keep])
    enr = np.array([d[k]["y"] for k in keep])
    y = enr / hs
    isb = np.array([k in bexar for k in keep])
    n, nb = len(keep), int(isb.sum())

    inc = {}
    with open(FIG_DIR / "figAlgebraIIOA_data.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            inc[r["leaid"]] = float(r["med_hhinc2016_k"])
    income = np.array([inc.get(k, np.nan) for k in keep])
    hasinc = np.isfinite(income)

    # panel A: per high-school student, weights = high-school enrollment
    b0, slope = _wls(pov, y, hs)
    se = _cluster_se(pov, y, hs, st)
    mean = float(enr.sum() / hs.sum())
    rel10 = 10 * slope / mean
    tx = st == "TX"
    t0, tslope = _wls(pov[tx], y[tx], hs[tx])
    tse = _robust_se(pov[tx], y[tx], hs[tx])
    tmean = float(enr[tx].sum() / hs[tx].sum())
    _, uslope = _wls(pov, y, np.ones(n))
    use = _cluster_se(pov, y, np.ones(n), st)
    # panel B: child-weighted correlation, as in the course comparison
    r_w = _wcorr(income[hasinc], y[hasinc], pop[hasinc])
    r_s = _spearman(income[hasinc], y[hasinc])
    i0, islope = _wls(income[hasinc], y[hasinc], pop[hasinc])
    r_incpov = float(np.corrcoef(income[hasinc], pov[hasinc])[0, 1])
    above = int((y > Y_MAX).sum())
    zero = int((y == 0).sum())

    fig, (axa, axb) = plt.subplots(1, 2, figsize=(16, 7.4), sharey=True,
                                   gridspec_kw={"wspace": 0.05})
    for ax, x, mask, xl in (
            (axa, 100 * pov, np.ones(n, bool),
             "district child poverty rate, ages 5-17 (%)"),
            (axb, income, hasinc,
             # a weighted mean of tract medians: not the median income
             # of the district's households (REV6)
             "district income: weighted mean of tract median\n"
             "household income (thousand dollars)")):
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
    sx = np.linspace(np.percentile(pov[tx], 2), np.percentile(pov[tx], 98), 40)
    axa.plot(100 * sx, t0 + tslope * sx, color=BLUE, lw=2.2, zorder=3,
             label="Texas, enrollment-weighted fit")
    xi = np.linspace(np.percentile(income[hasinc], 0.5),
                     np.percentile(income[hasinc], 99.5), 50)
    axb.plot(xi, i0 + islope * xi, color=INK, lw=2.2, zorder=3)
    axb.set_xlim(0, 155)
    axb.set_xticks([20, 40, 60, 80, 100, 120, 140])
    axa.set_ylim(0, Y_MAX)
    axa.set_ylabel(f"{COURSE} enrollees per high-school student",
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

    pdf = FIG_DIR / f"{NAME}.pdf"
    fig.savefig(pdf)
    fig.savefig(FIG_DIR / f"{NAME}.png", dpi=300)
    plt.close(fig)

    with open(FIG_DIR / f"{NAME}_data.csv", "w", newline="",
              encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["leaid", "name", "pov_rate", "med_hhinc2016_k",
                      f"{SUBJECT}_per_hs_student", "hs_enrollment_est",
                      "pop_5_17", "bexar"])
        for i in range(n):
            out.writerow([keep[i], name[i], f"{pov[i]:.4f}",
                          "" if not hasinc[i] else f"{income[i]:.2f}",
                          f"{y[i]:.5f}", int(round(hs[i])), int(pop[i]),
                          int(isb[i])])
    marks = {name[i]: {"pov_rate": float(pov[i]), "income_k": float(income[i]),
                       "per_hs_student": float(y[i]),
                       "ratio_to_national": float(y[i] / mean)}
             for i in np.flatnonzero(isb) if name[i] in LABELS}
    stats = {"cycle": CYCLE, "subject": SUBJECT, "n_districts": n,
             "n_bexar": nb, "n_with_income": int(hasinc.sum()),
             "districts_reporting_zero": zero,
             "per_hs_student": {"mean": mean, "slope": slope,
                                "se_state_cluster": se, "z": slope / se,
                                "rel10_pct": rel10},
             "per_hs_student_unweighted": {
                 "slope": uslope, "se_state_cluster": use,
                 "rel10_pct": 10 * uslope / float(y.mean())},
             "texas": {"n_districts": int(tx.sum()), "mean": tmean,
                       "slope": tslope, "se_robust": tse,
                       "rel10_pct": 10 * tslope / tmean},
             "income": {"weighted_pearson": r_w, "spearman": r_s},
             "income_poverty_pearson_unweighted": r_incpov,
             "bexar_landmarks": marks,
             "districts_above_display": above}
    (FIG_DIR / f"{NAME}_stats.json").write_text(json.dumps(stats, indent=1),
                                                encoding="utf-8")

    tex = [
        f"% Canonical caption for {NAME}.pdf",
        "% Generated by: code/paper0/course_panels_figure.py from",
        "% mart.course_poverty (GATEWAY) and figAlgebraIIOA_data.csv.",
        r"\begin{figure}[tbp]",
        r"  \centering",
        r"  \includegraphics[width=\textwidth]{" + NAME + ".pdf}",
        r"  \caption{District " + COURSE + " enrollment per high-school",
        "    student (CRDC 2017--18) against (A) the district child poverty",
        "    rate (SAIPE 2017) and (B) district income, the weighted mean of",
        "    tract median household incomes (ACS 2012--16, the tract",
        "    covariate distributed with the Opportunity Atlas; tracts",
        "    weighted by childhood-cohort count times land-area share), for",
        f"    the {n:,} districts of the",
        f"    common frame (matched, at least {MIN_POP} children aged 5--17,",
        "    a high-school course sequence reported, no missing-coded",
        "    course item). The denominator is estimated high-school",
        "    enrollment: total enrollment of the schools serving grades",
        "    9--12, prorated by grade span. (A) The black line is the U.S.",
        f"    enrollment-weighted least-squares fit, slope ${slope:+.3f}$ per",
        f"    unit of the poverty rate (state-clustered standard error",
        f"    {se:.3f}), which is ${rel10:+.1f}\\%$ of the national mean",
        f"    ({mean:.3f}) per ten percentage points of child poverty; the",
        "    blue line is",
        f"    the same fit within Texas ({int(tx.sum())} districts). (B) The",
        f"    {int(hasinc.sum()):,} districts with an income value; the",
        f"    child-weighted correlation is {r_w:.2f} (Spearman {r_s:.2f}).",
        f"    Red: the school districts of Bexar County, Texas ({nb} in the",
        "    frame, landmark districts labeled).",
        f"    {zero:,} districts report no {COURSE} enrollment, and {above}",
        "    above the displayed range are not shown. Districts are the",
        "    units; enrollment counts seats within one cycle, with no",
        "    completion or outcome content.}",
        r"  \label{" + NAME + "}",
        r"\end{figure}", ""]
    (FIG_DIR / f"{NAME}.tex").write_text(NL.join(tex), encoding="utf-8")
    print(f"n={n:,} bexar={nb}; mean {mean:.4f}, slope {slope:+.4f} "
          f"(SE {se:.4f}), {rel10:+.1f}% per 10 points; unweighted "
          f"{uslope:+.4f} (SE {use:.4f}); TX n={int(tx.sum())} slope "
          f"{tslope:+.4f} (robust SE {tse:.4f}), {10 * tslope / tmean:+.1f}%"
          f", TX mean {tmean:.4f}; income r={r_w:.3f}, Spearman {r_s:.3f}; "
          f"zero {zero}; above display {above}; income-poverty r "
          f"{r_incpov:.3f}")
    for k, v in marks.items():
        print(f"   {k:20s} pov {100 * v['pov_rate']:5.1f}% income "
              f"{v['income_k']:6.1f}k  per HS student "
              f"{v['per_hs_student']:.3f}  ({v['ratio_to_national']:.2f}x)")
    return str(pdf)


if __name__ == "__main__":
    print(" ", figure())
