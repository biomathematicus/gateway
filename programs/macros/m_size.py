"""Macros of the section-size models (manuscript Sections 2.4 and 3.6,
Appendix A "entry rule and inference", Appendix B.8 "sensitivity checks").

Sources, all under figures/module_c/class_size/:
  registered/   the registered estimation, written by
                programs/module_c/run_class_size.py (read, never edited)
  rev5/         the corrections after the REV5 review, written by
                programs/module_c/rev5_class_size.py: contrasts of the
                interaction model with their bootstrap intervals, pooled
                intervals that include the covariance between subjects,
                the next-course subset, support, and section sizes

Which folder a quantity is read from follows the plan
(prespecification/class_size_addendum.md, Section 14, D1): every registered
point estimate stands, and so do the registered tests of the size
coefficient (H3) and of the size-by-score interaction (H4); the contrasts
(slope at a given entry score, scenario by third), the pooled intervals,
and the total across subjects are printed with the rev5 intervals.

The descriptive curves of Figure "figClassSize" come from
programs/student_success/classsize.py, which writes no statistics file;
only its module-level constants are read here.

The counts that the text writes as words are at the end of build(). The
number of nested models is the length of LADDER in
programs/module_c/cs_figures.py, the comparison ladder of the figure.
"""
import ast
import re

from texmacros import PROGRAMS, C, J, Macros, const, row

TITLE = "Section size and grades (Sections 2.4 and 3.6, Appendices A and B.8)"
SOURCE = ("figures/module_c/class_size/registered/ and "
          "figures/module_c/class_size/rev5/")

REG = "module_c/class_size/registered/"
FIX = "module_c/class_size/rev5/"


def one(rows, test):
    """the single row for which test(row) holds"""
    hit = [r for r in rows if test(r)]
    assert len(hit) == 1, len(hit)
    return hit[0]


def ladder_models():
    """the keys of the nested models of the comparison ladder, in order:
    the first element of each pair of LADDER in module_c/cs_figures.py. The
    labels of the pairs are built with a name of the program, which const()
    cannot evaluate, so the keys are read from the syntax tree."""
    tree = ast.parse((PROGRAMS / "module_c/cs_figures.py")
                     .read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "LADDER"):
            assert isinstance(node.value, ast.List), type(node.value)
            return [ast.literal_eval(pair.elts[0])
                    for pair in node.value.elts]
    raise KeyError("LADDER")


