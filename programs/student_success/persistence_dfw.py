"""First-year outcomes in introductory courses and persistence.

Descriptive companion of major_change_dfw.py for the third question of the
manuscript (Section 3.4 and its appendix table): among the entrants of the
reference cohort, how a D, F, withdrawal, or no-credit outcome in a
first-year introductory course relates to being observed enrolled later.
Computed after the analysis plans of the linked models were frozen; nothing
here is a prespecified test, and the comparisons are unadjusted.

POPULATION. The reference cohort: first-time freshmen whose first term
falls between Fall 2014 and Fall 2015, observed from the entry term through
the same term four years later (inclusive). Entrants flagged for the
Coordinated Admission Program (CAP) spend the first year at the institution
and then transfer by the design of that program, so the comparisons use the
entrants without the flag; the CAP entrants are counted separately.

EXPOSURE. As in major_change_dfw.py: for each subject, the entrants holding
a first attempt in a course numbered below INTRO_BELOW during the first
year (terms before entry + 1), split by whether any such first attempt
ended in a D, F, withdrawal, or no-credit outcome (DFW).

OUTCOME. Not observed after the first year: no course record in any term
one year or more after the entry term, through the end of the window. An
entrant who stopped out and returned within the window counts as observed.
The record cannot tell an entrant who left higher education from one who
transferred to another institution.

The course outcome precedes the outcome in time by construction. A
withdrawal can be part of a departure already under way, so mathematics is
also split into failed (a D or F in a completed course) and withdrew or
no credit only.

Student rows are read into memory, never written, and never printed. The
outputs are aggregates in which every cell holds at least MIN_CELL
students:
    figures/student_success/tabPersistenceDFW.tex
    figures/student_success/persistence_dfw.csv
    figures/student_success/persistence_dfw_stats.json
    figures/student_success/figPersistenceDFW.pdf, .png, _data.csv

DFW OUTCOMES. Besides the entrant-by-entrant comparison, the outcomes
themselves are counted: each first attempt of the first year in an
introductory course that ended in a DFW is one outcome. Their shares by
subject are given for all entrants and for the entrants not observed
later, which says how much each subject contributes to the DFW outcomes of
the entrants who did not return.

No dataframes: SQL for retrieval, dictionaries and lists for computation.

    python persistence_dfw.py
"""
import csv
import json
import math
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pyodbc  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

import config
from major_change_dfw import (DFW, EPS, INTRO_BELOW, MIN_CELL, MIN_TAKERS,
                              OK, SUBJECT_NAME, Z, _ci, _s)

GRAY, BLUE, ORANGE = "#c3c2b7", "#2a78d6", "#eb6834"
FAIL = {"D+", "D", "D-", "F"}      # a completed course without credit
FOCUS = "MAT"                      # the subject shown in detail
ONE_YEAR = 1.0                     # term codes count years

SQL = f"""
with C as (
  select IDENTIFIER, min(try_cast(FIRSTTERMCODE as float)) as ft,
         max(CAP) as cap
  from OIR where STUDENTTYPE = 'New'
  group by IDENTIFIER
  having min(try_cast(FIRSTTERMCODE as float))
         between {config.COHORT_ENTRY_START} and {config.COHORT_ENTRY_END}
)
select C.IDENTIFIER, C.ft, C.cap, O.CURRENTTERM, O.SHRTCKN_SUBJ_CODE,
       try_cast(O.CT_SUBJECT as int), O.SHRTCKG_GRDE_CODE_FINAL
from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
where O.CURRENTTERM <= C.ft + {config.COHORT_HORIZON_YEARS}
"""


def read():
    """one entry per student; rows stay in memory, identifiers dropped"""
    with pyodbc.connect(config.CONN_STRING, timeout=20) as cn:
        rows = cn.cursor().execute(SQL).fetchall()
    S = defaultdict(lambda: {"ft": 0.0, "cap": False, "terms": set(),
                             "att": defaultdict(lambda: defaultdict(list))})
    for sid, ft, cap, term, subj, num, code in rows:
        s = S[sid]
        s["ft"], term = float(ft), float(term)
        s["cap"] = s["cap"] or bool(cap)
        s["terms"].add(term)
        if subj and num is not None:
            s["att"][(subj.strip(), int(num))][term].append(
                (code or "").strip())
    del rows
    return [student(s) for s in S.values()]


