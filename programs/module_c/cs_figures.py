"""Class-size addendum: figure and table from the released aggregates.

    python cs_figures.py registered      (or: dryrun)
    python cs_figures.py registered rev5   registered estimates with the
                                           corrected intervals of
                                           rev5_class_size.py; written to
                                           class_size/rev5/

figClassSizeLadder     (A) mathematics: the size coefficient as the
                       comparison tightens; (B) the primary coefficient
                       in every subject
tabClassSizeScenario   the 45-student cap scenario

Captions take their numbers from the tables, so no number is typed by
hand. Reads only files under code/figures/module_c/class_size/.
"""
import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

from mc_figures import SUBJECT_NAME

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "figures" / "module_c" / "class_size"
BLUE, RED, GRAY = "#2a78d6", "#e34948", "#898781"
INK, INK_MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"
plt.rcParams.update({"pdf.fonttype": 42, "font.family": "sans-serif",
                     "text.color": INK})
NL = "\n"
LADDER = [("m0", "all sections" + NL + "of the subject"),
          ("m1", "same course," + NL + "same term"),
          ("m2", "+ student preparation" + NL + "and background"),
          ("m3", "+ instructor effects" + NL + "(primary model)")]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    return float(v) if v not in ("", None) else np.nan


def tc(G):
    """95% critical value on G - 1 degrees of freedom (G instructors)"""
    return float(stats.t.ppf(0.975, max(int(G) - 1, 1)))


def style(ax):
    ax.axvline(0, color=INK_MUTED, lw=1.0, zorder=1)
    ax.grid(axis="x", color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=14, color=INK_MUTED)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK_MUTED)
    ax.tick_params(axis="y", length=0)


def sgn(v, d=3):
    return f"${v:+.{d}f}$"


def corrections(fix):
    """corrected intervals written by rev5_class_size.py, or None"""
    if fix is None:
        return None
    joint = {(r["outcome"], r["summary"]): r
             for r in read(fix / "cs_pooled_joint.csv")}
    return {"joint": joint, "contrasts": read(fix / "cs_contrasts.csv"),
            "sizes": read(fix / "cs_section_sizes.csv")}


