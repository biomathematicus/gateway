"""Macros of the institutional baseline (the university's student records).

Sections 2.1, 2.2, 3.4, 3.5 and Appendices A (institutional descriptives),
B.6, B.7, B.9 of the manuscript: the database description, the reference
cohort of first-time freshmen of Fall 2014 to Fall 2015 and its observation
window, the window audit, first-year outcomes in introductory courses and
major change, relative subject grading among students who change major, the
comparison-group design note, and cohort progression.

Sources (under programs/figures), each with the program that writes it:
  student_success/cohort_window_audit.json      student_success/cohort_window_audit.py
  student_success/major_change_dfw_stats.json   student_success/major_change_dfw.py
  student_success/figHeatmapSubjectMajor-changers_rows.csv
                                                student_success/heatmap.py
  module_c/reference_cohort_notes.json          module_c/cohort_notes.py
Parameters are read from the programs of student_success/ with const().
The counts that the text writes as words are at the end of build(); the
disclosure rule among them is the constant of tools/disclosure_scan.py.
"""
import math

from texmacros import C, J, Macros, const, fmt

TITLE = "Institutional baseline: reference cohort, major change, grading"
SOURCE = ("figures/student_success/cohort_window_audit.json, "
          "major_change_dfw_stats.json, "
          "figHeatmapSubjectMajor-changers_rows.csv; "
          "tabOddsNaiveCohort_stats.json, figChord-MAT-majors_stats.json; "
          "figures/module_c/reference_cohort_notes.json")

SS = "student_success/"