def student(s):
    """persistence and first-year first attempts of one student"""
    ft, last = s["ft"], max(s["terms"])
    took = {}
    any_level = defaultdict(int)     # DFW outcomes at every course level
    repeats = defaultdict(int)       # introductory, repeated attempts too
    for (subj, num), by_term in s["att"].items():
        if num < INTRO_BELOW:
            for t, codes in by_term.items():
                if t < ft + ONE_YEAR - EPS and any(c in DFW for c in codes):
                    repeats[subj] += 1
        t0 = min(by_term)                       # the first attempt
        if t0 >= ft + ONE_YEAR - EPS:
            continue
        valid = [c for c in by_term[t0] if c in DFW or c in OK]
        if not valid:
            continue
        bad = any(c in DFW for c in valid)
        any_level[subj] += int(bad)
        if num >= INTRO_BELOW:
            continue
        r = took.setdefault(subj, {"dfw": False, "fail": False,
                                   "dfw_term": None, "attempts": 0,
                                   "dfws": 0})
        r["attempts"] += 1           # one course, one first attempt
        if bad:
            r["dfw"] = True
            r["dfws"] += 1
            r["dfw_term"] = (t0 if r["dfw_term"] is None
                             else min(r["dfw_term"], t0))
        if any(c in FAIL for c in valid):
            r["fail"] = True
    return {"cap": s["cap"], "left": last < ft + ONE_YEAR - EPS,
            "last": last, "took": took, "any_level": dict(any_level),
            "repeats": dict(repeats),
            "dfws": sum(r["dfws"] for r in took.values())}


def rate(group):
    """students, students not observed later, and the share; None when a
    cell would hold fewer than MIN_CELL students"""
    n = len(group)
    k = sum(s["left"] for s in group)
    if min(k, n - k) < MIN_CELL:
        return None
    return {"students": n, "not_observed_later": k, "share": k / n}


def contrast(d1, d0):
    """not observed later, with the exposure against without it"""
    a, c = sum(s["left"] for s in d1), sum(s["left"] for s in d0)
    b, e = len(d1) - a, len(d0) - c
    if min(a, b, c, e) < MIN_CELL:
        return None
    p1, p0 = a / len(d1), c / len(d0)
    se = math.sqrt(p1 * (1 - p1) / len(d1) + p0 * (1 - p0) / len(d0))
    lor = math.log((a * e) / (b * c))
    sl = math.sqrt(1 / a + 1 / b + 1 / c + 1 / e)
    rd = p1 - p0
    return {"entrants": len(d1) + len(d0), "with_dfw": len(d1),
            "left_with_dfw": p1, "left_without": p0,
            "diff": rd, "diff_lo": rd - Z * se, "diff_hi": rd + Z * se,
            "odds_ratio": math.exp(lor), "or_lo": math.exp(lor - Z * sl),
            "or_hi": math.exp(lor + Z * sl)}


def by_subject(stu, min_takers=MIN_TAKERS):
    out = {}
    for subj in sorted({k for s in stu for k in s["took"]}):
        ids = [s for s in stu if subj in s["took"]]
        if len(ids) < min_takers:
            continue
        r = contrast([s for s in ids if s["took"][subj]["dfw"]],
                     [s for s in ids if not s["took"][subj]["dfw"]])
        if r:
            out[subj] = r
    return out