def figure(out, fix=None):
    dest, cor = fix or out, corrections(fix)
    prim = read(out / "cs_primary.csv")
    sfe = {(r["outcome"], r["term"]): r for r in read(out / "cs_student_fe.csv")}
    pooled = {(r["outcome"], r["class"], r["model"]): r
              for r in read(out / "cs_pooled.csv")}
    proj = {r["subject"]: r for r in read(out / "cs_projection.csv")
            if r["outcome"] == "dfw"}
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    g = {r["subject"]: r for r in prim if r["outcome"] == "grade"}
    d = {r["subject"]: r for r in prim if r["outcome"] == "dfw"}
    mat = g["MAT"]
    F = 20.0
    MINUS = "\u2212"

    fig = plt.figure(figsize=(17.0, 10.6))
    axa = fig.add_axes([0.172, 0.150, 0.183, 0.745])
    axb = fig.add_axes([0.497, 0.150, 0.190, 0.745])
    axc = fig.add_axes([0.722, 0.150, 0.190, 0.745])

    # (A) the mathematics ladder
    rows = [(lab, fnum(mat[k]), fnum(mat[k + "_hw"]), k == "m3")
            for k, lab in LADDER]
    sf = sfe[("grade", "log2_size_MAT")]
    rows.append(("same student" + NL + "across courses", fnum(sf["estimate"]),
                 fnum(sf["cluster_t_half_width"]), False))
    ya = np.linspace(len(g) - 0.9, 1.5, len(rows))
    for yi, (lab, b_, hw, main) in zip(ya, rows):
        col = RED if main else INK
        axa.plot([b_ - hw, b_ + hw], [yi, yi], color=col, lw=2.6, zorder=2,
                 solid_capstyle="round")
        axa.scatter([b_], [yi], s=230, color=col, edgecolors="white",
                    linewidths=1.3, zorder=3)
        axa.annotate(f"{b_:+.3f}".replace("-", MINUS), (b_, yi),
                     xytext=(0, 16),
                     textcoords="offset points", ha="center",
                     fontsize=F - 2, color=col)
    axa.set_yticks(ya)
    axa.set_yticklabels([r[0] for r in rows], fontsize=F - 1)
    style(axa)
    axa.tick_params(labelsize=F - 2)
    axa.set_xlabel("grade points per doubling" + NL + "of section size",
                   fontsize=F - 2)
    axa.set_title("A   Mathematics", fontsize=F + 3, loc="left", pad=14,
                  fontweight="bold")

    # (B) the primary coefficient, subjects ordered by entrants served
    subj = sorted(g, key=lambda k: -int(g[k]["rows"]))
    # the caption expands the codes itself, so the figure reads alone
    key = "; ".join(f"{k}, {SUBJECT_NAME.get(k, k)}" for k in subj)
    n = {k: int(g[k]["rows"]) for k in subj}
    nmax, ntot = max(n.values()), sum(n.values())
    yb = np.arange(len(subj), 0, -1).astype(float)
    ybot = -0.3
    tr = axb.get_yaxis_transform()
    for yi, k in zip(yb, subj):
        b_, hw = fnum(g[k]["m3"]), fnum(g[k]["m3_hw"])
        col = RED if k == "MAT" else BLUE
        hit = g[k]["bh_m3"] == "1"
        axb.plot([b_ - hw, b_ + hw], [yi, yi], color=col, lw=2.0,
                 alpha=0.9, zorder=2, solid_capstyle="round")
        axb.scatter([b_], [yi], s=55 + 420 * n[k] / nmax, zorder=3,
                    linewidths=1.7, facecolors=col if hit else "white",
                    edgecolors=col)
        axb.text(-0.31, yi, k, transform=tr, ha="right", va="center",
                 fontsize=F - 2, color=RED if k == "MAT" else INK,
                 fontweight="bold" if k == "MAT" else "normal")
        axb.text(-0.04, yi, f"{n[k]:,}", transform=tr, ha="right",
                 va="center", fontsize=F - 5, color=INK_MUTED)
    p = pooled[("grade", "all", "m3")]
    pb, lo, hi = fnum(p["pooled"]), fnum(p["lo"]), fnum(p["hi"])
    if cor:
        j = cor["joint"][("grade", "pooled M3, all")]
        lo, hi = fnum(j["lo_joint"]), fnum(j["hi_joint"])
    axb.plot([lo, hi], [ybot, ybot], color=INK, lw=2.8, zorder=2,
             solid_capstyle="round")
    axb.scatter([pb], [ybot], s=170, marker="D", color=INK,
                edgecolors="white", linewidths=1.3, zorder=3)
    axb.text(-0.385, ybot, f"all {len(subj)}", transform=tr, ha="right",
             va="center", fontsize=F - 2)
    axb.text(-0.04, ybot, f"{ntot:,}", transform=tr, ha="right",
             va="center", fontsize=F - 5, color=INK_MUTED)
    axb.text(-0.04, len(subj) + 0.75, "first attempts", transform=tr,
             ha="right", va="bottom", fontsize=F - 5, color=INK_MUTED)
    reach = {k: abs(fnum(g[k]["m3"])) + fnum(g[k]["m3_hw"]) for k in subj}
    lim = np.percentile(list(reach.values()), 90)
    axb.set_xlim(-lim, lim)
    axb.set_xlabel("grade points per doubling" + NL + "of section size",
                   fontsize=F - 2)
    axb.set_title("B   Per student", fontsize=F + 3, loc="left", pad=14,
                  fontweight="bold")

    # (C) the registered cap scenario on the scale of the institution
    t = dict(res["scenario_all_subjects"])
    if cor:
        j = cor["joint"][("dfw", "cap scenario, DFW outcomes per cohort, "
                          "all subjects")]
        t["lo"], t["hi"] = fnum(j["lo_joint"]), fnum(j["hi_joint"])
    for yi, k in zip(yb, subj):
        r = proj[k]
        v, a_, b_ = (fnum(r["dfw_outcomes_per_cohort"]),
                     fnum(r["per_cohort_lo"]), fnum(r["per_cohort_hi"]))
        col = RED if k == "MAT" else BLUE
        hit = d[k]["bh_m3"] == "1"
        axc.plot([a_, b_], [yi, yi], color=col, lw=2.0, alpha=0.9,
                 zorder=2, solid_capstyle="round")
        axc.scatter([v], [yi], s=150, zorder=3, linewidths=1.7,
                    facecolors=col if hit else "white", edgecolors=col)
        axc.text(1.04, yi, f"+{fnum(r['sections_added_per_year']):,.0f}",
                 transform=axc.get_yaxis_transform(), ha="left",
                 va="center", fontsize=F - 5, color=INK_MUTED)
    axc.plot([t["lo"], t["hi"]], [ybot, ybot], color=INK, lw=2.8, zorder=2,
             solid_capstyle="round")
    axc.scatter([t["dfw_outcomes_per_cohort"]], [ybot], s=170, marker="D",
                color=INK, edgecolors="white", linewidths=1.3, zorder=3)
    axc.text(1.04, ybot, f"+{t['sections_added_per_year']:,.0f}",
             transform=axc.get_yaxis_transform(), ha="left", va="center",
             fontsize=F - 5, color=INK_MUTED)
    axc.text(1.04, len(subj) + 0.75, "sections" + NL + "added" + NL
             + "per year", transform=axc.get_yaxis_transform(), ha="left",
             va="bottom", fontsize=F - 5, color=INK_MUTED,
             linespacing=1.05)
    top = max([abs(t["lo"]), abs(t["hi"])]
              + [abs(fnum(proj[k][c])) for k in subj
                 for c in ("per_cohort_lo", "per_cohort_hi")])
    limc = 50 * np.ceil(top / 50)
    axc.set_xlim(-limc, limc)
    axc.set_xlabel("DFW outcomes per cohort" + NL
                   + "if sections are capped at "
                   + f"{res['cap']}", fontsize=F - 2)
    axc.set_title("C   Institution", fontsize=F + 3, loc="left", pad=14,
                  fontweight="bold")
    for ax in (axb, axc):
        style(ax)
        ax.tick_params(labelsize=F - 2)
        ax.set_yticks([])
    for ax in (axa, axb, axc):
        ax.set_ylim(ybot - 0.9, len(subj) + 0.7)
    fig.savefig(dest / "figClassSizeLadder.pdf")
    fig.savefig(dest / "figClassSizeLadder.png", dpi=300)
    plt.close(fig)

    b0, b3, se3 = fnum(mat["m0"]), fnum(mat["m3"]), fnum(mat["m3_hw"])
    d3, dse = fnum(d["MAT"]["m3"]), fnum(d["MAT"]["m3_hw"])
    hits = sum(1 for k in subj if g[k]["bh_m3"] == "1")
    hits_d = sum(1 for k in subj if d[k]["bh_m3"] == "1")
    clipped = sum(1 for k in subj if reach[k] > lim)
    p3 = fnum(mat["m3_p_wild"])
    pm = proj["MAT"]
    small = min(subj, key=lambda k: n[k])
    tex = [
        "% Canonical caption for figClassSizeLadder.pdf",
        "% Generated by: code/module_c/cs_figures.py from",
        f"% code/figures/module_c/class_size/{out.name}/cs_primary.csv",
        "% and cs_projection.csv",
        r"\begin{figure}[tbp]",
        r"  \centering",
        # 0.95: the caption expands the subject codes, and at full width
        # the figure with its caption is taller than the page
        r"  \includegraphics[width=0.95\textwidth]{figClassSizeLadder.pdf}",
        r"  \caption{Section size and first-attempt outcomes among",
        "    first-time fall entrants of Fall 2014 to Fall 2018 in",
        "    face-to-face lecture sections of more than 10 students.",
        "    Intervals are 95\\%, from a wild cluster bootstrap over",
        "    instructors (the same-student row uses instructor-clustered",
        "    standard errors). (A) Mathematics",
        f"    ({int(mat['rows']):,} first attempts, {int(mat['students']):,}",
        f"    students, {int(mat['sections']):,} sections,",
        f"    {int(mat['instructors'])} instructors): the difference in",
        "    grade points that goes with a doubling of section size as the",
        "    comparison tightens. Across all sections of the subject the",
        f"    coefficient is {sgn(b0)}; with course-by-term effects, the",
        "    student covariates, and instructor effects (the prespecified",
        f"    primary model, red), it is {sgn(b3)}",
        f"    ({sgn(b3 - se3)} to {sgn(b3 + se3)}; $p={p3:.3f}$), and the",
        f"    matching difference in the DFW rate is ${100 * d3:+.1f}$",
        f"    percentage points (${100 * (d3 - dse):+.1f}$ to",
        f"    ${100 * (d3 + dse):+.1f}$). The last row compares each student",
        "    with the same student in other courses. (B) The primary",
        f"    coefficient in each of {len(subj)} subjects, ordered by the",
        "    first attempts each serves (printed beside the code, from",
        f"    {n[subj[0]]:,} in {subj[0]} to {n[small]:,} in {small}), with",
        "    marker area proportional to that count; filled markers pass",
        "    false-discovery control at $q=0.05$",
        f"    ({hits} of {len(subj)}). The diamond is the random-effects",
        f"    pooled estimate, {sgn(pb)} ({sgn(lo)} to {sgn(hi)})"
        + (", with an interval that includes the covariance between"
           " subject estimates." if cor else ".")
        + (f" The axis is set by the 90th percentile of interval reach;"
           f" {clipped} wider intervals run past it." if clipped else ""),
        "    (C) The same subjects on the scale of the institution: the",
        "    projected change in DFW outcomes per entry cohort if every",
        f"    lecture section above {res['cap']} students were split (the",
        "    scenario of Table~\\ref{tab:classsizescenario}), which",
        "    multiplies each subject's DFW coefficient by the first",
        "    attempts affected and by the change in their section sizes;",
        "    the lecture sections the split would add per year are printed",
        "    at right.",
        f"    Mathematics: ${fnum(pm['dfw_outcomes_per_cohort']):+.0f}$",
        f"    (${fnum(pm['per_cohort_lo']):+.0f}$ to",
        f"    ${fnum(pm['per_cohort_hi']):+.0f}$); all {t['subjects']}",
        f"    subjects (diamond): ${t['dfw_outcomes_per_cohort']:+.0f}$",
        f"    (${t['lo']:+.0f}$ to ${t['hi']:+.0f}$). "
        + ("No subject passes" if hits_d == 0 else f"{hits_d} pass"),
        "    false-discovery control on the DFW coefficient. Every",
        "    estimate is an association conditional on entry. Section",
        "    assignment is administrative, and the projection of panel C",
        "    applies only if the association is the effect of size. Subject",
        f"    codes: {key}.}}",
        r"  \label{figClassSizeLadder}",
        r"\end{figure}", ""]
    (dest / "figClassSizeLadder.tex").write_text(NL.join(tex),
                                                 encoding="utf-8")


