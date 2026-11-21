"""Macros of the district course gradients (manuscript Figure 2, Section 3.2,
Appendix B.1, and the appendix methods of the gradients).

Source: figures/paper0/figCourseGradients_stats.json, written by
programs/paper0/course_gradient_figure.py; the parameters (minimum number
of children, bootstrap resamples, least share of a county group) are read
from the constants of that program.

Every gradient is the relative gradient of a course: the change in the
enrollment rate per ten percentage points of child poverty, in percent of
the national mean of the course. The text prints a negative gradient as a
"decline" (the value without its sign) and a gradient with either sign as
a signed value; the two forms are separate macros.

The Calculus quantities that Figure 1 also reports (the national gradient,
its restatement in seats, the Texas gradient, the income correlation, the
counts of districts) are printed with the macros of m_calc.py. This module
asserts that the two programs agree on each of them.

The counts that the text writes as words (course families, cycles, the
districts and groups of the county panel) are at the end of build(). One of
them, the districts with more Algebra II enrollees than resident children,
is read from figures/ingest/data_inventory_stats.json, written by
programs/ingest/data_inventory.py.
"""
import math

from texmacros import J, Macros, const, fmt

TITLE = "District course gradients (Figure 2 and Appendix B.1)"
SOURCE = ("figures/paper0/figCourseGradients_stats.json; "
          "figures/ingest/data_inventory_stats.json (frame_mismatch)")

PROGRAM = "paper0/course_gradient_figure.py"

# the three widely taken core courses of the text
CORE = ("biology", "alg2", "geometry")
# the courses at the end of the accelerated sequence
ADVANCED = ("calculus", "ap_math", "ap_science")

BEXAR_GROUPS = (
    ["Alamo Heights ISD", "Fort Sam Houston ISD", "Randolph Field ISD",
     "Lackland ISD", "North East ISD"],
    ["Northside ISD"],
    ["Judson ISD", "East Central ISD"],
    ["Southwest ISD", "Southside ISD", "South San Antonio ISD",
     "Harlandale ISD"],
    ["Somerset ISD", "San Antonio ISD", "Edgewood ISD"],
)