def focus(stu, subj=FOCUS):
    """the subject in detail: kind of outcome, outcomes in other subjects,
    and when the students with a DFW were last observed"""
    ids = [s for s in stu if subj in s["took"]]
    t = lambda s: s["took"][subj]                       # noqa: E731
    other = lambda s: any(v["dfw"] for k, v in s["took"].items()  # noqa: E731
                          if k != subj)
    kinds = {
        "no_dfw": [s for s in ids if not t(s)["dfw"]],
        "d_or_f": [s for s in ids if t(s)["fail"]],
        "withdrawal_or_no_credit_only": [s for s in ids
                                         if t(s)["dfw"] and not t(s)["fail"]]}
    cross = {
        "dfw_here_and_elsewhere": [s for s in ids if t(s)["dfw"] and other(s)],
        "dfw_here_only": [s for s in ids if t(s)["dfw"] and not other(s)],
        "dfw_elsewhere_only": [s for s in ids if not t(s)["dfw"] and other(s)],
        "no_dfw_anywhere": [s for s in ids
                            if not t(s)["dfw"] and not other(s)]}
    with_dfw = [s for s in ids if t(s)["dfw"]]
    # no record in any term after the term of the first DFW in the subject
    gone = sum(s["last"] <= t(s)["dfw_term"] + EPS for s in with_dfw)
    assert min(gone, len(with_dfw) - gone) >= MIN_CELL
    return {
        "subject": subj, "entrants": len(ids),
        "by_outcome": {k: rate(v) for k, v in kinds.items()},
        "failed_against_no_dfw": contrast(kinds["d_or_f"], kinds["no_dfw"]),
        "by_dfw_elsewhere": {k: rate(v) for k, v in cross.items()},
        "among_no_dfw_elsewhere": contrast(cross["dfw_here_only"],
                                           cross["no_dfw_anywhere"]),
        "among_dfw_elsewhere": contrast(cross["dfw_here_and_elsewhere"],
                                        cross["dfw_elsewhere_only"]),
        "with_dfw": len(with_dfw),
        "with_dfw_no_record_after_that_term": gone,
        "share_with_dfw_no_record_after_that_term": gone / len(with_dfw)}


def outcomes(stu, named):
    """DFW outcomes counted course by course: each first attempt of the
    first year in an introductory course that ended in a DFW is one
    outcome. Shares by subject among all entrants, among the entrants not
    observed later, and among those observed later; subjects outside
    `named` are pooled."""
    groups = {"all": stu, "not_observed_later": [s for s in stu if s["left"]],
              "observed_later": [s for s in stu if not s["left"]]}
    out = {}
    for name, grp in groups.items():
        n = defaultdict(int)
        a = defaultdict(int)
        for s in grp:
            for subj, r in s["took"].items():
                key = subj if subj in named else "other"
                n[key] += r["dfws"]
                a[key] += r["attempts"]
        total = sum(n.values())
        with_dfw = [s for s in grp if s["dfws"] > 0]
        assert len(with_dfw) >= MIN_CELL
        out[name] = {
            "students": len(grp), "students_with_dfw": len(with_dfw),
            "share_of_students_with_dfw": len(with_dfw) / len(grp),
            "dfw_outcomes": total,
            "first_attempts": sum(a.values()),
            "by_subject": {k: {"dfw_outcomes": n[k], "first_attempts": a[k],
                               "share_of_dfw_outcomes": n[k] / total}
                           for k in sorted(n, key=lambda k: -n[k])
                           if n[k] >= MIN_CELL},
            "students_with_dfw_in_focus": sum(
                1 for s in with_dfw if s["took"].get(FOCUS, {}).get("dfw")),
        }
        out[name]["share_of_students_with_dfw_holding_one_in_focus"] = (
            out[name]["students_with_dfw_in_focus"] / len(with_dfw))
    # the same share for the focus subject with every course level counted
    n_all = defaultdict(int)
    for s in stu:
        for subj, k in s["any_level"].items():
            n_all[subj] += k
    out["every_course_level"] = {
        "dfw_outcomes": sum(n_all.values()),
        "share_in_focus": n_all[FOCUS] / sum(n_all.values())}
    # and with the repeated attempts of the first year counted as well
    # (introductory courses)
    n_rep = defaultdict(int)
    for s in stu:
        for subj, k in s["repeats"].items():
            n_rep[subj] += k
    out["with_repeated_attempts"] = {
        "dfw_outcomes": sum(n_rep.values()),
        "share_in_focus": n_rep[FOCUS] / sum(n_rep.values())}
    return out


def by_count(stu, top=4):
    """not observed later by the number of DFW outcomes of the first year"""
    out = {}
    for k in range(top + 1):
        grp = [s for s in stu if (s["dfws"] == k if k < top
                                  else s["dfws"] >= top)]
        out[str(k) if k < top else f"{top}_or_more"] = rate(grp)
    return out


def scale(stu, subj=FOCUS):
    """how the entrants not observed later and those observed later differ
    in their first-year record of the subject (observed counts)"""
    out = {}
    for name, grp in (("not_observed_later", [s for s in stu if s["left"]]),
                      ("observed_later", [s for s in stu if not s["left"]])):
        took = [s for s in grp if subj in s["took"]]
        dfw = [s for s in took if s["took"][subj]["dfw"]]
        assert min(len(took), len(dfw), len(grp) - len(took)) >= MIN_CELL
        out[name] = {"students": len(grp),
                     "with_first_year_attempt": len(took),
                     "with_first_year_dfw": len(dfw),
                     "share_with_dfw": len(dfw) / len(grp),
                     "share_with_dfw_among_takers": len(dfw) / len(took)}
    return out


