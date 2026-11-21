"""First-year outcomes in introductory courses and later major status.

Descriptive bridge between the major-change flows and the mathematics
gateway (manuscript Section 3.4 and its appendix table). Computed after
the analysis plans of the linked models were frozen; nothing here is a
prespecified test, and nothing here orders a course outcome and a change
of major in time.

POPULATIONS. The reference cohort of the manuscript: first-time freshmen
whose first term falls between Fall 2014 and Fall 2015, observed from the
entry term through the same term four years later (inclusive). Two
populations are reported side by side, because the comparison depends on
which entrants remain observable (REV6, finding 1):

  later-observed   entrants with an enrollment record in a term at or
                   after entry + 1 year. An entrant who stopped out and
                   returned qualifies; the rule is "observed enrolled at
                   least one year after entry", which is weaker than
                   enrollment at the one-year anniversary.
  all              every entrant with a first-year attempt, whatever the
                   later enrollment. An entrant who leaves in the first
                   year has less opportunity to record a change of major
                   (some still do).

EXPOSURE. For each subject, the entrants holding a first attempt in a
course numbered below 2000 during the first year (terms before entry + 1),
split by whether any such first attempt ended in a D, F, withdrawal, or
no-credit outcome (DFW), with the grade codes of the linked models.

OUTCOME. Changed major, with the rules of the cohort tables as first
built (kept for comparability): the first and the last recorded major
within the window differ, a missing value counts as a change, and records
dated before the entry term are admitted. The script reproduces the
published 43.0%, counts the students each rule touches, and repeats the
mathematics comparison under an entry-bounded rule that keeps confirmed
changes only (REV6, finding 6).

Student rows are read into memory, never written, and never printed. The
outputs are aggregates in which every cell holds at least ten students:
    code/figures/student_success/tabMajorChangeDFW.tex
    code/figures/student_success/major_change_dfw.csv
    code/figures/student_success/major_change_dfw_stats.json

The product "entrants with a DFW x rate difference" printed by the first
version of this script was removed: it is a scaled contrast that reads as
a count of attributable changes, which the comparison cannot support
(REV6, finding 2). Scale is shown by the observed number of entrants.

No dataframes: SQL for retrieval, dictionaries and lists for computation.

    python major_change_dfw.py
"""
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import pyodbc

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "module_c"))
import config  # noqa: E402
from mc_figures import SUBJECT_NAME  # noqa: E402

DFW = {"D+", "D", "D-", "F", "W", "NC"}
OK = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "CR"}
INTRO_BELOW = 2000        # course numbers of introductory courses
MIN_TAKERS = 400          # later-observed entrants with a first attempt
MIN_CELL = 10             # disclosure rule
UNDECLARED = "University College"
Z = 1.959964
EPS = 1e-9

SQL = f"""
with C as (
  select IDENTIFIER, min(try_cast(FIRSTTERMCODE as float)) as ft
  from OIR where STUDENTTYPE = 'New'
  group by IDENTIFIER
  having min(try_cast(FIRSTTERMCODE as float))
         between {config.COHORT_ENTRY_START} and {config.COHORT_ENTRY_END}
)
select C.IDENTIFIER, C.ft, O.CURRENTTERM, O.DEPARTMENT, O.SHRTCKN_SUBJ_CODE,
       try_cast(O.CT_SUBJECT as int), O.SHRTCKG_GRDE_CODE_FINAL
from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
where O.CURRENTTERM <= C.ft + {config.COHORT_HORIZON_YEARS}
"""