def build():
    s = J("paper0/figCourseGradients_stats.json")
    calc = J("paper0/figCalculusPanels_stats.json")    # agreement checks only
    M = Macros("Grad")

    first, primary, last = const(PROGRAM, "CYCLES")
    assert primary == s["primary_cycle"] == const(PROGRAM, "PRIMARY")
    assert calc["cycle"] == primary
    cyc = s["cycles"]

    def frame(cycle, name, denominator):
        """gradients of one cycle, district frame, and denominator"""
        return cyc[cycle][name][denominator]["subjects"]

    # the frame of the figure, per student in the grades of the course
    hs = frame(primary, "figure5_frame", "hs")
    # the same frame, per resident child aged 5 to 17
    child = frame(primary, "figure5_frame", "child")
    # Algebra I in grades 7-8 is divided by enrollment in grades 7 and 8;
    # the program keeps the per-high-school-student fit under its own key
    assert "per_high_school_student" in hs["alg1_g0708"]
    assert "grades 7-8" in hs["alg1_g0708"]["denominator"]

    def decline(g, spec=".1f"):
        """a negative gradient printed as a decline"""
        assert g < 0, g
        return fmt(-g, spec)

    def signed(prefix, sub, spec="+.1f"):
        """a gradient with its bootstrap interval, each printed with a sign"""
        M(prefix + "Rel", sub["rel10"], spec)
        M(prefix + "RelLow", sub["rel10_lo"], spec)
        M(prefix + "RelHigh", sub["rel10_hi"], spec)

    # ---- parameters and frame --------------------------------------
    min_pop = const(PROGRAM, "MIN_POP")
    assert min_pop == s["min_pop"]
    assert min_pop == const("paper0/course_panels_figure.py", "MIN_POP")
    M("MinChildren", min_pop, "int")
    n_boot = const(PROGRAM, "N_BOOT")
    assert n_boot == s["n_boot"]
    M("BootstrapResamples", n_boot, "int")

    # districts that hold a missing-coded course item leave the frame
    n_frame = cyc[primary]["figure5_frame"]["hs"]["n_districts"]
    n_before = cyc[primary]["incomplete_kept"]["hs"]["n_districts"]
    n_dropped = cyc[primary]["n_incomplete_excluded"]
    assert n_frame == calc["n_districts"]       # printed as \CalcDistricts
    assert n_frame == cyc[primary]["figure5_frame"]["child"]["n_districts"]
    assert n_before == cyc[primary]["incomplete_kept"]["child"]["n_districts"]
    assert n_before - n_dropped == n_frame
    M("IncompleteDistricts", n_dropped, "int")
    M("DistrictsBeforeExclusion", n_before, "int")

    # ---- national gradients of the primary cycle ---------------------
    # widely taken core courses: gradient and bootstrap interval
    signed("Biology", hs["biology"])
    signed("AlgebraTwo", hs["alg2"])
    signed("Geometry", hs["geometry"])
    signed("AlgebraOneNineTen", hs["alg1_g0910"])

    # the declines of the accelerated sequence and of the middle rows
    M("ApMathRelDecline", decline(hs["ap_math"]["rel10"]))
    M("ApScienceRelDecline", decline(hs["ap_science"]["rel10"]))
    M("ApAnyRelDecline", decline(hs["ap_any"]["rel10"]))
    M("AdvMathRelDecline", decline(hs["adv_math"]["rel10"]))
    M("PhysicsRelDecline", decline(hs["physics"]["rel10"]))

    # Calculus: the point estimate is \CalcRelDecline; the interval of
    # the decline runs from minus the upper bound to minus the lower bound
    cal = hs["calculus"]
    assert math.isclose(cal["rel10"], calc["per_hs_student"]["rel10_pct"])
    M("CalculusRelDeclineLow", decline(cal["rel10_hi"]))
    M("CalculusRelDeclineHigh", decline(cal["rel10_lo"]))

    # Algebra I in grades 7-8, per student in those grades: the decline
    # and its interval (the lower end of the decline is negative when the
    # interval of the gradient includes zero)
    early = hs["alg1_g0708"]
    M("EarlyAlgebraRelDecline", decline(early["rel10"]))
    M("EarlyAlgebraRelDeclineLow", -early["rel10_hi"], "s.1f")
    M("EarlyAlgebraRelDeclineHigh", decline(early["rel10_lo"]))
    early_first = frame(first, "figure5_frame", "hs")["alg1_g0708"]
    assert "grades 7-8" in early_first["denominator"]
    M("EarlyAlgebraFirstCycleRelDecline", decline(early_first["rel10"]))
    M("EarlyAlgebraFirstCycleRelDeclineLow", decline(early_first["rel10_hi"]))
    M("EarlyAlgebraFirstCycleRelDeclineHigh", decline(early_first["rel10_lo"]))

    # Added for the text that quotes the results a second time (unit
    # `reuse`): the range of the declines over the three courses at the
    # end of the accelerated sequence (Calculus, AP mathematics, AP
    # science), in whole percent
    adv_hs = [hs[k]["rel10"] for k in ADVANCED]
    M("AdvancedRelDeclineMin", decline(max(adv_hs), ".0f"))
    M("AdvancedRelDeclineMax", decline(min(adv_hs), ".0f"))

    # ---- profile by tenths of high-school students -------------------
    dec = s["deciles_" + primary]
    assert len(dec["bounds"]) == const(PROGRAM, "NQ")
    ratio = dict(zip(dec["rows"], dec["ratio"]))
    lowest, highest = dec["bounds"][0], dec["bounds"][-1]
    assert lowest[1] < highest[0]
    # child poverty rate that bounds the lowest and the highest tenth
    M("LowestTenthPovertyMax", 100 * lowest[1], ".1f")
    M("HighestTenthPovertyMin", 100 * highest[0], ".1f")
    # enrollment per student over the national value, in those tenths
    M("CalculusLowestTenthRatio", ratio["calculus"][0], ".2f")
    M("CalculusHighestTenthRatio", ratio["calculus"][-1], ".2f")
    M("BiologyLowestTenthRatio", ratio["biology"][0], ".2f")
    M("BiologyHighestTenthRatio", ratio["biology"][-1], ".2f")

    # ---- Bexar County (panel B) ---------------------------------------
    bx = s["bexar_" + primary]
    assert bx["n_districts"] == calc["n_bexar"]
    min_share = const(PROGRAM, "MIN_SHARE")
    assert min_share == bx["min_share_of_students_per_group"]
    # least share of the county's high-school students in a group
    M("BexarMinSharePct", 100 * min_share, ".0f")

    groups = bx["groups"]
    assert [g["districts"] for g in groups] == list(BEXAR_GROUPS)
    words = ("One", "Two", "Three", "Four", "Five")
    assert len(groups) == len(words)
    for word, g in zip(words, groups):
        # child poverty rates of the districts of the group
        if g["n_districts"] == 1:
            assert g["pov_lo"] == g["pov_hi"]
            M(f"BexarGroup{word}Poverty", 100 * g["pov_lo"], ".1f")
        else:
            M(f"BexarGroup{word}PovertyLow", 100 * g["pov_lo"], ".1f")
            M(f"BexarGroup{word}PovertyHigh", 100 * g["pov_hi"], ".1f")
        # Calculus per high-school student over the national rate
        M(f"BexarGroup{word}CalculusRatio", g["ratio"]["calculus"], ".2f")
    # the core courses over the five groups: smallest and largest ratio
    core_ratios = [g["ratio"][k] for g in groups for k in CORE]
    M("BexarCoreRatioMin", min(core_ratios), ".2f")
    M("BexarCoreRatioMax", max(core_ratios), ".2f")

    # gradients over the fifteen districts, in percent of the national
    # mean, with intervals from the bootstrap that resamples districts
    brel = bx["rel10"]
    M("BexarCalculusRelDecline", decline(brel["calculus"]["rel10"], ".0f"))
    M("BexarCalculusRelDeclineLow", decline(brel["calculus"]["rel10_hi"], ".0f"))
    M("BexarCalculusRelDeclineHigh", decline(brel["calculus"]["rel10_lo"], ".0f"))
    M("BexarApMathRelDecline", decline(brel["ap_math"]["rel10"], ".0f"))
    M("BexarApScienceRelDecline", decline(brel["ap_science"]["rel10"], ".0f"))
    # advanced mathematics rises with child poverty within the county; the
    # lower bound is printed with one decimal because it lies near zero
    adv = brel["adv_math"]
    assert adv["rel10_lo"] > 0
    M("BexarAdvMathRel", adv["rel10"], "+.0f")
    M("BexarAdvMathRelLow", adv["rel10_lo"], ".1f")
    M("BexarAdvMathRelHigh", adv["rel10_hi"], ".0f")

    # Added for the text that quotes the results a second time (unit
    # `reuse`).
    # The county's Calculus gradient and its interval with their signs
    # (the same quantity as BexarCalculusRelDecline, printed as a gradient)
    signed("BexarCalculus", brel["calculus"], "+.0f")
    # The two groups with the lowest child poverty against the other
    # three: Calculus is taken at less than half of the national rate in
    # each of the three and at more than half in each of the two.
    lower, upper = groups[:2], groups[2:]
    upper_ratios = [g["ratio"]["calculus"] for g in upper]
    assert max(upper_ratios) < 1 / 2 < min(g["ratio"]["calculus"]
                                           for g in lower)
    # range of the Calculus ratio over the three groups
    M("BexarUpperGroupsCalculusRatioMin", min(upper_ratios), ".2f")
    M("BexarUpperGroupsCalculusRatioMax", max(upper_ratios), ".2f")
    # The text describes the districts of the three groups as those with
    # child poverty "above" a whole percent: the whole percent below the
    # lowest rate among them, which every district of the two other
    # groups stays under.
    above = math.floor(100 * min(g["pov_lo"] for g in upper))
    assert 100 * max(g["pov_hi"] for g in lower) < above
    M("BexarUpperGroupsPovertyAbove", above, "int")

    # ---- robustness: the three cycles ---------------------------------
    # the Calculus decline of the primary cycle is \CalcRelDecline
    M("CalculusFirstCycleRelDecline",
      decline(frame(first, "figure5_frame", "hs")["calculus"]["rel10"]))
    M("CalculusLastCycleRelDecline",
      decline(frame(last, "figure5_frame", "hs")["calculus"]["rel10"]))
    # the core courses over the three cycles: lowest and highest gradient
    core_cycles = [frame(c, "figure5_frame", "hs")[k]["rel10"]
                   for c in (first, primary, last) for k in CORE]
    M("CoreCyclesRelMin", min(core_cycles), "+.1f")
    M("CoreCyclesRelMax", max(core_cycles), "+.1f")

    # ---- robustness: frame, fixed effects, denominator ----------------
    neutral = frame(primary, "neutral_frame", "hs")
    span = s["grade_9_12_schools_" + primary]
    span_cal = span["subjects"]["calculus"]
    # Calculus decline under each of the three checks
    M("CalculusNeutralFrameRelDecline", decline(neutral["calculus"]["rel10"]))
    M("CalculusStateFeRelDecline", decline(cal["rel10_state_fe"]))
    M("CalculusExactSpanRelDecline", decline(span_cal["rel10"]))
    M("CalculusExactSpanRelDeclineLow", decline(span_cal["rel10_hi"]))
    M("CalculusExactSpanRelDeclineHigh", decline(span_cal["rel10_lo"]))
    # the range of the Calculus decline over the three checks
    checks = [neutral["calculus"]["rel10"], cal["rel10_state_fe"],
              span_cal["rel10"]]
    M("CalculusChecksRelDeclineMin", decline(max(checks)))
    M("CalculusChecksRelDeclineMax", decline(min(checks)))
    # the core courses on the neutral frame: lowest and highest gradient
    core_neutral = [neutral[k]["rel10"] for k in CORE]
    M("CoreNeutralFrameRelMin", min(core_neutral), "+.1f")
    M("CoreNeutralFrameRelMax", max(core_neutral), "+.1f")
    # schools whose grade span is exactly 9-12 (the denominator check)
    M("ExactSpanSchools", span["n_schools"], "int")

    # ---- Texas ---------------------------------------------------------
    # within-state slopes per student in the grades of the course: per
    # high-school student, and for Algebra I in grades 7-8 per student in
    # grades 7 and 8, as in the national fits
    tx = s["texas_" + primary]["hs"]
    txs = tx["subjects"]
    assert tx["n_districts"] == calc["texas"]["n_districts"]  # \CalcTexasDistricts
    assert math.isclose(txs["calculus"]["rel10"],
                        calc["texas"]["rel10_pct"])            # \CalcTexasRelDecline
    M("TexasApMathRelDecline", decline(txs["ap_math"]["rel10"]))
    assert "grades 7-8" in txs["alg1_g0708"]["denominator"]
    M("TexasEarlyAlgebraRelDecline", decline(txs["alg1_g0708"]["rel10"]))
    M("TexasAlgebraTwoRel", txs["alg2"]["rel10"], "+.1f")
    M("TexasAlgebraTwoZ", txs["alg2"]["z_hc1"], ".2f")

    # ---- gradients in seats --------------------------------------------
    # enrollees per 100 students in the grades of the course per ten
    # percentage points of child poverty: 100 x 0.10 x slope = 10 x slope
    def seats(k):
        return 10 * hs[k]["slope"]

    def seats_decline(k):
        assert seats(k) < 0, k
        return fmt(seats(k), "a.1f")

    M("ApAnySeats", seats_decline("ap_any"))
    M("EarlyAlgebraSeats", seats_decline("alg1_g0708"))
    M("AdvMathSeats", seats_decline("adv_math"))
    M("ApScienceSeats", seats_decline("ap_science"))
    M("ApMathSeats", seats_decline("ap_math"))
    # Calculus in seats is \CalcSeatsPerTenPoints
    assert math.isclose(cal["slope"], calc["per_hs_student"]["slope"])
    # the largest change among the core courses, either sign
    M("CoreSeatsMax", max(abs(seats(k)) for k in CORE), ".1f")

    # ---- district income -----------------------------------------------
    # child-weighted correlation of district income with enrollment per
    # high-school student
    inc = s["income_association_" + primary]

    def corr(k):
        return inc[k + "|per high-school student"]["weighted_pearson"]

    assert {v["n_districts"] for v in inc.values()} == {calc["n_with_income"]}
    assert math.isclose(corr("calculus"),
                        calc["income"]["weighted_pearson"])     # \CalcIncomeCorr
    M("IncomeCoreCorrMin", min(corr(k) for k in CORE), "s.2f")
    M("IncomeCoreCorrMax", max(corr(k) for k in CORE), "s.2f")
    M("IncomeAdvMathCorr", corr("adv_math"), ".2f")
    # the text gives one value for AP mathematics and AP science
    assert fmt(corr("ap_math"), ".2f") == fmt(corr("ap_science"), ".2f")
    M("IncomeApCorr", corr("ap_math"), ".2f")

    # ---- the per-capita measure (per resident child) --------------------
    # estimated high-school enrollment per resident child: the reference
    # row of the program
    ref = child[const(PROGRAM, "REF")]
    M("HsEnrollmentPerChildRelDecline", decline(ref["rel10"]))
    M("HsEnrollmentPerChildRelDeclineLow", decline(ref["rel10_hi"]))
    M("HsEnrollmentPerChildRelDeclineHigh", decline(ref["rel10_lo"]))
    # per resident child, the range over the core courses and over the
    # courses at the end of the accelerated sequence
    core_child = [child[k]["rel10"] for k in CORE]
    M("CorePerChildRelDeclineMin", decline(max(core_child)))
    M("CorePerChildRelDeclineMax", decline(min(core_child)))
    adv_child = [child[k]["rel10"] for k in ADVANCED]
    M("AdvancedPerChildRelDeclineMin", decline(max(adv_child), ".0f"))
    M("AdvancedPerChildRelDeclineMax", decline(min(adv_child), ".0f"))

    # ---- the gradient in seats with the normal interval of its
    # state-clustered standard error (fields seats_lo and seats_hi)
    for key, name in (("ap_any", "ApAny"), ("alg1_g0708", "EarlyAlgebra"),
                      ("adv_math", "AdvancedMath")):
        M(f"{name}SeatsLow", hs[key]["seats_lo"], "s.1f")
        M(f"{name}SeatsHigh", hs[key]["seats_hi"], ".1f")

    # ---- counts that the text writes as words ----------------------------
    # The format "word" prints fifteen, and "Word" prints Fifteen for the
    # start of a sentence. Each value is the expression of the numeral
    # macro of the same quantity, or the output or constant named here.
    # Course families of the comparison: the SUBJECTS of the program, each
    # with a gradient in the frame of the figure and in the county panel.
    families = const(PROGRAM, "SUBJECTS")
    assert set(families) == set(hs) == set(brel)
    M("CourseFamiliesWord", len(families), "word")
    # CRDC cycles on which the comparison is computed
    assert set(cyc) == set(const(PROGRAM, "CYCLES"))
    M("CyclesWord", len(cyc), "word")
    # districts that leave the frame for an incomplete total (the numeral
    # is \GradIncompleteDistricts)
    M("IncompleteDistrictsWord", n_dropped, "word")
    # districts of Bexar County in the frame (the numeral is
    # \CalcBexarDistricts), and the groups they are combined into
    assert sum(g["n_districts"] for g in groups) == bx["n_districts"]
    M("BexarDistrictsWord", bx["n_districts"], "word")
    M("BexarDistrictsCapitalWord", bx["n_districts"], "Word")
    M("BexarGroupsWord", len(groups), "word")
    # The groups are in order of child poverty. Calculus is taken at more
    # than half of the national rate in the groups with the lowest child
    # poverty and at less than half of it in every other group; the text
    # counts the groups of each kind.
    assert ([g["pov_lo"] for g in groups]
            == sorted(g["pov_lo"] for g in groups))
    above_half = [g["ratio"]["calculus"] > 1 / 2 for g in groups]
    assert above_half == sorted(above_half, reverse=True)
    assert sum(above_half) == len(lower)
    M("BexarLowerGroupsWord", sum(above_half), "word")
    M("BexarUpperGroupsWord", len(groups) - sum(above_half), "word")
    # Districts of the primary cycle that record more Algebra II enrollees
    # than resident children aged 5 to 17, counted in the project database
    # by ingest/data_inventory.py (figures/ingest/data_inventory_stats.json).
    # Leaving them out reverses the sign of the unweighted slope of
    # enrollment per resident child on the poverty rate.
    mis = J("ingest/data_inventory_stats.json")["frame_mismatch"]
    assert mis["cycle"] == primary and mis["min_children"] == min_pop
    fit_all = mis["fits"]["all_districts"]
    fit_rest = mis["fits"]["without_ratio_above_one"]
    n_mismatch = mis["ratio_above_one"]["n_districts"]
    assert fit_all["n_districts"] - fit_rest["n_districts"] == n_mismatch
    assert fit_all["slope_unweighted"] > 0 > fit_rest["slope_unweighted"]
    M("FrameMismatchDistrictsWord", n_mismatch, "word")
    return M.items