def name(k):
    """the name of a subject as tables and figures print it"""
    if k == "other":
        return "other subjects"
    t = SUBJECT_NAME.get(k, k)
    t = t[4:] if t.startswith("the ") else t
    return t.replace(" and criticism", "")


def figure(stats, out):
    """Two aligned panels by subject. A: the share of the first-year DFW
    outcomes that fall in the subject, among all entrants and among the
    entrants not observed later. B: the share not observed later among the
    entrants with and without a DFW in the subject."""
    oc, rows = stats["outcomes"], stats["by_subject"]
    every = oc["all"]["by_subject"]
    gone = oc["not_observed_later"]["by_subject"]
    order = [k for k in every if k != "other"] + ["other"]
    assert all(k in gone for k in order)
    y = list(range(len(order)))
    label = [name(k)[0].upper() + name(k)[1:] for k in order]
    a_all = [100 * every[k]["share_of_dfw_outcomes"] for k in order]
    a_gone = [100 * gone[k]["share_of_dfw_outcomes"] for k in order]

    plt.rcParams.update({"pdf.fonttype": 42, "font.family": "sans-serif",
                         "text.color": config.INK})
    fig, (ax, bx) = plt.subplots(
        1, 2, figsize=(13, 8.8), sharey=True,
        gridspec_kw={"width_ratios": [1.1, 1.0], "wspace": 0.05})
    h = 0.38
    ax.barh([i - h / 2 for i in y], a_all, h * 0.92, color=GRAY, zorder=3)
    ax.barh([i + h / 2 for i in y], a_gone, h * 0.92, color=BLUE, zorder=3)
    ax.text(a_all[0] + 0.4, -h / 2, f"{a_all[0]:.1f}%", va="center",
            fontsize=13, color=config.INK_MUTED)
    ax.text(a_gone[0] + 0.4, h / 2, f"{a_gone[0]:.1f}%", va="center",
            fontsize=13, color=BLUE, fontweight="bold")
    ax.set_yticks(y)
    ax.set_yticklabels(label, fontsize=14, color=config.INK)
    ax.invert_yaxis()
    ax.set_xlabel("share of the first-year DFW outcomes (%)", fontsize=15)
    ax.set_title("A. Where the DFW outcomes are", fontsize=15, loc="left",
                 fontweight="bold")
    ax.legend(handles=[
        Patch(color=GRAY, label=f"all entrants "
              f"({oc['all']['dfw_outcomes']:,} outcomes)"),
        Patch(color=BLUE, label="entrants not observed later "
              f"({oc['not_observed_later']['dfw_outcomes']:,} outcomes)")],
        # beside the rows whose bars are shortest
        loc="center right", bbox_to_anchor=(1.0, 0.30), fontsize=13,
        frameon=False)
    ax.set_xlim(0, max(a_all + a_gone) + 3.6)

    for i, k in enumerate(order):
        if k not in rows:
            continue
        r = rows[k]
        lo, hi = 100 * r["left_without"], 100 * r["left_with_dfw"]
        bx.plot([lo, hi], [i, i], color=config.INK_MUTED, lw=1.2, zorder=2)
        bx.plot(lo, i, "o", ms=8.5, mfc="white", mec=config.INK_MUTED,
                mew=1.6, zorder=3)
        bx.plot(hi, i, "o", ms=9.5, color=ORANGE, zorder=4)
        if i == 0:
            bx.text(lo - 1.2, i, f"{lo:.1f}%", ha="right", va="center",
                    fontsize=13, color=config.INK_MUTED)
            bx.text(hi + 1.2, i, f"{hi:.1f}%", ha="left", va="center",
                    fontsize=13, color=ORANGE, fontweight="bold")
    bx.set_xlim(0, max(100 * r["left_with_dfw"] for r in rows.values()) + 9)
    bx.set_xlabel("entrants not observed later (%)", fontsize=15)
    bx.set_title("B. With and without a DFW in the subject", fontsize=15,
                 loc="left", fontweight="bold")
    bx.legend(handles=[
        Line2D([], [], marker="o", ls="none", ms=8.5, mfc="white",
               mec=config.INK_MUTED, mew=1.6,
               label="entrants without a DFW in the subject"),
        Line2D([], [], marker="o", ls="none", ms=9.5, color=ORANGE,
               label="entrants with a DFW in the subject")],
        loc="lower right", fontsize=13, frameon=False)
    for a in (ax, bx):
        a.tick_params(axis="x", labelsize=13, color=config.INK_MUTED)
        a.tick_params(axis="y", length=0)
        a.grid(axis="x", color=config.GRID, linewidth=0.6, zorder=0)
        a.set_axisbelow(True)
        for side in ("top", "right", "left"):
            a.spines[side].set_visible(False)
        a.spines["bottom"].set_color(config.INK_MUTED)
    fig.savefig(out / "figPersistenceDFW.pdf", bbox_inches="tight")
    fig.savefig(out / "figPersistenceDFW.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    with open(out / "figPersistenceDFW_data.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject", "dfw_outcomes_all_entrants",
                    "share_of_dfw_outcomes_all_entrants",
                    "dfw_outcomes_not_observed_later",
                    "share_of_dfw_outcomes_not_observed_later",
                    "entrants_with_dfw", "not_observed_later_with_dfw",
                    "not_observed_later_without_dfw"])
        for k in order:
            r = rows.get(k)
            w.writerow([k, every[k]["dfw_outcomes"],
                        f"{every[k]['share_of_dfw_outcomes']:.5f}",
                        gone[k]["dfw_outcomes"],
                        f"{gone[k]['share_of_dfw_outcomes']:.5f}",
                        r["with_dfw"] if r else "",
                        f"{r['left_with_dfw']:.5f}" if r else "",
                        f"{r['left_without']:.5f}" if r else ""])