def build():
    M = Macros("Size")
    res = J(REG + "results.json")
    fix = J(FIX + "results.json")
    prim = C(REG + "cs_primary.csv")
    coef = C(REG + "cs_coefficients.csv")
    proj = C(REG + "cs_projection.csv")
    sfe = C(REG + "cs_student_fe.csv")
    flow = C(REG + "cs_stage0_flow.csv")
    expo = C(REG + "cs_stage0_exposure.csv")
    bal = C(REG + "cs_stage0_balance.csv")
    nxt = C(REG + "cs_next_course.csv")
    con = C(FIX + "cs_contrasts.csv")
    cal = C(FIX + "cs_contrast_calibration.csv")
    joint = C(FIX + "cs_pooled_joint.csv")
    sub = C(FIX + "cs_next_course_subset.csv")
    sup = C(FIX + "cs_support.csv")
    sizes = C(FIX + "cs_section_sizes.csv")

    # ------------------------------------------------ parameters of the plan
    cap = const("module_c/run_class_size.py", "CAP")
    assert cap == res["cap"] == res["scenario_all_subjects"]["cap"]
    M("Cap", cap, "int")
    M("MinSection", const("module_c/cs_data.py", "MIN_SECTION"), "int")
    M("EntryMinStudents", const("module_c/run_class_size.py", "MIN_STUDENTS"),
      "int")
    M("EntryMinSdLogSize", const("module_c/run_class_size.py", "MIN_SD"),
      ".2f")
    draws = const("module_c/run_class_size.py", "NBOOT")
    assert draws == fix["bootstrap_draws"]
    M("BootstrapDraws", draws, "int")

    # ------------------------------------------------------- rows and subjects
    primary = row(flow, step="face-to-face lecture section (primary set)")
    every = row(expo, subject="ALL")
    assert primary["rows"] == every["rows"]
    assert primary["students"] == every["students"]
    M("FirstAttempts", primary["rows"], "int")
    M("Entrants", primary["students"], "int")
    modeled, outside = res["subjects_modeled"], res["subjects_outside_entry_rule"]
    assert len(modeled) == res["scenario_all_subjects"]["subjects"]
    assert sorted(modeled) == sorted(
        r["subject"] for r in expo if r["enters_models"] == "1")
    M("SubjectsModeled", len(modeled), "int")
    # the subjects of the performance models: those that enter and those
    # that the entry rule leaves out
    assert sorted(modeled + outside) == sorted(
        r["subject"] for r in expo if r["subject"] != "ALL")
    M("SubjectsConsidered", len(modeled) + len(outside), "int")

    # the same-student model (student fixed effects): its instructors
    sg = [r for r in sfe if r["outcome"] == "grade"]
    assert len({r["instructor_clusters"] for r in sg}) == 1
    M("SameStudentInstructors", sg[0]["instructor_clusters"], "int")

    # --------------------- observed sizes of the mathematics lecture sections
    calc = one(sizes, lambda r: r["courses"].startswith("Calculus I and II"))
    below = one(sizes, lambda r: r["courses"].startswith("courses below"))
    M("CalculusMedianSize", calc["p50"], "int")
    # the percentile of the Calculus section sizes that equals the cap
    at_cap = [k for k in calc if re.fullmatch(r"p\d+", k)
              and int(calc[k]) == cap]
    assert len(at_cap) == 1, at_cap
    M("CapCalculusPercentile", at_cap[0][1:], "int0")
    # "none above": the smallest size at or below which the file reports
    # every Calculus section (the bound is part of the field name)
    full = sorted(int(m.group(1)) for k in calc
                  if (m := re.fullmatch(r"share_(\d+)_or_fewer", k))
                  and float(calc[k]) == 1.0)
    assert full, "no size bounds every Calculus section"
    M("CalculusSizeBound", full[0], "int")
    # the size above which the file counts the large sections of the
    # courses below Calculus (again part of the field name)
    large = [m.group(1) for k in below
             if (m := re.fullmatch(r"share_above_(\d+)", k))]
    assert len(large) == 1 and float(below["share_above_" + large[0]]) > 0
    M("LargeSectionBound", large[0], "int")

    # ------------------- descriptive curves (student_success/classsize.py)
    M("CurveGridMax", const("student_success/classsize.py", "X_MAX"), "int0")
    M("CurveBin", const("student_success/classsize.py", "BIN"), "int0")
    M("CurveSmoothing", const("student_success/classsize.py", "HP_LAMBDA"),
      "int0")

    # ------------------------------- mathematics: the comparison ladder (H3)
    g = row(prim, outcome="grade", subject="MAT")
    d = row(prim, outcome="dfw", subject="MAT")
    m0, m0hw = float(g["m0"]), float(g["m0_hw"])
    M("MatAllSectionsGrade", m0, "+.3f")
    M("MatAllSectionsGradeLow", m0 - m0hw, "+.3f")
    M("MatAllSectionsGradeHigh", m0 + m0hw, "+.3f")
    M("MatCourseTermGrade", g["m1"], "+.3f")
    h3 = res["H3"]
    assert abs(h3["mat_m3_grade_per_doubling"] - float(g["m3"])) < 1e-4
    M("MatPrimaryGrade", h3["mat_m3_grade_per_doubling"], "+.3f")
    M("MatPrimaryGradeLow", h3["lo"], "+.3f")
    M("MatPrimaryGradeHigh", h3["hi"], "+.3f")
    M("MatPrimaryGradeP", h3["wild_bootstrap_p"], ".2f")
    # the DFW coefficient of the primary model, in percentage points
    assert abs(h3["mat_m3_dfw_per_doubling"] - float(d["m3"])) < 1e-4
    M("MatPrimaryDfw", 100 * h3["mat_m3_dfw_per_doubling"], "+.1f")
    M("MatPrimaryDfwLow", 100 * h3["dfw_lo"], "+.1f")
    M("MatPrimaryDfwHigh", 100 * h3["dfw_hi"], "+.1f")
    # each student compared with the same student in other courses
    sm = row(sfe, outcome="grade", term="log2_size_MAT")
    assert abs(h3["student_fe_mat_grade"] - float(sm["estimate"])) < 1e-9
    M("MatSameStudentGrade", h3["student_fe_mat_grade"], "+.3f")
    # balance: entry mathematics score per doubling of size, within course
    # and term
    M("MatBalanceMathScore",
      row(bal, subject="MAT", covariate="zm")["per_doubling_of_size"], "+.3f")

    # ------------------- mathematics: the size-by-score interaction (H4),
    # the registered test (addendum D1: "the registered values stand")
    h4 = res["H4"]
    assert abs(h4["mat_m4_size_x_math_grade"] - float(g["m4"])) < 1e-4
    assert abs(h4["wild_bootstrap_p"] - float(g["m4_p_wild"])) < 1e-9
    M("MatInteractionGrade", h4["mat_m4_size_x_math_grade"], ".3f")
    M("MatInteractionGradeLow", h4["lo"], ".3f")
    M("MatInteractionGradeHigh", h4["hi"], ".3f")
    M("MatInteractionGradeP", h4["wild_bootstrap_p"], ".3f")
    # DFW: the text gives the fall of the coefficient per standard
    # deviation of the entry score, in percentage points
    fall, fhw = -float(d["m4"]), float(d["m4_hw"])
    assert fall > 0
    M("MatInteractionDfwFall", 100 * fall, ".1f")
    M("MatInteractionDfwFallLow", 100 * (fall - fhw), ".1f")
    M("MatInteractionDfwFallHigh", 100 * (fall + fhw), ".1f")
    M("MatInteractionDfwP", d["m4_p_wild"], ".3f")
    # Added for the text that quotes the results a second time (unit
    # `reuse`): the grade coefficient of the interaction with its sign
    M("MatInteractionGradeSigned", h4["mat_m4_size_x_math_grade"], "+.3f")

    # ---------- mathematics: the size slope at a given entry score (rev5
    # contrasts; DFW rows of that file are in percentage points)
    def slope(outcome, sd):
        return one(con, lambda r: r["outcome"] == outcome
                   and r["contrast"].startswith("size slope at entry score")
                   and float(r["contrast"].split()[-2]) == sd)

    lo_d, lo_g = slope("dfw", -1), slope("grade", -1)
    hi_d, hi_g = slope("dfw", 1), slope("grade", 1)
    assert float(lo_d["estimate"]) > 0 > float(lo_g["estimate"])
    M("MatSlopeLowScoreDfw", lo_d["estimate"], ".1f")
    M("MatSlopeLowScoreDfwLow", lo_d["wild_lo"], ".1f")
    M("MatSlopeLowScoreDfwHigh", lo_d["wild_hi"], ".1f")
    M("MatSlopeLowScoreDfwP", lo_d["p_wild_bootstrap"], ".3f")
    M("MatSlopeLowScoreGradeLower", lo_g["estimate"], "a.3f")
    M("MatSlopeLowScoreGradeLow", lo_g["wild_lo"], "+.3f")
    M("MatSlopeLowScoreGradeHigh", lo_g["wild_hi"], "+.3f")
    M("MatSlopeLowScoreGradeP", lo_g["p_wild_bootstrap"], ".3f")
    M("MatSlopeHighScoreDfw", hi_d["estimate"], "+.1f")
    M("MatSlopeHighScoreDfwLow", hi_d["wild_lo"], "+.1f")
    M("MatSlopeHighScoreDfwHigh", hi_d["wild_hi"], "+.1f")
    M("MatSlopeHighScoreGrade", hi_g["estimate"], "+.3f")
    M("MatSlopeHighScoreGradeLow", hi_g["wild_lo"], "+.3f")
    M("MatSlopeHighScoreGradeHigh", hi_g["wild_hi"], "+.3f")

    # ------------------------------------------------- across the subjects
    grade = {r["subject"]: r for r in prim if r["outcome"] == "grade"}
    dfw = {r["subject"]: r for r in prim if r["outcome"] == "dfw"}
    pj = row(joint, outcome="grade", summary="pooled M3, all")
    assert int(pj["subjects"]) == len(modeled)
    M("PooledGrade", pj["estimate"], "+.3f")
    M("PooledGradeLow", pj["lo_joint"], "+.3f")
    M("PooledGradeHigh", pj["hi_joint"], "+.3f")
    # the one subject that passes false-discovery control (grade outcome)
    passing = [s for s, r in grade.items() if r["bh_m3"] == "1"]
    assert passing == ["AIS"], passing
    assert not [s for s, r in dfw.items() if r["bh_m3"] == "1"]
    M("AisPrimaryGrade", grade["AIS"]["m3"], "+.3f")
    # section size of the first-year seminar at the median and at the 90th
    # percentile of its first attempts (the text: "about ... and about ...")
    ais = row(expo, subject="AIS")
    M("AisSizeMedian", ais["size_p50"], "int")
    M("AisSizeNinetieth", ais["size_p90"], "int")
    # first attempts (grade outcome) of the largest and the smallest subject
    by_rows = sorted(grade, key=lambda s: int(grade[s]["rows"]))
    assert by_rows[-1] == "MAT" and by_rows[0] == "ART", by_rows
    M("MatGradeFirstAttempts", grade["MAT"]["rows"], "int")
    M("FewestGradeFirstAttempts", grade["ART"]["rows"], "int")
    # music: the second-largest negative coefficient per student
    by_coef = sorted(grade, key=lambda s: float(grade[s]["m3"]))
    assert by_coef[1] == "MUS", by_coef
    M("MusPrimaryGrade", grade["MUS"]["m3"], "+.3f")
    # every first attempt weighted equally: the same-student model
    sa = row(sfe, outcome="grade", term="log2_size")
    sae, sahw = float(sa["estimate"]), float(sa["cluster_t_half_width"])
    M("SameStudentGrade", sae, "+.3f")
    M("SameStudentGradeLow", sae - sahw, "+.3f")
    M("SameStudentGradeHigh", sae + sahw, "+.3f")

    # ------------- scenario: DFW outcomes per entry cohort, by subject
    pd = {r["subject"]: r for r in proj if r["outcome"] == "dfw"}
    order = sorted(pd, key=lambda s: float(pd[s]["dfw_outcomes_per_cohort"]))
    assert order[:2] == ["HIS", "MAT"], order      # largest reductions
    assert order[-2:] == ["AIS", "CHE"], order     # largest increases
    for code in ("HIS", "MAT", "CHE", "AIS", "MUS"):
        name = code.capitalize()                   # HisDfwPerCohort, ...
        M(name + "DfwPerCohort", pd[code]["dfw_outcomes_per_cohort"], "+.0f")
        M(name + "DfwPerCohortLow", pd[code]["per_cohort_lo"], "+.0f")
        M(name + "DfwPerCohortHigh", pd[code]["per_cohort_hi"], "+.0f")
    # mathematics again, as the text words it: "53 fewer ... from 178
    # fewer to 71 more"
    mat = pd["MAT"]
    assert (float(mat["per_cohort_lo"]) < float(mat["dfw_outcomes_per_cohort"])
            < 0 < float(mat["per_cohort_hi"]))
    M("MatDfwPerCohortFewer", mat["dfw_outcomes_per_cohort"], "a.0f")
    M("MatDfwPerCohortLowFewer", mat["per_cohort_lo"], "a.0f")
    M("MatDfwPerCohortHighMore", mat["per_cohort_hi"], "a.0f")

    # ---------------- scenario in mathematics: all affected first attempts
    years = res["cohorts"][1] - res["cohorts"][0] + 1
    M("MatAffectedPerCohort", int(mat["affected_first_attempts"]) / years,
      "int")
    M("MatScenarioDfw", mat["change_among_affected"], "+.1f")
    M("MatScenarioDfwLow", mat["lo"], "+.1f")
    M("MatScenarioDfwHigh", mat["hi"], "+.1f")
    M("MatSectionsPerYear", mat["sections_per_year"], "int")
    M("MatSectionsAddedPerYear", mat["sections_added_per_year"], "int")
    # Added for the text that quotes the results a second time (unit
    # `reuse`): the sections that the split adds, as a percentage of the
    # mathematics sections taught now (counts over the window; the yearly
    # values of the file give the same share)
    added_share = int(mat["sections_added"]) / int(mat["sections_in_window"])
    assert abs(added_share - float(mat["sections_added_per_year"])
               / float(mat["sections_per_year"])) < 1e-3
    M("MatSectionsAddedPct", 100 * added_share, ".0f")

    # ------- scenario in mathematics by third of the entry score (rev5
    # contrasts with their wild cluster bootstrap intervals)
    def third(outcome, which):
        return row(con, outcome=outcome, contrast=f"cap scenario, {which} third")

    td, tg = third("dfw", "lowest"), third("grade", "lowest")
    assert float(td["estimate"]) < 0 < float(tg["estimate"])
    M("LowThirdDfwFewer", td["estimate"], "a.1f")
    M("LowThirdDfwLow", td["wild_lo"], "+.1f")
    M("LowThirdDfwHigh", td["wild_hi"], "+.1f")
    M("LowThirdDfwP", td["p_wild_bootstrap"], ".3f")
    M("LowThirdGrade", tg["estimate"], ".2f")
    M("LowThirdGradeLow", tg["wild_lo"], "+.2f")
    M("LowThirdGradeHigh", tg["wild_hi"], "+.2f")
    M("LowThirdGradeP", tg["p_wild_bootstrap"], ".3f")
    # the same interval by inverting the bootstrap test, and the
    # clustered-t interval that the plan specified
    M("LowThirdDfwInvertedLow", td["inverted_lo"], "+.1f")
    M("LowThirdDfwInvertedHigh", td["inverted_hi"], "+.1f")
    M("LowThirdDfwClusterLow", td["cluster_t_lo"], "+.1f")
    M("LowThirdDfwClusterHigh", td["cluster_t_hi"], "+.1f")
    tm, th = third("dfw", "middle"), third("dfw", "highest")
    assert float(tm["estimate"]) < 0 < float(th["estimate"])
    M("MidThirdDfwFewer", tm["estimate"], "a.1f")
    M("MidThirdDfwLow", tm["wild_lo"], "+.1f")
    M("MidThirdDfwHigh", tm["wild_hi"], "+.1f")
    M("HighThirdDfwMore", th["estimate"], ".1f")
    M("HighThirdDfwLow", th["wild_lo"], "+.1f")
    M("HighThirdDfwHigh", th["wild_hi"], "+.1f")

    # support for the scenario among the affected first attempts
    sp = row(sup, entry_math_score="all with a score")
    M("AffectedMedianSize", sp["median_size_now_among_affected"], "int")
    M("AffectedMedianSizeAfterSplit", sp["median_size_after_split"], "int")
    # share whose course and term also held a section at or below the cap
    # (the cap is part of the field name)
    key = [k for k in sp
           if k.startswith("share_affected_in_cells_with_a_section_of_")]
    assert len(key) == 1 and int(key[0].split("_")[-3]) == cap, key
    M("AffectedShareWithSmallSection", 100 * float(sp[key[0]]), ".0f")

    # ----------------------------------- scenario across all the subjects
    tot = res["scenario_all_subjects"]
    tj = fix["scenario_all_subjects_joint"]
    assert abs(tot["dfw_outcomes_per_cohort"]
               - tj["dfw_outcomes_per_cohort"]) < 1e-6
    M("AllSectionsPerYear", tot["sections_per_year"], "int")
    M("AllSectionsAddedPerYear", tot["sections_added_per_year"], "int")
    M("AllDfwPerCohort", tj["dfw_outcomes_per_cohort"], "+.0f")
    M("AllDfwPerCohortLow", tj["lo"], "+.0f")
    M("AllDfwPerCohortHigh", tj["hi"], "+.0f")

    # ------------------------- sensitivity: the next mathematics course
    nf = fix["next_course_flow"]
    M("NextOriginFirstAttempts", nf["origin_first_attempts"], "int")
    M("NextContinuers", nf["take_a_later_mathematics_course"], "int")
    M("NextBothGrades", nf["with_grades_in_both_courses"], "int")
    M("NextDifferentInstructor", nf["next_course_different_instructor"],
      "int")
    allc = one(sub, lambda r: r["sample"].startswith("all continuers"))
    assert int(allc["rows"]) == nf["with_grades_in_both_courses"]
    assert abs(float(allc["next_grade_per_doubling_given_origin"])
               - res["leniency_check"]
               ["next_grade_per_doubling_given_origin_grade"]) < 1e-9
    M("NextGrade", allc["next_grade_per_doubling_given_origin"], "+.3f")
    M("NextGradeLow", allc["lo"], "+.3f")
    M("NextGradeHigh", allc["hi"], "+.3f")
    other = one(sub, lambda r: r["sample"].endswith("different instructor")
                and r["interval_from"] == "wild bootstrap")
    assert int(other["rows"]) == nf["next_course_different_instructor"]
    M("NextGradeDifferentInstructor",
      other["next_grade_per_doubling_given_origin"], "+.3f")
    M("NextGradeDifferentInstructorLow", other["lo"], "+.3f")
    M("NextGradeDifferentInstructorHigh", other["hi"], "+.3f")
    # continuation to another mathematics course within a year, in
    # percentage points per doubling (descriptive, seen before the freeze)
    ct = row(nxt, model="continuation: course-term effects", term="log2_size")
    assert ct["interval_from"] == "wild bootstrap"
    ce, chw = float(ct["estimate"]), float(ct["half_width"])
    # two decimals: the file holds four decimals of the proportion, and
    # with one decimal the value would fall on a rounding tie
    M("ContinuationPerDoubling", 100 * ce, "+.2f")
    M("ContinuationPerDoublingLow", 100 * (ce - chw), "+.1f")
    M("ContinuationPerDoublingHigh", 100 * (ce + chw), "+.1f")

    # ------------------ sensitivity: the banded form (mathematics, grade)
    # The edges of a band are part of the name of its term (size_11_30,
    # size_121_plus); the reference band is the one without a term.
    bands = sorted(
        ((int(r["term"].split("_")[1]), r["term"].split("_")[2], r)
         for r in coef if r["outcome"] == "grade" and r["subject"] == "MAT"
         and r["model"] == "bands" and r["term"].startswith("size_")),
        key=lambda b: b[0])
    small, above, big, top = bands                 # exactly four terms
    assert top[1] == "plus" and int(above[1]) + 1 == big[0]
    assert int(big[1]) + 1 == top[0]
    ref_low, ref_high = int(small[1]) + 1, above[0] - 1
    assert ref_low <= ref_high
    M("BandSmallLow", small[0], "int")
    M("BandSmallHigh", small[1], "int")
    M("BandSmallGrade", small[2]["estimate"], "+.3f")
    M("BandReferenceLow", ref_low, "int")
    M("BandReferenceHigh", ref_high, "int")
    M("BandMiddleLow", above[0], "int")
    M("BandMiddleHigh", above[1], "int")
    M("BandMiddleGrade", above[2]["estimate"], "+.3f")
    M("BandLargeLow", big[0], "int")
    # also the size above which the largest band begins
    M("BandLargeHigh", big[1], "int")
    M("BandLargeGrade", big[2]["estimate"], "+.3f")
    M("BandLargestGrade", top[2]["estimate"], "+.3f")

    # -------- calibration of the contrast tests on shuffled grades (rev5):
    # rejection rates at the nominal level, in percent
    shuffles = {r["shuffles"] for r in cal}
    assert len(shuffles) == 1
    M("ContrastShuffles", shuffles.pop(), "int")
    wild = [100 * float(r["wild_reject_05"]) for r in cal]
    clus = [100 * float(r["cluster_t_reject_05"]) for r in cal]
    M("ContrastWildRejectMin", min(wild), ".1f")
    M("ContrastWildRejectMax", max(wild), ".1f")
    M("ContrastClusterRejectMin", min(clus), ".1f")
    M("ContrastClusterRejectMax", max(clus), ".1f")

    # ---- the calibration of the dry runs: rejection rates at the nominal
    # 5% level over the subjects of the calibration, on shuffled grades
    dry = C("module_c/class_size/dryrun/cs_calibration.csv")
    assert len({r["shuffles"] for r in dry}) == 1
    M("DryShuffles", dry[0]["shuffles"], "int")
    M("DrySubjects", len(dry), "int")
    M("DryClusterRejectMin",
      100 * min(float(r["cluster_t_reject_05"]) for r in dry), ".1f")
    M("DryClusterRejectMax",
      100 * max(float(r["cluster_t_reject_05"]) for r in dry), ".1f")
    M("DryWildRejectMin",
      100 * min(float(r["wild_reject_05"]) for r in dry), ".1f")
    M("DryWildRejectMax",
      100 * max(float(r["wild_reject_05"]) for r in dry), ".1f")

    # ---- the descriptive curve of mathematics (figClassSizeUTSA): mean
    # grade in the smallest sections and at the reference size
    curve = J("student_success/figClassSizeUTSA_stats.json")
    M("CurveMatGpaSmallest", curve["mat_curve"]["gpa_at_smallest_size"],
      ".1f")
    M("CurveMatGpaReference", curve["mat_curve"]["gpa_at_reference_size"],
      ".1f")
    M("CurveReferenceSize", curve["mat_curve"]["reference_size"], "int")
    M("CurveMinStudents", curve["min_students"], "int")

    # --------------------------- counts that the text writes as words
    # The format "word" prints five, and "Word" prints Five for the start
    # of a sentence. Each value is the expression of the numeral macro of
    # the same quantity, or the output or constant named here.
    # subjects that enter the models (the numeral is \SizeSubjectsModeled)
    # and subjects that the entry rule leaves out
    M("SubjectsModeledCapitalWord", len(modeled), "Word")
    M("SubjectsOutsideWord", len(outside), "word")
    # The nested models of the comparison ladder (cs_figures.LADDER): each
    # is a column of the registered estimates, and the last is the primary
    # model, the one that H3 tests.
    ladder = ladder_models()
    assert all(k in g for k in ladder)
    assert abs(float(g[ladder[-1]]) - h3["mat_m3_grade_per_doubling"]) < 1e-4
    M("NestedModelsCapitalWord", len(ladder), "Word")
    # subjects whose size coefficient passes false-discovery control in
    # the primary model (grade outcome); the text names the subject
    M("SubjectsPassingCapitalWord", len(passing), "Word")
    return M.items