def _student(s, bounded):
    """flags and first-year first attempts of one student

    bounded=False: the rules of the cohort tables (records before the
    entry term admitted; a missing major endpoint counts as a change).
    bounded=True: records from the entry term on; `changed` is None when
    an endpoint is missing, so that only confirmed changes are counted.
    """
    ft = s["ft"]
    ts = sorted(t for t in s["terms"] if not bounded or t >= ft - EPS)
    first = sorted(x or "" for x in s["terms"][ts[0]])[0] or None
    last = sorted(x or "" for x in s["terms"][ts[-1]])[0] or None
    if first is None or last is None:
        changed = None if bounded else True
    else:
        changed = first != last
    took = {}
    for (subj, num), by_term in s["att"].items():
        if num >= INTRO_BELOW:
            continue
        terms = [t for t in by_term if not bounded or t >= ft - EPS]
        if not terms:
            continue
        t0 = min(terms)                      # the first attempt
        if t0 >= ft + 1.0 - EPS:
            continue
        valid = [c for c in by_term[t0] if c in DFW or c in OK]
        if valid:
            took[subj] = took.get(subj, False) or any(c in DFW for c in valid)
    return {"changed": changed,
            "persisted": ts[-1] >= ft + 1.0 - EPS,
            "undeclared": first == UNDECLARED,
            "took": took,
            "pre_entry": min(s["terms"]) < ft - EPS,
            "missing_endpoint": first is None or last is None,
            "tie": (len(s["terms"][ts[0]]) > 1) or (len(s["terms"][ts[-1]]) > 1)}


def read():
    """the course records of the reference cohort, one entry per student:
    entry term, recorded departments by term, and final grade codes by
    course and term. Rows stay in memory and identifiers are dropped."""
    with pyodbc.connect(config.CONN_STRING, timeout=20) as cn:
        rows = cn.cursor().execute(SQL).fetchall()
    S = defaultdict(lambda: {"ft": 0.0, "terms": defaultdict(set),
                             "att": defaultdict(lambda: defaultdict(list))})
    for sid, ft, term, dept, subj, num, code in rows:
        s = S[sid]
        s["ft"], term = float(ft), float(term)
        s["terms"][term].add(dept)
        if subj and num is not None:
            s["att"][(subj.strip(), int(num))][term].append((code or "").strip())
    del rows
    return list(S.values())


def load():
    """one record per student under each rule"""
    S = read()
    legacy = [_student(s, False) for s in S]
    bounded = [_student(s, True) for s in S]
    return legacy, bounded


def compare(stu, keep, min_takers=MIN_TAKERS):
    """one row per subject: change of major with and without a DFW;
    students whose change is unknown (None) are left out"""
    out = {}
    subjects = sorted({k for s in stu for k in s["took"]})
    for subj in subjects:
        ids = [s for s in stu if subj in s["took"] and keep(s)
               and s["changed"] is not None]
        if len(ids) < min_takers:
            continue
        d1 = [s for s in ids if s["took"][subj]]
        d0 = [s for s in ids if not s["took"][subj]]
        a = sum(s["changed"] for s in d1)
        b = len(d1) - a
        c = sum(s["changed"] for s in d0)
        e = len(d0) - c
        if min(a, b, c, e) < MIN_CELL:
            continue
        p1, p0 = a / len(d1), c / len(d0)
        se = math.sqrt(p1 * (1 - p1) / len(d1) + p0 * (1 - p0) / len(d0))
        lor = math.log((a * e) / (b * c))
        sl = math.sqrt(1 / a + 1 / b + 1 / c + 1 / e)
        rd = p1 - p0
        out[subj] = {
            "entrants": len(ids), "with_dfw": len(d1),
            "changed_with_dfw": p1, "changed_without": p0,
            "diff": rd, "diff_lo": rd - Z * se, "diff_hi": rd + Z * se,
            "odds_ratio": math.exp(lor), "or_lo": math.exp(lor - Z * sl),
            "or_hi": math.exp(lor + Z * sl)}
    return out


def _s(v, nd=1):
    """signed number in TeX math"""
    t = f"{abs(v):.{nd}f}"
    return f"${'-' if v < 0 else '+'}{t}$"


def _ci(lo, hi, nd=1):
    """interval in TeX math; a sign is printed only when negative"""
    return f"$({lo:.{nd}f},\\,{hi:.{nd}f})$"