def table(rows, n_pop, n_cohort, n_cap, path):
    order = sorted(rows, key=lambda k: -rows[k]["with_dfw"])
    lines = [
        "% Generated by programs/student_success/persistence_dfw.py from the",
        "% institutional record (rows in memory only); aggregates with at",
        "% least ten students per cell. Regenerate: python persistence_dfw.py",
        r"\begin{table}[tbp]",
        r"\centering\footnotesize",
        r"\setlength{\tabcolsep}{4pt}",
        r"\caption{First-year outcomes in introductory courses and",
        r"  persistence, by subject, in the reference cohort. For each",
        r"  subject, the entrants holding a first attempt in a course",
        f"  numbered below {INTRO_BELOW} during the first year are split by",
        r"  whether any such first attempt ended in a D, F, withdrawal, or",
        r"  no-credit outcome (DFW). Not observed later: no course record in",
        r"  a term one year or more after the entry term, through the end of",
        r"  the observation window (Section~\ref{sec:data:cohort}); an",
        r"  entrant who stopped out and returned counts as observed, and a",
        r"  transfer to another institution cannot be told from leaving",
        f"  higher education. The table uses the {n_pop:,} entrants of the",
        f"  cohort ({n_cohort:,}) without the Coordinated Admission Program",
        f"  flag; the {n_cap:,} entrants with the flag transfer after the",
        r"  first year by the design of that program. Parentheses hold",
        r"  pointwise 95\%",
        r"  intervals: a Wald interval for a difference, in percentage",
        r"  points, and the log (Woolf) method for the odds ratio. Subjects",
        f"  with at least {MIN_TAKERS} entrants holding such an attempt,",
        r"  ordered by the number with a DFW. An entrant can appear in",
        r"  several rows. The comparisons are unadjusted and exploratory:",
        r"  they were computed after the analysis plans were frozen, and",
        r"  the intervals are not adjusted for the number of subjects.}",
        r"\label{tab:persistencedfw}",
        r"\begin{tabular}{@{}lrrrrcc@{}}",
        r"\toprule",
        r" & & & \multicolumn{2}{c}{Not observed later (\%)} & Difference"
        r" & \\",
        r"\cmidrule(lr){4-5}",
        r"Subject & Entrants & With DFW & with DFW & without & (points)"
        r" & Odds ratio \\",
        r"\midrule"]
    for k in order:
        r = rows[k]
        lines.append(
            f"{name(k)[0].upper() + name(k)[1:]}"
            f" & {r['entrants']:,} & {r['with_dfw']:,}"
            f" & {100 * r['left_with_dfw']:.1f}"
            f" & {100 * r['left_without']:.1f}"
            f" & {_s(100 * r['diff'])} "
            f"{_ci(100 * r['diff_lo'], 100 * r['diff_hi'])}"
            f" & {r['odds_ratio']:.2f} {_ci(r['or_lo'], r['or_hi'], 2)} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    cohort = read()
    cap = [s for s in cohort if s["cap"]]
    stu = [s for s in cohort if not s["cap"]]
    rows = by_subject(stu)
    stats = {
        "cohort": len(cohort),
        "cohort_not_observed_later": sum(s["left"] for s in cohort),
        "cap": rate(cap),
        "population": rate(stu),
        "population_definition": "entrants of the reference cohort without "
                                 "the Coordinated Admission Program flag",
        "outcome_definition": "no course record in a term one year or more "
                              "after the entry term, within the window (a "
                              "returning stop-out counts as observed)",
        "intro_below": INTRO_BELOW, "min_takers": MIN_TAKERS,
        "min_cell": MIN_CELL, "dfw_codes": sorted(DFW),
        "fail_codes": sorted(FAIL),
        "by_subject": rows,
        "largest_difference": max(rows, key=lambda k: rows[k]["diff"]),
        "most_entrants_with_dfw": max(rows, key=lambda k: rows[k]["with_dfw"]),
        # a DFW in any introductory course of the first year, among the
        # entrants with a first-year attempt in such a course
        "any_subject": contrast(
            [s for s in stu if any(v["dfw"] for v in s["took"].values())],
            [s for s in stu if s["took"]
             and not any(v["dfw"] for v in s["took"].values())]),
        "focus": focus(stu),
        "scale": scale(stu),
        "outcomes": outcomes(stu, set(rows)),
        "by_number_of_dfw_outcomes": by_count(stu),
        # the same comparison with the CAP entrants included
        "focus_subject_whole_cohort": by_subject(cohort).get(FOCUS),
    }
    out = config.IMG_DIR
    out.mkdir(parents=True, exist_ok=True)
    table(rows, len(stu), len(cohort), len(cap),
          out / "tabPersistenceDFW.tex")
    cols = ["entrants", "with_dfw", "left_with_dfw", "left_without", "diff",
            "diff_lo", "diff_hi", "odds_ratio", "or_lo", "or_hi"]
    with open(out / "persistence_dfw.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject"] + cols)
        for subj, r in sorted(rows.items(), key=lambda kv: -kv[1]["with_dfw"]):
            w.writerow([subj] + [r[c] if isinstance(r[c], int)
                                 else f"{r[c]:.5f}" for c in cols])
    (out / "persistence_dfw_stats.json").write_text(
        json.dumps(stats, indent=1), encoding="utf-8")
    figure(stats, out)

    p, c = stats["population"], stats["cap"]
    print(f"cohort {len(cohort):,}; without the CAP flag {p['students']:,}, "
          f"not observed later {100 * p['share']:.1f}%; with the flag "
          f"{c['students']:,}, not observed later {100 * c['share']:.1f}%")
    for subj in sorted(rows, key=lambda j: -rows[j]["with_dfw"])[:8]:
        r = rows[subj]
        print(f"  {subj:4s} n={r['entrants']:5,d} dfw={r['with_dfw']:5,d} "
              f"{100 * r['left_with_dfw']:5.1f} vs {100 * r['left_without']:5.1f}"
              f"  diff {100 * r['diff']:+5.1f} ({100 * r['diff_lo']:+.1f} to "
              f"{100 * r['diff_hi']:+.1f})  OR {r['odds_ratio']:.2f}")
    f_ = stats["focus"]
    print(FOCUS, "by outcome:", {k: (v["students"], round(100 * v["share"], 1))
                                 for k, v in f_["by_outcome"].items()})
    print(FOCUS, "by DFW elsewhere:",
          {k: (v["students"], round(100 * v["share"], 1))
           for k, v in f_["by_dfw_elsewhere"].items()})
    print(f"{FOCUS}: {f_['with_dfw']:,} with a DFW; "
          f"{100 * f_['share_with_dfw_no_record_after_that_term']:.1f}% have "
          "no record after that term")
    print("scale:", {k: (v["students"], v["with_first_year_dfw"],
                         round(100 * v["share_with_dfw"], 1))
                     for k, v in stats["scale"].items()})
    print(" ", out / "tabPersistenceDFW.tex")


if __name__ == "__main__":
    main()
