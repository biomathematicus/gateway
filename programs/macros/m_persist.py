"""Macros of the persistence comparison: first-year outcomes in
introductory courses and being observed enrolled later, in the reference
cohort (Section 3.4 and Appendix B.7 of the manuscript).

Source: figures/student_success/persistence_dfw_stats.json, written by
programs/student_success/persistence_dfw.py.
"""
from texmacros import J, Macros

TITLE = "Persistence after first-year course outcomes"
SOURCE = "figures/student_success/persistence_dfw_stats.json"


def build():
    s = J("student_success/persistence_dfw_stats.json")
    M = Macros("Persist")
    pop, cap = s["population"], s["cap"]
    rows, f, sc = s["by_subject"], s["focus"], s["scale"]
    assert f["subject"] == "MAT"
    mat = rows["MAT"]

    # ---- the population and its outcome
    assert s["cohort"] == pop["students"] + cap["students"]
    M("PopulationN", pop["students"], "int")
    M("LeftN", pop["not_observed_later"], "int")
    M("LeftPct", 100 * pop["share"], ".1f")
    M("CapN", cap["students"], "int")
    M("CapLeftPct", 100 * cap["share"], ".1f")

    def contrast(name, r):
        M(name + "LeftWithPct", 100 * r["left_with_dfw"], ".1f")
        M(name + "LeftWithoutPct", 100 * r["left_without"], ".1f")
        M(name + "Diff", 100 * r["diff"], "s.1f")
        M(name + "DiffLo", 100 * r["diff_lo"], "s.1f")
        M(name + "DiffHi", 100 * r["diff_hi"], "s.1f")

    # ---- mathematics: entrants with a first-year first attempt
    M("MatN", mat["entrants"], "int")
    M("MatDfwN", mat["with_dfw"], "int")
    M("MatDfwPct", 100 * mat["with_dfw"] / mat["entrants"], ".1f")
    contrast("Mat", mat)
    M("MatOdds", mat["odds_ratio"], ".2f")

    # the kind of outcome: a D or F in a completed course, or a withdrawal
    # or no-credit outcome only
    kind = f["by_outcome"]
    assert (kind["no_dfw"]["students"] + kind["d_or_f"]["students"]
            + kind["withdrawal_or_no_credit_only"]["students"]
            == mat["entrants"])
    M("MatFailN", kind["d_or_f"]["students"], "int")
    contrast("MatFail", f["failed_against_no_dfw"])
    M("MatWithdrewN", kind["withdrawal_or_no_credit_only"]["students"],
      "int")
    M("MatWithdrewLeftPct",
      100 * kind["withdrawal_or_no_credit_only"]["share"], ".1f")
    # entrants with a DFW who hold no record after the term of that course
    M("MatGoneAfterTermPct",
      100 * f["share_with_dfw_no_record_after_that_term"], ".1f")

    # crossed with a DFW in another introductory subject
    cross = f["by_dfw_elsewhere"]
    M("MatBothN", cross["dfw_here_and_elsewhere"]["students"], "int")
    M("MatOnlyN", cross["dfw_here_only"]["students"], "int")
    contrast("MatWithElsewhere", f["among_dfw_elsewhere"])
    contrast("MatAlone", f["among_no_dfw_elsewhere"])
    # the text says the interval of the difference includes zero when the
    # DFW in mathematics stands alone, and excludes it otherwise
    assert f["among_no_dfw_elsewhere"]["diff_lo"] < 0 < f[
        "among_no_dfw_elsewhere"]["diff_hi"]
    assert f["among_dfw_elsewhere"]["diff_lo"] > 0

    # ---- how the entrants not observed later differ in their record
    gone, here = sc["not_observed_later"], sc["observed_later"]
    assert gone["students"] == pop["not_observed_later"]
    assert gone["with_first_year_dfw"] == round(
        mat["left_with_dfw"] * mat["with_dfw"])
    M("LeftMatDfwN", gone["with_first_year_dfw"], "int")
    M("LeftMatDfwPct", 100 * gone["share_with_dfw"], ".1f")
    M("StayN", here["students"], "int")
    M("StayMatDfwPct", 100 * here["share_with_dfw"], ".1f")

    # ---- every introductory subject with enough entrants
    assert s["most_entrants_with_dfw"] == "MAT"
    order = sorted(rows, key=lambda k: -rows[k]["with_dfw"])
    M("Subjects", len(rows), "int")
    M("SubjectsWord", len(rows), "word")
    M("SecondSubjectDfwN", rows[order[1]]["with_dfw"], "int")
    # the text says the difference is positive with an interval above zero
    # in every subject
    assert all(r["diff_lo"] > 0 for r in rows.values())
    diffs = [100 * r["diff"] for r in rows.values()]
    M("DiffMin", min(diffs), ".1f")
    M("DiffMax", max(diffs), ".1f")
    # the text names the first-year seminar and writing composition as
    # subjects where a DFW goes with leaving more often than in mathematics
    for k in ("AIS", "WRC"):
        assert rows[k]["left_with_dfw"] > mat["left_with_dfw"]
        assert rows[k]["diff"] > mat["diff"]
    # subjects whose difference is larger than that of mathematics
    M("SubjectsAboveMatWord",
      sum(r["diff"] > mat["diff"] for r in rows.values()), "word")
    M("MinTakers", s["min_takers"], "int")

    # ---- a DFW in any introductory course of the first year
    a = s["any_subject"]
    M("AnyN", a["entrants"], "int")
    M("AnyDfwN", a["with_dfw"], "int")
    M("AnyDfwPct", 100 * a["with_dfw"] / a["entrants"], ".1f")
    contrast("Any", a)

    # ---- the mathematics comparison with the CAP entrants included
    contrast("MatWholeCohort", s["focus_subject_whole_cohort"])

    # ---- the DFW outcomes themselves: each first attempt of the first
    # year in an introductory course that ended in a DFW is one outcome
    oc = s["outcomes"]
    every, lost, kept = (oc["all"], oc["not_observed_later"],
                         oc["observed_later"])
    assert every["students_with_dfw"] == a["with_dfw"]
    M("Outcomes", every["dfw_outcomes"], "int")
    M("FirstAttempts", every["first_attempts"], "int")
    M("OutcomeRatePct",
      100 * every["dfw_outcomes"] / every["first_attempts"], ".1f")
    # mathematics is the largest single source, among all entrants and
    # among the entrants not observed later
    by_all, by_lost = every["by_subject"], lost["by_subject"]
    named = [k for k in by_all if k != "other"]
    assert max(named, key=lambda k: by_all[k]["dfw_outcomes"]) == "MAT"
    assert max((k for k in by_lost if k != "other"),
               key=lambda k: by_lost[k]["dfw_outcomes"]) == "MAT"
    second = sorted(named, key=lambda k: -by_all[k]["dfw_outcomes"])[1]
    M("MatOutcomes", by_all["MAT"]["dfw_outcomes"], "int")
    M("MatOutcomeSharePct", 100 * by_all["MAT"]["share_of_dfw_outcomes"],
      ".1f")
    M("SecondSubjectOutcomeSharePct",
      100 * by_all[second]["share_of_dfw_outcomes"], ".1f")
    M("MatOutcomeShareWithRepeatsPct",
      100 * oc["with_repeated_attempts"]["share_in_focus"], ".1f")
    # share of the first attempts that end in a DFW: mathematics has the
    # highest among the named subjects
    rate_of = {k: by_all[k]["dfw_outcomes"] / by_all[k]["first_attempts"]
               for k in named}
    assert max(rate_of, key=rate_of.get) == "MAT"
    M("MatOutcomeRatePct", 100 * rate_of["MAT"], ".1f")
    M("MatFirstAttempts", by_all["MAT"]["first_attempts"], "int")

    # the entrants not observed later who hold at least one DFW outcome,
    # and what mathematics contributes to their outcomes
    M("LeftWithDfwN", lost["students_with_dfw"], "int")
    M("LeftWithDfwPct", 100 * lost["share_of_students_with_dfw"], ".1f")
    M("LeftOutcomes", lost["dfw_outcomes"], "int")
    M("LeftMatOutcomes", by_lost["MAT"]["dfw_outcomes"], "int")
    M("LeftMatOutcomeSharePct",
      100 * by_lost["MAT"]["share_of_dfw_outcomes"], ".1f")
    second_lost = sorted((k for k in by_lost if k != "other"),
                         key=lambda k: -by_lost[k]["dfw_outcomes"])[1]
    assert second_lost == "WRC"                  # writing composition
    M("LeftSecondSubjectOutcomeSharePct",
      100 * by_lost[second_lost]["share_of_dfw_outcomes"], ".1f")
    assert lost["students_with_dfw_in_focus"] == gone["with_first_year_dfw"]
    M("LeftWithDfwHoldingMatPct",
      100 * lost["share_of_students_with_dfw_holding_one_in_focus"], ".1f")
    # the same shares among the entrants observed later
    M("StayWithDfwPct", 100 * kept["share_of_students_with_dfw"], ".1f")
    M("StayMatOutcomeSharePct",
      100 * kept["by_subject"]["MAT"]["share_of_dfw_outcomes"], ".1f")

    # ---- not observed later by the number of DFW outcomes
    cnt = s["by_number_of_dfw_outcomes"]
    shares = [cnt[k]["share"] for k in ("0", "1", "2", "3", "4_or_more")]
    assert shares == sorted(shares)              # the share rises throughout
    for key, name in (("0", "None"), ("1", "One"), ("2", "Two"),
                      ("3", "Three"), ("4_or_more", "FourPlus")):
        M(f"LeftPctWith{name}", 100 * cnt[key]["share"], ".1f")
    M("FourPlusN", cnt["4_or_more"]["students"], "int")
    return M.items