def build():
    M = Macros("Inst")
    audit = J(SS + "cohort_window_audit.json")
    dfw = J(SS + "major_change_dfw_stats.json")
    heat = C(SS + "figHeatmapSubjectMajor-changers_rows.csv")
    notes = J("module_c/reference_cohort_notes.json")
    # (the students of the extract and of the per-student credit table are
    # in m_pop.py)

    # --------------------------------------------------- reference cohort
    n = audit["cohort_n"]
    # the three programs describe the same cohort and the same window
    assert n == dfw["cohort"] == notes["cohort_n"], "cohort sizes differ"
    assert audit["entry_window"] == [
        const(SS + "config.py", "COHORT_ENTRY_START"),
        const(SS + "config.py", "COHORT_ENTRY_END")]
    assert audit["horizon_years"] == const(SS + "config.py",
                                           "COHORT_HORIZON_YEARS")
    M("CohortN", n, "int")

    # entry terms: the two fall terms, and spring plus summer between them
    terms = notes["entry_terms"]
    assert sorted(terms) == ["fall_2014", "fall_2015", "spring_2015",
                             "summer_2015"], sorted(terms)
    assert sum(terms.values()) == n
    M("CohortFirstFallN", terms["fall_2014"], "int")
    M("CohortSecondFallN", terms["fall_2015"], "int")
    M("CohortSpringSummerN", terms["spring_2015"] + terms["summer_2015"],
      "int")
    # Added for the text that quotes the results a second time (unit
    # `reuse`): share of the cohort that entered in one of the two fall
    # terms, in whole percent
    M("CohortFallPct", 100 * (terms["fall_2014"] + terms["fall_2015"]) / n,
      ".0f")

    # Coordinated Admission Program (CAP) flag and senior-level progression
    cap, nocap = notes["cap_set"], notes["cap_not_set"]
    assert cap["students"] + nocap["students"] == n
    M("CapN", cap["students"], "int")
    M("CapSeniorPct", 100 * cap["reached_senior_level"] / cap["students"],
      ".1f")
    M("NoCapN", nocap["students"], "int")
    M("NoCapSeniorPct",
      100 * nocap["reached_senior_level"] / nocap["students"], ".1f")
    # odds ratio of mathematics exposure and no senior-level enrollment
    # among students without the flag
    M("NoCapOddsMat", nocap["mat_odds_ratio_not_reaching"], ".2f")

    # ------------------------------------------------------ window audit
    # share reaching a senior-level course: declared (inclusive) window and
    # the strict four-year variant
    reach = audit["reached_above_4000"]
    assert (cap["reached_senior_level"] + nocap["reached_senior_level"]
            == reach["inclusive"]["n"])
    M("SeniorPct", 100 * reach["inclusive"]["n"] / n, ".1f")
    M("SeniorStrictN", reach["strict"]["n"], "int")
    M("SeniorStrictPct", 100 * reach["strict"]["n"] / n, ".1f")

    def cells(subject, boundary):
        """2 x 2 table of one gateway subject: a = took the subject, no
        senior-level course; b = took it, reached one; c, d = the same
        for students who did not take it"""
        t = audit["odds_ratios"][subject][boundary]
        a, b, c, d = t["a"], t["b"], t["c"], t["d"]
        assert a + b + c + d == n, (subject, boundary)
        assert b + d == reach[boundary]["n"], (subject, boundary)
        return a, b, c, d

    def odds(subject, boundary):
        """odds ratio of having no senior-level enrollment, takers against
        the rest of the cohort, from the cells (the file rounds its own)"""
        a, b, c, d = cells(subject, boundary)
        v = (a / c) / (b / d)
        assert round(v, 3) == audit["odds_ratios"][subject][boundary][
            "odds_ratio"], (subject, boundary)
        return v

    for subject, name in (("mat", "Mat"), ("wrc", "Wrc"), ("ais", "Ais")):
        M("Odds" + name, odds(subject, "inclusive"), ".2f")
        M("Odds" + name + "Strict", odds(subject, "strict"), ".2f")
        # share of the cohort that took the subject within the window
        a, b, c, d = cells(subject, "inclusive")
        M(name + "TakersPct", 100 * (a + b) / n, ".1f")

    # the mathematics odds ratio as two rates: no senior-level enrollment
    # among students with a mathematics course and among those without
    a, b, c, d = cells("mat", "inclusive")
    M("MatNoSeniorPct", 100 * a / (a + b), ".1f")
    M("NoMatNoSeniorPct", 100 * c / (c + d), ".1f")

    # boundary cases of the outcome and the rules of the major-change flag
    band, rules = audit["outcome_band"], dfw["rule_counts"]
    M("GraduateNumberedN", band["students_touching_5000_plus_in_window"],
      "int")
    assert (band["students_with_pre_entry_records"]
            == rules["students_with_records_before_entry"])
    M("PreEntryRecordsN", rules["students_with_records_before_entry"], "int")
    missing = rules["students_with_a_missing_major_endpoint"]
    M("MissingMajorN", missing, "int")
    # the text states that no student holds two majors in a boundary term
    assert not rules["students_with_two_majors_in_first_or_last_term"]
    assert not rules["students_with_two_majors_in_first_or_last_term_bounded"]

    # ------------------------------------------------------- major change
    changed = dfw["changed"]
    assert math.isclose(changed / n, dfw["share_changed"])
    M("MajorChangePct", 100 * dfw["share_changed"], ".1f")
    # The flag counts a missing first or last major as a change, so the
    # confirmed changes are the changes minus the students with a missing
    # endpoint; the complete cases are the cohort minus those students.
    confirmed, complete = changed - missing, n - missing
    M("ConfirmedChangePct", 100 * confirmed / n, ".1f")
    M("MajorCompleteN", complete, "int")
    M("ConfirmedChangeCompletePct", 100 * confirmed / complete, ".1f")
    # entry-bounded rule (records from the entry term on), confirmed only
    M("BoundedConfirmedN", rules["bounded_confirmed_students"], "int")
    M("BoundedConfirmedChangePct",
      100 * rules["bounded_confirmed_share_changed"], ".1f")

    # entrants observed enrolled a year or more after entry, and the rest
    later, left = dfw["later_observed"], dfw["not_observed_after_first_year"]
    assert later + left == n
    M("LaterObservedN", later, "int")
    M("LaterObservedChangePct", 100 * dfw["share_changed_later_observed"],
      ".1f")
    M("NotObservedN", left, "int")
    M("NotObservedChangePct",
      100 * dfw["share_changed_not_observed_after_first_year"], ".1f")

    # ------------------- first-year DFW in introductory courses and change
    res = dfw["results"]
    lat, full = res["later_observed"], res["all"]
    assert dfw["intro_below"] == const(SS + "major_change_dfw.py",
                                       "INTRO_BELOW")
    M("IntroBelow", dfw["intro_below"], "int0")
    # the level of the intervals that the normal quantile Z of the program
    # gives: 100 (2 Phi(Z) - 1)
    z = const(SS + "major_change_dfw.py", "Z")
    M("DfwIntervalLevel", 100 * math.erf(z / math.sqrt(2)), ".0f")

    def difference(name, r):
        """difference in the share that changed major, with a DFW minus
        without, in percentage points, with its interval; a sign is
        printed only when the value is negative"""
        M(name + "Diff", 100 * r["diff"], "s.1f")
        M(name + "DiffLo", 100 * r["diff_lo"], "s.1f")
        M(name + "DiffHi", 100 * r["diff_hi"], "s.1f")

    def odds_ratio(name, r):
        M(name + "Odds", r["odds_ratio"], ".2f")
        M(name + "OddsLo", r["or_lo"], ".2f")
        M(name + "OddsHi", r["or_hi"], ".2f")

    # mathematics, entrants observed a year or more after entry
    m = lat["MAT"]
    M("DfwMatLaterN", m["entrants"], "int")
    M("DfwMatLaterWithN", m["with_dfw"], "int")
    M("DfwMatLaterWithoutN", m["entrants"] - m["with_dfw"], "int")
    M("DfwMatLaterChangedWithPct", 100 * m["changed_with_dfw"], ".1f")
    M("DfwMatLaterChangedWithoutPct", 100 * m["changed_without"], ".1f")
    difference("DfwMatLater", m)
    odds_ratio("DfwMatLater", m)

    # mathematics, all entrants with a first-year attempt
    m = full["MAT"]
    M("DfwMatAllN", m["entrants"], "int")
    M("DfwMatAllChangedWithPct", 100 * m["changed_with_dfw"], ".1f")
    M("DfwMatAllChangedWithoutPct", 100 * m["changed_without"], ".1f")
    difference("DfwMatAll", m)
    odds_ratio("DfwMatAll", m)

    # mathematics counts the most entrants with a DFW in both populations,
    # and mathematics and physics are the two subjects whose difference is
    # positive with an interval above zero in both
    for pop in (lat, full):
        assert max(pop, key=lambda k: pop[k]["with_dfw"]) == "MAT"
    assert sorted(dfw["positive_difference_excluding_zero_in_both_"
                      "populations"]) == ["MAT", "PHY"]
    M("DfwPhyLaterWithN", lat["PHY"]["with_dfw"], "int")

    # computer science and chemistry
    M("DfwCsLaterDiff", 100 * lat["CS"]["diff"], "s.1f")
    # the text orders the subjects by the difference among later-observed
    # entrants: computer science and chemistry above mathematics, then
    # information systems and physics, which print close to mathematics
    order = sorted(lat, key=lambda k: -lat[k]["diff"])
    assert order[:2] == ["CS", "CHE"]
    assert set(order[2:5]) == {"IS", "PHY", "MAT"}
    M("DfwIsLaterDiff", 100 * lat["IS"]["diff"], "s.1f")
    M("DfwPhyLaterDiff", 100 * lat["PHY"]["diff"], "s.1f")
    difference("DfwCheLater", lat["CHE"])
    difference("DfwCheAll", full["CHE"])
    # writing composition, history, and the first-year seminar, all entrants
    for subject, name in (("WRC", "Wrc"), ("HIS", "His"), ("AIS", "Ais")):
        M("Dfw" + name + "AllDiff", 100 * full[subject]["diff"], "s.1f")

    # mathematics without the entrants whose first major is University
    # College (no declared major)
    m = res["later_observed_declared"]["MAT"]
    M("DfwMatDeclaredN", m["entrants"], "int")
    M("DfwMatDeclaredDiff", 100 * m["diff"], "s.1f")
    odds_ratio("DfwMatDeclared", m)

    # mathematics under the entry-bounded rule with confirmed changes only
    difference("DfwMatBoundedLater",
               res["later_observed_bounded_confirmed"]["MAT"])
    difference("DfwMatBoundedAll", res["all_bounded_confirmed"]["MAT"])

    # ------------------------------ relative subject grading among movers
    # one row per subject of the heatmap: per-mover deviation (student-
    # weighted mean over the observed cells), movers observed, cells
    # observed, total across movers
    per = {r["subject"]: float(r["weighted_mean_deviation"]) for r in heat}
    # totals at full precision (the rounded column can fall on a half)
    tot = {r["subject"]: float(r["total_deviation_unrounded"]) for r in heat}
    movers = {r["subject"]: int(r["students_in_cells"]) for r in heat}
    ncell = {r["subject"]: int(r["cells_observed"]) for r in heat}
    assert len(per) == len(heat)
    by_per = sorted(per, key=per.get)            # lowest grading first
    by_tot = sorted(tot, key=tot.get)

    top_subjects = const(SS + "heatmap.py", "TOP_SUBJECTS")
    top_majors = const(SS + "heatmap.py", "TOP_MAJORS")
    assert top_subjects == top_majors == len(heat)
    M("HeatMinCell", const(SS + "heatmap.py", "MIN_CELL_N"), "int")
    # the display keeps this many subjects and this many donor majors
    M("HeatTopKept", top_subjects, "int")

    # per mover: chemistry lowest, then mathematics and political science
    # (one value for the two), then business law, economics, and biology
    assert by_per[0] == "CHE" and set(by_per[1:3]) == {"MAT", "POL"}
    assert set(by_per[3:6]) == {"BLW", "ECO", "BIO"}
    M("HeatChePerMover", per["CHE"], "+.2f")
    M("HeatCheMovers", movers["CHE"], "int")
    M("HeatCheCells", ncell["CHE"], "int")
    assert fmt(per["MAT"], "+.2f") == fmt(per["POL"], "+.2f")
    M("HeatMatPolPerMover", per["MAT"], "+.2f")
    M("HeatBlwEcoBioPerMoverLow", per[by_per[3]], "+.2f")
    M("HeatBlwEcoBioPerMoverHigh", per[by_per[5]], "+.2f")
    # Added for the text that quotes the results a second time (unit
    # `reuse`): the deviations of mathematics and of chemistry as grade
    # points below the movers' own averages (printed without the sign),
    # where the text ranks mathematics second to chemistry per mover
    assert by_per[:2] == ["CHE", "MAT"] and per["MAT"] < 0
    M("HeatMatPerMoverBelow", per["MAT"], "a.2f")
    M("HeatChePerMoverBelow", per["CHE"], "a.2f")

    # in total across movers: mathematics, political science, chemistry
    assert by_tot[:3] == ["MAT", "POL", "CHE"]
    M("HeatMatTotal", tot["MAT"], "+.0fg")
    M("HeatPolTotal", tot["POL"], "+.0fg")
    M("HeatMatMovers", movers["MAT"], "int")
    M("HeatPolMovers", movers["POL"], "int")
    # both are observed in every donor-major column of the display
    assert ncell["MAT"] == ncell["POL"] == top_majors
    M("HeatDonorMajorColumns", top_majors, "int")
    M("HeatCheTotal", tot["CHE"], "+.0fg")

    # above the movers' norms: per mover information systems and art, in
    # total the first-year seminar ahead of information systems
    assert by_per[-1] == "IS" and by_per[-2] == "ART"
    assert by_tot[-1] == "AIS" and by_tot[-2] == "IS"
    M("HeatIsPerMover", per["IS"], "+.2f")
    M("HeatArtPerMover", per["ART"], "+.2f")
    M("HeatAisTotal", tot["AIS"], "+.0fg")
    M("HeatAisMovers", movers["AIS"], "int")
    M("HeatAisPerMover", per["AIS"], "+.2f")
    M("HeatIsTotal", tot["IS"], "+.0fg")

    # ------------------------------------- the naive design of the odds
    naive = J(SS + "tabOddsNaiveCohort_stats.json")["naive"]
    M("NaiveOddsMat", naive["MAT"]["odds_ratio"], ".2f")
    M("NaiveOddsWrc", naive["WRC"]["odds_ratio"], ".2f")
    M("NaiveOddsAis", naive["AIS"]["odds_ratio"], ".2f")

    # ------------------------------------------------ the chord diagram
    chord = J(SS + "figChord-MAT-majors_stats.json")
    M("ChordStudents", chord["n_students"], "int")
    assert chord["n_merged"] == const(SS + "config.py",
                                      "CHORD_OTHER_SMALLEST")
    # Publication rule of the figure: a ribbon is a count of students, so
    # only the flows of at least MIN_FLOW students are drawn, and sectors
    # are sized by the drawn flows. What is drawn and what is withheld:
    assert chord["min_flow"] == const(SS + "chord.py", "MIN_FLOW")
    assert chord["min_drawn_flow"] >= chord["min_flow"]
    assert chord["n_drawn_students"] + chord["n_withheld_students"] == \
        chord["n_students"]
    M("ChordMinFlowWord", chord["min_flow"], "word")
    M("ChordDrawnFlows", chord["n_drawn_flows"], "int")
    M("ChordDrawnStudents", chord["n_drawn_students"], "int")
    M("ChordDrawnPct",
      100 * chord["n_drawn_students"] / chord["n_students"], ".1f")
    M("ChordWithheldFlows", chord["n_withheld_flows"], "int")
    M("ChordWithheldStudents", chord["n_withheld_students"], "int")
    M("ChordSectors", chord["n_sectors"], "int")

    # ----------------------------------------- parameters of the displays
    # chord diagram: the angle at which the longest major name is placed
    M("ChordAnchorDeg", const(SS + "config.py", "CHORD_ANCHOR_DEG"), ".0f")
    # Benjamini-Hochberg level of the statistical helpers
    M("FdrQ", const(SS + "config.py", "Q_FDR"))
    # section-size figure: width of the size bins, and the smoothing
    # parameter of the Hodrick-Prescott filter as a power of ten
    M("SectionSizeBin", const(SS + "classsize.py", "BIN"), "int")
    lam = const(SS + "classsize.py", "HP_LAMBDA")
    power = round(math.log10(lam))
    assert 10 ** power == lam, lam
    M("HpLambda", "10^{%d}" % power)

    # --------------------------- counts that the text writes as words
    # The format "word" prints seven, and "Word" prints Seven for the start
    # of a sentence. Each value is read from the output or the constant
    # named here.
    # the observation window: from the entry term through the same term
    # this many years later (COHORT_HORIZON_YEARS, asserted above)
    M("HorizonYearsWord", audit["horizon_years"], "word")
    # students with a course numbered exactly at the senior-level boundary,
    # whom the strict inequality of the outcome leaves out
    # The count is withheld when it rests on fewer students than the
    # minimum cell; the text then says so.
    n_exact = band["students_touching_exactly_4000"]
    M("ExactBoundaryCourseNText",
      "Fewer than " + fmt(audit["min_cell"], "word") if n_exact is None
      else fmt(n_exact, "Word" if n_exact < 100 else "int"))
    # subjects of the table of introductory-course outcomes and major
    # change: its rows are the subjects of the later-observed population,
    # and each has its difference among all entrants in the last column
    assert set(lat) <= set(full)
    M("DfwSubjectsWord", len(lat), "word")
    # majors collected in the sector Other of the chord diagram
    # (CHORD_OTHER_SMALLEST, asserted above)
    M("ChordOtherMajorsWord", chord["n_merged"], "word")
    # Disclosure rule: the fewest students that a published aggregate cell
    # may rest on. The release scan (tools/disclosure_scan.py) holds it,
    # and the programs that write the student-linked aggregates use the
    # same value.
    min_cell = const("tools/disclosure_scan.py", "MIN_CELL")
    assert min_cell == dfw["min_cell"] == const(SS + "major_change_dfw.py",
                                                "MIN_CELL")
    assert min_cell == const("module_c/run_module_c.py", "MIN_CELL")
    # the same rule as \PopMinCellWord of m_pop.py, which the data appendix
    # prints from the parameters of the linkage profile
    assert min_cell == J(SS + "linkage_profile_stats.json")["parameters"][
        "min_cell"]
    M("DisclosureMinCellWord", min_cell, "word")
    return M.items