def table(out, fix=None):
    dest, cor = fix or out, corrections(fix)
    rows = read(out / "cs_projection.csv")
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    dfw = {r["subject"]: r for r in rows if r["outcome"] == "dfw"}
    grd = {r["subject"]: r for r in rows if r["outcome"] == "grade"}
    thirds = read(out / "cs_projection_mat_thirds.csv")
    years = res["cohorts"][1] - res["cohorts"][0] + 1

    def ci(v, lo, hi, d):
        return (f"${v:+.{d}f}$ {{\\scriptsize(${lo:+.{d}f}$ to "
                f"${hi:+.{d}f}$)}}")

    r, gr = dfw["MAT"], grd["MAT"]
    body = [
        f"    Mathematics & "
        f"{int(r['affected_first_attempts']) / years:,.0f} & "
        f"{ci(fnum(gr['change_among_affected']), fnum(gr['lo']), fnum(gr['hi']), 2)} & "
        f"{ci(fnum(r['change_among_affected']), fnum(r['lo']), fnum(r['hi']), 1)} & "
        f"{ci(fnum(r['dfw_outcomes_per_cohort']), fnum(r['per_cohort_lo']), fnum(r['per_cohort_hi']), 0)} & "
        f"{fnum(r['sections_per_year']):,.0f} & "
        f"{fnum(r['sections_added_per_year']):,.0f} \\\\"]
    for lab in ("lowest third", "middle third", "highest third"):
        g = next(t for t in thirds if t["outcome"] == "grade"
                 and t["entry_math_score"] == lab)
        d = next(t for t in thirds if t["outcome"] == "dfw"
                 and t["entry_math_score"] == lab)
        n = int(d["affected_first_attempts"])
        assert n >= 10, lab
        k = n / years / 100.0
        gv = [fnum(g[c]) for c in ("change_among_affected", "cluster_t_lo",
                                   "cluster_t_hi")]
        dv = [fnum(d[c]) for c in ("change_among_affected", "cluster_t_lo",
                                   "cluster_t_hi")]
        if cor:
            # the same contrasts with their wild cluster bootstrap intervals
            pick = {r["outcome"]: r for r in cor["contrasts"]
                    if r["contrast"] == f"cap scenario, {lab}"}
            for v, r, digits in ((gv, pick["grade"], 3), (dv, pick["dfw"], 3)):
                assert abs(v[0] - fnum(r["estimate"])) < 10 ** -digits, lab
                v[1], v[2] = fnum(r["wild_lo"]), fnum(r["wild_hi"])
        body.append(
            f"    \\quad {lab}$^\\dagger$ & {n / years:,.0f} & "
            f"{ci(*gv, 2)} & {ci(*dv, 1)} & "
            f"{ci(*(k * v for v in dv), 0)} & & \\\\")
    t = dict(res["scenario_all_subjects"])
    if cor:
        j = cor["joint"][("dfw", "cap scenario, DFW outcomes per cohort, "
                          "all subjects")]
        t["lo"], t["hi"] = fnum(j["lo_joint"]), fnum(j["hi_joint"])
    note = (
        ["    $^\\dagger$Rows by third of the entry mathematics score use",
         "    the model with the size-by-score interaction; each is a",
         "    linear contrast of the size coefficient and the interaction",
         "    with its own wild cluster bootstrap interval, computed after",
         "    the plan was frozen in place of the clustered-$t$ intervals",
         "    the plan specified. The projection describes an intervention",
         "    only if section size causes the estimated differences, the",
         "    association is linear in the logarithm of size over the",
         "    split, and added sections are taught as existing ones are;",
         "    the observational models do not establish these conditions.",
         "    The interval of the total includes the covariance between",
         "    subject estimates. The threshold of",
         f"    {res['cap']} students is a scenario value: the record holds",
         "    no enrollment-cap field."]
        if cor else
        ["    $^\\dagger$Rows by third of the entry mathematics",
         "    score use the model with the size-by-score interaction and",
         "    intervals from instructor-clustered standard errors. The",
         "    scenario takes the within-course association as the effect of",
         "    size, linear in the logarithm of size, with added sections",
         "    taught as existing ones are; the total assumes independent",
         "    subject estimates."])
    body.append(r"    \midrule")
    body.append(
        f"    All {t['subjects']} subjects & {t['affected'] / years:,.0f} & & & "
        f"{ci(t['dfw_outcomes_per_cohort'], t['lo'], t['hi'], 0)} & "
        f"{t['sections_per_year']:,.0f} & "
        f"{t['sections_added_per_year']:,.0f} \\\\")
    tex = [
        "% Generated by: code/module_c/cs_figures.py from",
        f"% code/figures/module_c/class_size/{out.name}/cs_projection.csv",
        "% and cs_projection_mat_thirds.csv",
        r"\begin{table}[tbp]",
        r"  \centering",
        r"  \caption{Scenario: every face-to-face lecture section above",
        f"    {res['cap']} students is split into equal sections of",
        f"    {res['cap']} or fewer. Projected changes apply the primary",
        "    within-course coefficient of each subject to the first attempts",
        "    of first-time fall entrants in the affected sections (annual",
        f"    means over the Fall {res['cohorts'][0]} to Fall",
        f"    {res['cohorts'][1]} entry cohorts), with 95\\% intervals from",
        "    the wild cluster bootstrap of the coefficient. Sections per",
        "    year count every lower-division lecture section of the",
        "    subject."] + note[:-1] + [note[-1] + "}",
        r"  \label{tab:classsizescenario}",
        r"  \footnotesize",
        r"  \setlength{\tabcolsep}{2.5pt}",
        r"  \begin{tabular}{lrrrrrr}",
        r"    \toprule",
        r"    & First attempts & Grade & DFW rate, & DFW outcomes &"
        r" \multicolumn{2}{c}{Sections per year} \\",
        r"    & per cohort & points & pct.\ points &"
        r" per cohort & now & added \\",
        r"    \midrule"] + body + [
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}", ""]
    (dest / "tabClassSizeScenario.tex").write_text(NL.join(tex),
                                                   encoding="utf-8")


if __name__ == "__main__":
    o = BASE / (sys.argv[1] if len(sys.argv) > 1 else "registered")
    fx = BASE / sys.argv[2] if len(sys.argv) > 2 else None
    figure(o, fx)
    table(o, fx)
    print(" ", (fx or o) / "figClassSizeLadder.pdf")
    print(" ", (fx or o) / "tabClassSizeScenario.tex")
