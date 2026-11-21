"""Generated LaTeX tables for the frozen-cohort baseline (Paper 0).

Emits into code/figures/student_success/:
  tabCohortBaseline.tex   headline frozen quantities of the 2014-15 cohort
  tabOddsNaiveCohort.tex  naive vs cohort-restricted odds ratios for the
                          core gateway subjects (the capability-confounding
                          worked example of Section 2)

Every number is computed by the cohort machinery in data.py against the
institutional database; nothing is transcribed by hand.
"""
import json

import numpy as np
from scipy.stats import fisher_exact

import config
import data
from db import cached_query, term_str

CORE =["MAT", "WRC", "AIS"]


def _woolf_ci(a: int, b: int, c: int, d: int) -> str:
    """95% CI for the odds ratio (Woolf / log method)."""
    if min(a, b, c, d) == 0:
        return "--"
    se = np.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    lo, hi = np.exp(np.log((a / c) / (b / d)) + np.array([-1.96, 1.96]) * se)
    return f"[{lo:.2f}, {hi:.2f}]"


def _fmt_p(p: float) -> str:
    if p < 1e-4:
        return "$<10^{-4}$"
    return f"{p:.3f}"


def naive_odds(subject: str) -> tuple:
    """spOddsRatio 2x2 for one subject over the full analysis window.

    Same cache name as data.odds_ratio_all, so existing pkl caches are
    reused. Exposure window Fall 2014-Fall 2019; outcome: no 4000-level
    course; the unexposed group is everyone else in the window, which
    mixes transfer students (credit earned elsewhere) with right-censored
    late entrants.
    """
    name = f"aOddsRatio-{subject}-{config.S_START}-{config.S_END}"
    sql = f"exec spOddsRatio '{subject}', {config.S_START}, {config.S_END}"
    o = cached_query(name, sql, ["k", "n"]).set_index("k")["n"]
    a, b, c, d = (int(o.get(k, 0)) for k in (1, 2, 3, 4))
    or_, p = fisher_exact([[a, b], [c, d]])
    return a, b, c, d, (a / c) / (b / d), p


def cohort_baseline() -> str:
    """Headline frozen quantities of the reference cohort."""
    cohort = data.odds_ratio_cohort()
    tag = (f"{config.COHORT_ENTRY_START}-{config.COHORT_ENTRY_END}-"
           f"{config.COHORT_HORIZON_YEARS:g}y")
    cte = data._COHORT_CTE.format(start=config.COHORT_ENTRY_START,
                                  end=config.COHORT_ENTRY_END)
    outcomes = cached_query(
        f"aCohort-outcomes-{tag}",
        cte + f"""
        select C.IDENTIFIER as id,
               max(case when try_cast(O.CT_SUBJECT as int) > 4000
                        and O.CURRENTTERM <= C.ft +
                            {config.COHORT_HORIZON_YEARS} then 1
                        else 0 end) as has4k
        from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
        group by C.IDENTIFIER""",
        ["id", "has4k"])
    n = len(outcomes)
    n4k = int(outcomes["has4k"].astype(int).sum())
    changed = data.cohort_major_change()
    nch = int(changed.sum())

    core = cohort.set_index("subject").reindex(CORE)
    rows = [
        ("First-time freshmen entering "
         f"{term_str(config.COHORT_ENTRY_START)}--"
         f"{term_str(config.COHORT_ENTRY_END)}", f"{n:,}", "100.0\\%"),
        ("Reached a course numbered above 4000 in window",
         f"{n4k:,}", f"{100 * n4k / n:.1f}\\%"),
        ("Changed major within the window",
         f"{nch:,}", f"{100 * nch / len(changed):.1f}\\%"),
    ]
    for s in CORE:
        served = int(core.loc[s, "served"])
        rows.append((f"Took {s} within the window",
                     f"{served:,}", f"{100 * served / n:.1f}\\%"))

    out = ["\\begin{table}[tbp]", "  \\centering",
           "  \\caption{Baseline quantities of the reference "
           "cohort: first-time freshmen entering "
           f"{term_str(config.COHORT_ENTRY_START)} through "
           f"{term_str(config.COHORT_ENTRY_END)}, outcomes measured "
           "over the declared observation window (the entry term through "
           "the same term four years later, inclusive; "
           "Section~\\ref{sec:data:cohort}), so that every measurement "
           "closed "
           "before Fall 2020. Generated from the institutional database "
           "by \\texttt{cohort\\_tables.py}; nothing is transcribed by "
           "hand.}",
           "  \\label{tab:cohortbaseline}",
           "  \\begin{tabular}{@{}lrr@{}}", "    \\toprule",
           "    Quantity & $N$ & Share of cohort \\\\", "    \\midrule"]
    for name, cnt, pct in rows:
        out.append(f"    {name} & {cnt} & {pct} \\\\")
    out += ["    \\bottomrule", "  \\end{tabular}", "\\end{table}", ""]
    p = config.IMG_DIR / "tabCohortBaseline.tex"
    p.write_text("\n".join(out), encoding="utf-8")
    return str(p)