def table(sel, full, n_keep, n_all, path):
    def name(k):
        t = SUBJECT_NAME.get(k, k)
        t = t[4:] if t.startswith("the ") else t
        return t.replace(" and criticism", "")

    order = sorted(sel, key=lambda k: -sel[k]["with_dfw"])
    lines = [
        "% Generated by code/student_success/major_change_dfw.py from the",
        "% institutional record (rows in memory only); aggregates with at",
        "% least ten students per cell. Regenerate: python major_change_dfw.py",
        r"\begin{table}[tbp]",
        r"\centering\footnotesize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\caption{First-year outcomes in introductory courses and later",
        r"  major status, by subject, in the reference cohort. For each",
        r"  subject, the entrants holding a first attempt in a course",
        r"  numbered below 2000 during the first year are split by whether",
        r"  any such first attempt ended in a D, F, withdrawal, or no-credit",
        r"  outcome (DFW). Changed major: the first and last recorded majors",
        r"  within the observation window differ",
        r"  (Section~\ref{sec:data:cohort}). Columns 2 to 7 use the "
        f"{n_keep:,}",
        r"  entrants observed enrolled at least one year after entry (a",
        r"  record in a term one year or more after the entry term; an",
        r"  entrant who stopped out and returned qualifies). The last column",
        r"  gives the same difference among all entrants with such an",
        f"  attempt (the cohort holds {n_all:,} entrants), whatever their",
        r"  later enrollment. Parentheses hold 95\% intervals:",
        r"  a Wald interval for a difference, in percentage points, and the",
        r"  log (Woolf) method for the odds ratio. Subjects with at least",
        f"  {MIN_TAKERS} later-observed entrants, ordered by the number with",
        r"  a DFW. An entrant can appear in several rows. The comparisons are",
        r"  unadjusted and descriptive, they were computed after the analysis",
        r"  plans were frozen, and they do not establish the order of the",
        r"  course outcome and the change of major.}",
        r"\label{tab:majorchangedfw}",
        # scaled to the text width: the table is a few points too wide
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{@{}lrrrrccc@{}}",
        r"\toprule",
        r" & \multicolumn{6}{c}{Observed enrolled at least one year after"
        r" entry} & All entrants \\",
        r"\cmidrule(lr){2-7}\cmidrule(l){8-8}",
        r" & & & \multicolumn{2}{c}{Changed major (\%)} & Difference"
        r" & & Difference \\",
        r"\cmidrule(lr){4-5}",
        r"Subject & Entrants & With DFW & with DFW & without & (points)"
        r" & Odds ratio & (points) \\",
        r"\midrule"]
    for k in order:
        r, f = sel[k], full.get(k)
        last = (f"{_s(100 * f['diff'])} "
                f"{_ci(100 * f['diff_lo'], 100 * f['diff_hi'])}"
                if f else "")
        lines.append(
            f"{name(k)[0].upper() + name(k)[1:]}"
            f" & {r['entrants']:,} & {r['with_dfw']:,}"
            f" & {100 * r['changed_with_dfw']:.1f}"
            f" & {100 * r['changed_without']:.1f}"
            f" & {_s(100 * r['diff'])} "
            f"{_ci(100 * r['diff_lo'], 100 * r['diff_hi'])}"
            f" & {r['odds_ratio']:.2f} {_ci(r['or_lo'], r['or_hi'], 2)}"
            f" & {last} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}}", r"\end{table}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    legacy, bounded = load()
    n = len(legacy)
    per = [s for s in legacy if s["persisted"]]
    left = [s for s in legacy if not s["persisted"]]
    res = {
        "later_observed": compare(legacy, lambda s: s["persisted"]),
        "later_observed_declared": compare(
            legacy, lambda s: s["persisted"] and not s["undeclared"]),
        "all": compare(legacy, lambda s: True),
        # entry-bounded records, confirmed changes only (REV6, finding 6)
        "later_observed_bounded_confirmed": compare(
            bounded, lambda s: s["persisted"]),
        "all_bounded_confirmed": compare(bounded, lambda s: True)}

    out = config.IMG_DIR
    out.mkdir(parents=True, exist_ok=True)
    table(res["later_observed"], res["all"], len(per), n,
          out / "tabMajorChangeDFW.tex")
    cols = ["entrants", "with_dfw", "changed_with_dfw", "changed_without",
            "diff", "diff_lo", "diff_hi", "odds_ratio", "or_lo", "or_hi"]
    with open(out / "major_change_dfw.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["population", "subject"] + cols)
        for k, rows in res.items():
            for subj, r in sorted(rows.items(), key=lambda kv: -kv[1]["with_dfw"]):
                w.writerow([k, subj] + [r[c] if isinstance(r[c], int)
                                        else f"{r[c]:.5f}" for c in cols])

    def share(g):
        g = [s for s in g if s["changed"] is not None]
        return sum(s["changed"] for s in g) / len(g)

    known = [s for s in bounded if s["changed"] is not None]
    both = [k for k in res["later_observed"]
            if res["later_observed"][k]["diff_lo"] > 0
            and k in res["all"] and res["all"][k]["diff_lo"] > 0]
    stats = {
        "cohort": n, "changed": sum(s["changed"] for s in legacy),
        "share_changed": share(legacy),
        "later_observed": len(per), "share_changed_later_observed": share(per),
        "not_observed_after_first_year": len(left),
        "share_changed_not_observed_after_first_year": share(left),
        "later_observed_declared": sum(not s["undeclared"] for s in per),
        "rule_counts": {
            "students_with_records_before_entry": sum(
                s["pre_entry"] for s in legacy),
            "students_with_a_missing_major_endpoint": sum(
                s["missing_endpoint"] for s in legacy),
            "students_with_two_majors_in_first_or_last_term": sum(
                s["tie"] for s in legacy),
            "students_with_two_majors_in_first_or_last_term_bounded": sum(
                s["tie"] for s in bounded),
            "bounded_confirmed_students": len(known),
            "bounded_confirmed_share_changed": share(known)},
        "positive_difference_excluding_zero_in_both_populations": both,
        "intro_below": INTRO_BELOW, "min_takers": MIN_TAKERS,
        "min_cell": MIN_CELL,
        "population_definitions": {
            "later_observed": "an enrollment record in a term at or after "
                              "entry + 1 year (a returning stop-out "
                              "qualifies)",
            "all": "every entrant with a first-year first attempt"},
        "results": res}
    (out / "major_change_dfw_stats.json").write_text(
        json.dumps(stats, indent=1), encoding="utf-8")

    print(f"cohort {n:,}; changed {100 * share(legacy):.1f}%; observed a "
          f"year or more after entry {len(per):,} ({100 * share(per):.1f}% "
          f"changed); not observed after the first year {len(left):,} "
          f"({100 * share(left):.1f}% changed)")
    print("rule counts:", stats["rule_counts"])
    print("positive difference, interval above zero in both populations:",
          both)
    for k, rows in res.items():
        print(f"\n{k}")
        for subj in sorted(rows, key=lambda j: -rows[j]["with_dfw"])[:7]:
            r = rows[subj]
            print(f"  {subj:4s} n={r['entrants']:5,d} dfw={r['with_dfw']:5,d} "
                  f"{100 * r['changed_with_dfw']:5.1f} vs "
                  f"{100 * r['changed_without']:5.1f}  diff "
                  f"{100 * r['diff']:+5.1f} ({100 * r['diff_lo']:+.1f} to "
                  f"{100 * r['diff_hi']:+.1f})  OR {r['odds_ratio']:.2f} "
                  f"({r['or_lo']:.2f}-{r['or_hi']:.2f})")
    print(" ", out / "tabMajorChangeDFW.tex")


if __name__ == "__main__":
    main()