def odds_naive_vs_cohort() -> str:
    """The capability-confounding worked example, as a generated table."""
    cohort = data.odds_ratio_cohort().set_index("subject")
    out = ["\\begin{table}[tbp]", "  \\centering", "  \\small",
           "  \\caption{Association between core-subject exposure and "
           "having no enrollment in a course numbered above 4000 within "
           "the window, under two designs. The "
           "naive design (columns 2--4; stored procedure over the full "
           f"{term_str(config.S_START)}--{term_str(config.S_END)} "
           "window) compares takers of each subject with every other "
           "student in the window, a group that mixes transfer entrants "
           "holding credit earned elsewhere with right-censored late "
           "entrants. The cohort design (columns 5--7) restricts both "
           "groups to first-time freshmen entering "
           f"{term_str(config.COHORT_ENTRY_START)}--"
           f"{term_str(config.COHORT_ENTRY_END)} with the fixed "
           "observation window of Section~\\ref{sec:data:cohort}. "
           "Odds ratios above one indicate higher odds of "
           "having no such enrollment among takers; $p$ from "
           "Fisher's exact test; 95\\% confidence intervals by the log "
           "(Woolf) method. Generated by \\texttt{cohort\\_tables.py}.}",
           "  \\label{tab:oddsnaivecohort}",
           "  \\begin{tabular}{@{}lrrl@{\\qquad}rrl@{}}", "    \\toprule",
           "    & \\multicolumn{3}{l}{Naive (all students in window)} & "
           "\\multicolumn{3}{l@{}}{Cohort-restricted (entry cohort)} \\\\",
           "    \\cmidrule(r){2-4}\\cmidrule(l){5-7}",
           "    Subject & OR & 95\\% CI & $p$ & OR & 95\\% CI & $p$ \\\\",
           "    \\midrule"]
    stats = {"naive": {}, "cohort": {}}
    for s in CORE:
        a, b, c, d, or_n, p_n = naive_odds(s)
        rc = cohort.loc[s]
        ci_c = _woolf_ci(int(rc["a"]), int(rc["b"]), int(rc["c"]),
                         int(rc["d"]))
        out.append(
            f"    {s} & {or_n:.2f} & {_woolf_ci(a, b, c, d)} & "
            f"{_fmt_p(p_n)} & {rc['odds_ratio']:.2f} & {ci_c} & "
            f"{_fmt_p(float(rc['p']))} \\\\")
        # the same estimates for the text of the manuscript (no cell counts)
        stats["naive"][s] = {"odds_ratio": float(or_n), "p": float(p_n)}
        stats["cohort"][s] = {"odds_ratio": float(rc["odds_ratio"]),
                              "p": float(rc["p"])}
    out += ["    \\bottomrule", "  \\end{tabular}", "\\end{table}", ""]
    p = config.IMG_DIR / "tabOddsNaiveCohort.tex"
    p.write_text("\n".join(out), encoding="utf-8")
    (config.IMG_DIR / "tabOddsNaiveCohort_stats.json").write_text(
        json.dumps(stats, indent=1), encoding="utf-8")
    return str(p)


def generate() -> None:
    print(" ", cohort_baseline())
    print(" ", odds_naive_vs_cohort())


if __name__ == "__main__":
    generate()
