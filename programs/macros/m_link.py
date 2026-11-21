"""Macros of the linked entrant models: entrants of Fall 2014 through Fall
2019 linked to their sending schools and districts (manuscript Sections
sec:data:link and sec:results:summary, Appendices app:methods:link and
sec:link).

Sources, under figures/module_c/:
  cohorts_2014_2019/  the run of module_c/run_module_c.py on the cohorts of
                      deviation D1: sample flow, variance partition,
                      preparation and subject coefficients, results.json,
                      and the predictive evaluation the plan specified
  rev5/               the corrections of deviation D2, written by
                      module_c/rev5_module_c.py and module_c/mc_figures.py:
                      joint intervals of the pooled coefficients, the two
                      prediction tasks, the run without the aid variables
Where both folders hold a quantity, the rev5 value is read. The CSV files
hold four decimals; a results.json holds full precision and is read first
when it holds the quantity.

The counts that the text writes as words are at the end of build(). Those
that describe the design (the cohorts of the plan as first written, the
cycles of the school snapshot, the levels of the entry mathematics course,
the folds) are read from the constants of module_c/mc_data.py and
module_c/run_module_c.py; no output of the eleven-cohort run is read.
"""
import ast

from texmacros import PROGRAMS, C, J, Macros, const, fmt, row

TITLE = "Linked entrant models (entrants of Fall 2014 to Fall 2019)"
SOURCE = ("figures/module_c/cohorts_2014_2019 (results.json, stage0_*.csv, "
          "q1_*.csv, q2_*.csv, ladder_*.csv, sensitivity.csv) and "
          "figures/module_c/rev5 "
          "(results.json, q2_pooled_joint.csv, q2_weighted_summary.json, "
          "ladder_*.csv, sensitivity_no_aid.csv)")

BASE, REV = "module_c/cohorts_2014_2019/", "module_c/rev5/"
RUN, FIX = "module_c/run_module_c.py", "module_c/rev5_module_c.py"
# the two prediction tasks, as rev5_module_c.py names them in its outputs
HELD_OUT = "within offering, schools held out"
LATER = "later cohorts from earlier cohorts"
# Unadjusted two-sided level at which the interval of a coefficient is
# said to exclude zero. A convention that no program holds as a constant:
# mc_figures.py writes `p < 0.05` inline where it shades the cells of
# Figure figSubjectPredictors.
LEVEL = 0.05


def default_arg(rel, func, name):
    """the default value of an argument of a function of a program, read
    from its source without importing it (a parameter the program does not
    hold as a module-level constant):
    default_arg('module_c/mc_models.py', 'bh', 'q')"""
    tree = ast.parse((PROGRAMS / rel).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func:
            args, defaults = node.args.args, node.args.defaults
            named = dict(zip([a.arg for a in args[len(args) - len(defaults):]],
                             defaults))
            return ast.literal_eval(named[name])
    raise KeyError((rel, func, name))


def median(values):
    s = sorted(values)
    n, h = len(s), len(s) // 2
    assert n
    return s[h] if n % 2 else (s[h - 1] + s[h]) / 2


def build():
    M = Macros("Link")
    res, rev = J(BASE + "results.json"), J(REV + "results.json")
    assert res["first_cohort"] == rev["first_cohort"]
    h1, h2 = res["H1"], rev["H2"]
    # standard deviation of the entry mathematics score over the pooled
    # cohorts, in score points: the unit of every preparation coefficient
    sd = h1["math_score_sd_points"]

    # ------------------------------------------------------- population
    flow = {r["step"]: int(r["students"])
            for r in C(BASE + "stage0_sample_flow.csv")}
    entrants = flow["first-time fall entrants, Fall "
                    f"{res['first_cohort']} to Fall {res['last_cohort']}"]
    scored = flow["linked sample with both scores (Q1)"]
    assert scored == h1["students"]
    M("Entrants", entrants, "int")
    M("Sample", flow["linked sample (school and district context complete)"],
      "int")
    M("SampleScored", scored, "int")
    M("SampleGradeCohorts", flow["Q2 cohorts, linked"], "int")
    # share of the fall entrants who did not apply for aid (no AGI recorded)
    M("NonApplicantPct",
      100 * (1 - flow["aid applicants (AGI recorded)"] / entrants), ".1f")

    # ------------------------------------------- subjects and parameters
    subj = C(BASE + "stage0_subjects.csv")
    quant = [r for r in subj if r["class"] == "quantitative"]
    wsum = J(REV + "q2_weighted_summary.json")
    minimum = const(RUN, "MIN_SUBJECT")
    assert len(subj) == wsum["subjects"]
    assert len(subj) - len(quant) == h2["subjects"]
    assert all(int(r["linked_students"]) >= minimum for r in subj)
    M("Subjects", len(subj), "int")
    M("QuantSubjects", len(quant), "int")
    M("OtherSubjects", h2["subjects"], "int")
    M("SubjectMinimum", minimum, "int")
    # level of the Benjamini-Hochberg control across subjects
    M("FdrLevel", default_arg("module_c/mc_models.py", "bh", "q"), ".2f")
    M("ScoreSD", sd, ".0f")

    # ------------------------------------- where preparation varies (Q1)
    vp = C(BASE + "q1_variance_partition.csv")

    def shares(outcome):
        """shares of the variance that remains after entry cohort and CAP
        status: between districts, between schools, within schools"""
        r = row(vp, outcome=outcome, step="design")
        v = [float(r[k]) for k in ("var_district", "var_school",
                                   "var_student")]
        return [x / sum(v) for x in v]

    d, s, e = shares("math")
    M("VarDistrictPct", 100 * d, ".1f")
    M("VarSchoolPct", 100 * s, ".1f")
    M("VarBetweenPct", 100 * (d + s), ".0f")
    M("VarWithinPct", 100 * e, ".1f")
    M("VarWithinPctRound", 100 * e, ".0f")
    d, s, e = shares("gap")          # mathematics minus verbal
    M("GapVarBetweenPct", 100 * (d + s), ".1f")
    M("GapVarWithinPct", 100 * e, ".1f")
    # reduction of a component from the first step, after family
    # resources, demographics, and district poverty (+P), then with the
    # school block (+S)
    step_p = row(vp, outcome="math", step="+P")
    step_s = row(vp, outcome="math", step="+S")
    M("VarDistrictReducedPct", 100 * float(step_p["explained_district"]),
      ".0f")
    M("VarSchoolReducedPct", 100 * float(step_p["explained_school"]), ".0f")
    M("VarSchoolReducedWithSchoolPct",
      100 * float(step_s["explained_school"]), ".0f")

    # ---------------------- preparation coefficients, full model (Q1)
    q1 = C(BASE + "q1_coefficients.csv")

    def b1(outcome, model, term, field="estimate"):
        return float(row(q1, outcome=outcome, model=model, term=term)[field])

    idx = res["index_on_math_score"]
    assert fmt(idx["estimate"], ".4f") == fmt(
        b1("math", "full", "advmath_index"), ".4f")
    # score points per standard deviation of the predictor: the
    # coefficient in standard deviations of the score, times `sd`
    M("IndexPoints", idx["estimate_score_points"], ".1f")
    M("IndexPointsSigned", idx["estimate_score_points"], "+.1f")
    pov = sd * b1("math", "full", "district_poverty")
    M("PovertyPoints", pov, "a.1f")
    M("PovertyPointsSigned", pov, "+.1f")
    M("IncomeRankPoints", sd * b1("math", "full", "agi_rank"), "+.1f")
    # first-generation entrants against entrants who are not
    M("FirstGenPoints", sd * b1("math", "full", "fg:First Generation"),
      "a.1f")

    # income rank between sending schools and within them
    M("IncomeBetween", b1("math", "income gradient", "agi_between"), ".3f")
    M("IncomeWithin", b1("math", "income gradient", "agi_within"), ".3f")
    gap_bw = "agi_between_minus_within"
    M("IncomeBetweenMinusWithin", b1("math", "income gradient", gap_bw),
      ".2f")
    # the difference over its standard error
    M("IncomeBetweenMinusWithinZ",
      b1("math", "income gradient", gap_bw)
      / b1("math", "income gradient", gap_bw, "se"), ".1f")

    # H1: advanced-mathematics index on mathematics minus verbal
    assert h1["supported"]
    M("HOne", h1["estimate"], "+.3f")
    M("HOneLow", h1["lo"], ".3f")
    M("HOneHigh", h1["hi"], ".3f")
    M("HOnePoints", h1["estimate_score_points"], ".1f")
    M("GapIncomeWithin", b1("gap", "income gradient", "agi_within"), "+.2f")
    M("GapMale", b1("gap", "full", "gender:Male"), "+.2f")
    # the three largest coefficients of the full model of this measure.
    # Hispanic students are the reference group of the ethnicity terms.
    gap_full = [r for r in q1 if r["outcome"] == "gap"
                and r["model"] == "full" and r["term"] != "const"]
    assert not any("Hispanic" in r["term"] for r in gap_full)
    top = sorted(gap_full, key=lambda r: -abs(float(r["estimate"])))[:3]
    assert [r["term"] for r in top] == ["eth:International", "eth:Asian",
                                        "gender:Male"]
    M("GapInternational", b1("gap", "full", "eth:International"), "+.2f")
    M("GapInternationalSE", b1("gap", "full", "eth:International", "se"),
      ".2f")
    M("GapAsian", b1("gap", "full", "eth:Asian"), "+.2f")
    # advanced-mathematics index on the level of the entry mathematics
    # course (secondary outcome)
    M("IndexEntryLevel", b1("entry_math_level", "secondary",
                            "advmath_index"), "+.2f")

    # variation explained with sending schools held out (linear model)
    lad0 = C(BASE + "ladder_skill.csv")
    M("MathHeldOutPct", 100 * float(row(
        lad0, target="Q1 math score", family="linear")["oof_r2"]), ".0f")
    # one decimal: the source holds 0.0650, a rounding tie in whole percent
    M("GapHeldOutPct", 100 * float(row(
        lad0, target="Q1 math-verbal gap", family="linear")["oof_r2"]), ".1f")

    # ------------------------------- the run without the aid variables
    na = C(REV + "sensitivity_no_aid.csv")

    def noaid(model, quantity, field="without_aid_variables"):
        return float(row(na, model=model, quantity=quantity)[field])

    prep_math = "preparation: mathematics score"
    prep_gap = "preparation: mathematics minus verbal"
    M("NoAidIndexPoints", sd * noaid(prep_math, "advmath_index"), "+.1f")
    # from the coefficient at full precision (results.json, no_aid)
    full = J(REV + "results.json")["no_aid"]
    assert abs(full["score_sd_points"] - sd) < 1e-6
    M("NoAidPovertyPoints", full["score_sd_points"] * full["preparation"][
        "mathematics score"]["district_poverty"]["without_aid_variables"][
            "coef"], "+.1f")
    M("NoAidHOne", noaid(prep_gap, "advmath_index"), "+.3f")
    M("NoAidHOneLow", noaid(prep_gap, "advmath_index", "lo_without"), ".3f")
    M("NoAidHOneHigh", noaid(prep_gap, "advmath_index", "hi_without"), ".3f")
    M("NoAidPooledMathOther", noaid(
        "first-year grades, non-quantitative subjects", "mathematics score"),
      ".3f")
    M("NoAidSubjectsPassing", noaid(
        "first-year grades", "subjects where the mathematics score passes "
        "false-discovery control with a positive sign"), "int")

    # ------------------------------------------- subject models (Q2)
    prim = C(BASE + "q2_primary.csv")
    grade = [r for r in prim if r["outcome"] == "grade"]
    assert len(grade) == len(subj)
    mat_g = row(prim, outcome="grade", subject="MAT")
    mat_d = row(prim, outcome="dfw", subject="MAT")
    # mathematics courses: grade points, and DFW in percentage points
    M("MatMathGrade", mat_g["math"], ".2f")
    M("MatVerbalGrade", mat_g["verbal"], "+.2f")
    M("MatMathDfwPoints", 100 * float(mat_d["math"]), "a.1f")
    M("MatMathDfwPointsSigned", 100 * float(mat_d["math"]), "+.1f")

    # subjects whose mathematics coefficient is positive under
    # false-discovery control
    passing = [r for r in grade
               if r["bh_math"] == "1" and float(r["math"]) > 0]
    assert len(passing) == wsum["subjects_passing"]
    assert (sum(r["class"] == "other" for r in passing)
            == h2["subjects_passing_fdr_positive"])
    # the text says "all" of the quantitative subjects
    assert sum(r["class"] == "quantitative" for r in passing) == len(quant)
    M("SubjectsPassing", len(passing), "int")
    # the text says the coefficient is positive in "all" subjects
    assert all(float(r["math"]) > 0 for r in grade)
    M("OtherSubjectsPassing", h2["subjects_passing_fdr_positive"], "int")
    M("PassingAttemptsPct", 100 * wsum[
        "share_of_first_attempts_in_subjects_passing_fdr_math"], ".0f")

    # pooled coefficients with the joint (school-clustered) intervals
    pj = C(REV + "q2_pooled_joint.csv")

    def pooled(cls, contrast, field="pooled"):
        return float(row(pj, **{"outcome": "grade", "class": cls,
                                "contrast": contrast})[field])

    assert h2["supported"]
    assert fmt(h2["pooled"], ".4f") == fmt(pooled("other", "math"), ".4f")
    M("PooledMathOther", h2["pooled"], ".3f")
    M("PooledMathOtherTwo", h2["pooled"], ".2f")
    M("PooledMathOtherLow", h2["lo_joint"], ".3f")
    M("PooledMathOtherHigh", h2["hi_joint"], ".3f")
    # the interval under the independence the plan assumed. The lower end
    # is not assigned (discrepancy_link.json): the text prints 0.112.
    M("PooledMathOtherLowIndep", h2["lo_independent"], ".3f")
    M("PooledMathOtherHighIndep", h2["hi_independent"], ".3f")
    M("PooledVerbalOther", pooled("other", "verbal"), ".3f")
    diff = "math_minus_verbal"
    M("PooledDiffOther", pooled("other", diff), "+.3f")
    M("PooledDiffOtherLow", pooled("other", diff, "lo_joint"), "+.3f")
    M("PooledDiffOtherHigh", pooled("other", diff, "hi_joint"), "+.3f")
    M("PooledMathQuant", pooled("quantitative", "math"), ".3f")
    M("PooledMathQuantTwo", pooled("quantitative", "math"), ".2f")
    M("PooledMathQuantLow", pooled("quantitative", "math", "lo_joint"), ".3f")
    M("PooledMathQuantHigh", pooled("quantitative", "math", "hi_joint"),
      ".3f")
    M("PooledVerbalQuant", pooled("quantitative", "verbal"), ".3f")
    # Added for the text that quotes the results a second time (unit
    # `reuse`): the pooled verbal coefficients with two decimals, the
    # companions of PooledMathOtherTwo and PooledMathQuantTwo.
    # PooledVerbalQuantTwo is not assigned (discrepancy_reuse.json): the
    # source holds 0.0648 and the text prints 0.07.
    M("PooledVerbalOtherTwo", pooled("other", "verbal"), ".2f")
    M("PooledVerbalQuantTwo", pooled("quantitative", "verbal"), ".2f")

    # subject coefficients averaged with weights equal to first attempts
    wfa = "weighted_by_first_attempts"
    M("WeightedMathOther", pooled("other", "math", wfa), ".3f")
    M("WeightedMathQuant", pooled("quantitative", "math", wfa), ".3f")
    M("WeightedDiffOtherLowIndep", pooled("other", diff, "w_lo_independent"),
      ".3f")
    M("WeightedDiffOtherHighIndep", pooled("other", diff, "w_hi_independent"),
      ".3f")
    # The joint interval of the weighted difference, as
    # mc_figures.pooled_table prints it in Table tab:subjectpooled: the
    # weighted mean of the subject coefficients of q2_primary.csv at full
    # precision, with the joint half-width of q2_pooled_joint.csv.
    other = [r for r in grade if r["class"] == "other"]
    wdiff = (sum(float(r["rows"]) * float(r[diff]) for r in other)
             / sum(float(r["rows"]) for r in other))
    assert fmt(wdiff, ".4f") == fmt(pooled("other", diff, wfa), ".4f")
    half = (pooled("other", diff, "w_hi_joint")
            - pooled("other", diff, "w_lo_joint")) / 2
    M("WeightedDiffOtherLow", wdiff - half, "+.3f")
    M("WeightedDiffOtherHigh", wdiff + half, "+.3f")

    # correlation between the mathematics coefficients of two subjects
    corr = rev["subject_correlation"]["grade math"]
    M("SubjectCorrMean", corr["mean_off_diagonal"], ".2f")
    M("SubjectCorrMax", corr["largest"], ".2f")

    # ------------- first prediction task: sending schools held out
    # (grades; skill is the proportional reduction in squared error)
    bs = C(REV + "ladder_blocks_summary.csv")
    name = const(FIX, "BLOCK_NAME")
    assert all(int(r["subjects"]) == len(subj) for r in bs)

    def block(label, field="median_added_r2"):
        return float(row(bs, outcome="grade",
                         block_added_in_order=label)[field])

    skill_w = wsum["oof_r2_grade_linear"]
    assert fmt(block("all blocks"), ".3f") == fmt(
        skill_w["median_across_subjects"], ".3f")
    M("SkillMedian", block("all blocks"), ".3f")
    M("SkillMedianPct", 100 * block("all blocks"), ".1f")
    M("SkillMinPct", 100 * block("all blocks", "smallest"), ".0f")
    M("SkillMaxPct", 100 * block("all blocks", "largest"), ".0f")
    M("SkillWeightedPct", 100 * skill_w["weighted_by_first_attempts"], ".1f")
    # skill added by a block when it enters in order: median across
    # subjects, with the interval from resampling sending schools
    M("PrepAdded", block(name["T"]), ".3f")
    M("PrepAddedLow", block(name["T"], "median_lo"), ".3f")
    M("PrepAddedHigh", block(name["T"], "median_hi"), ".3f")
    M("FamilyAdded", block(name["F"]), ".3f")
    M("DemoAdded", block(name["D"]), ".3f")
    positive = "subjects_with_positive_increment"
    M("PovertyAdded", block(name["P"]), ".4f")
    M("PovertyAddedSigned", block(name["P"]), "+.4f")
    M("PovertyAddedLow", block(name["P"], "median_lo"), "+.4f")
    M("PovertyAddedHigh", block(name["P"], "median_hi"), "+.4f")
    M("PovertyAddedMin", block(name["P"], "smallest"), "+.3f")
    M("PovertyAddedMax", block(name["P"], "largest"), "+.3f")
    M("PovertyAddedPositive", block(name["P"], positive), "int")
    M("SchoolAdded", block(name["S_comp"]), "+.4f")
    M("SchoolAddedLow", block(name["S_comp"], "median_lo"), "+.4f")
    M("SchoolAddedHigh", block(name["S_comp"], "median_hi"), ".4f")
    M("SchoolAddedMin", block(name["S_comp"], "smallest"), "+.3f")
    M("SchoolAddedMax", block(name["S_comp"], "largest"), "+.3f")
    M("SchoolAddedPositive", block(name["S_comp"], positive), "int")

    # the evaluation the plan specified (course-by-term means from all
    # rows), linear model: medians across subjects
    wsum0 = J(BASE + "q2_weighted_summary.json")
    lb0 = C(BASE + "ladder_blocks.csv")

    def plan_added(b):
        v = [float(r["added_r2_in_order"]) for r in lb0
             if r["target"].startswith("Q2 grade ") and r["family"] == "linear"
             and r["block"] == b]
        assert len(v) == len(subj)
        return median(v)

    M("PlanSkillMedianPct",
      100 * wsum0["oof_r2_grade_linear"]["median_across_subjects"], ".1f")
    M("PlanPrepAdded", plan_added("T"), ".3f")
    M("PlanPovertyAdded", plan_added("P"), ".4f")
    M("PlanSchoolAdded", plan_added("S_comp"), "+.4f")

    # ---- second task (later cohorts from earlier cohorts) and the DFW
    # outcome: per-subject rows of rev5/ladder_skill.csv
    sk = C(REV + "ladder_skill.csv")

    def rows_of(task, outcome, family):
        sel = [r for r in sk if r["task"] == task and r["family"] == family
               and r["target"].startswith(f"Q2 {outcome} ")]
        assert len(sel) == len(subj), (task, outcome, family, len(sel))
        return sel

    def skill(task, outcome, family, field="r2_against_baseline"):
        return [float(r[field]) for r in rows_of(task, outcome, family)]

    ridge = skill(LATER, "grade", "ridge")
    # two decimals: the median is 0.0835 at the four decimals of the
    # source, a rounding tie with one decimal
    M("LaterRidgeMedianPct", 100 * median(ridge), ".2f")
    M("LaterRidgeMinPct", 100 * min(ridge), ".0f")
    M("LaterRidgeMaxPct", 100 * max(ridge), ".0f")
    M("LaterLinearMedianPct", 100 * median(skill(LATER, "grade", "linear")),
      ".1f")
    lb = C(REV + "ladder_blocks.csv")

    def later_added(b):
        v = [float(r["added_r2_in_order"]) for r in lb
             if r["task"] == LATER and r["family"] == "linear"
             and r["block"] == b and r["target"].startswith("Q2 grade ")]
        assert len(v) == len(subj)
        return median(v)

    M("LaterPovertyAdded", later_added("P"), ".3f")
    M("LaterSchoolAdded", later_added("S_comp"), "+.3f")

    # DFW: median area under the curve of the linear model, and of the
    # baseline rate alone
    M("AucHeldOut", median(skill(HELD_OUT, "dfw", "linear", "auc")), ".2f")
    M("AucLater", median(skill(LATER, "dfw", "linear", "auc")), ".2f")
    M("AucHeldOutBaseline",
      median(skill(HELD_OUT, "dfw", "linear", "auc_baseline_only")), ".2f")
    M("AucLaterBaseline",
      median(skill(LATER, "dfw", "linear", "auc_baseline_only")), ".2f")

    # largest gain in skill of the random forest: over the linear model
    # in the first task, over ridge regression in the second
    forest = rev["forest_against_linear"][f"{HELD_OUT}, grade"]
    assert forest["subjects"] == len(subj)
    M("ForestGainHeldOut", forest["largest_forest_minus_linear"], ".3f")
    later = {fam: {r["target"]: float(r["r2_against_baseline"])
                   for r in rows_of(LATER, "grade", fam)}
             for fam in ("rf", "ridge")}
    assert later["rf"].keys() == later["ridge"].keys()
    M("ForestGainLater", max(later["rf"][t] - later["ridge"][t]
                             for t in later["rf"]), ".3f")

    def fell_back(task):
        """percent of the evaluated grade rows whose baseline fell back on
        the mean of the course (first task) or of the subject (second)"""
        sel = rows_of(task, "grade", "linear")
        return (100 * sum(int(r["rows_whose_baseline_fell_back"]) for r in sel)
                / sum(int(r["rows"]) for r in sel))

    M("HeldOutFallbackPct", fell_back(HELD_OUT), ".2f")
    M("LaterFallbackPct", fell_back(LATER), ".1f")

    # --------------- other predictors of the grade models (step b)
    qc = [r for r in C(BASE + "q2_coefficients.csv")
          if r["outcome"] == "grade" and r["step"] == "b"]

    def clear(term):
        """estimates of a term in the subjects where its interval excludes
        zero (unadjusted)"""
        return [float(r["estimate"]) for r in qc
                if r["term"] == term and float(r["p"]) < LEVEL]

    cap = clear("cap")
    assert sum(r["term"] == "cap" for r in qc) == len(subj)
    assert all(v > 0 for v in cap)
    M("CapGradeMin", min(cap), ".1f")
    M("CapGradeMax", max(cap), ".1f")
    M("CapSubjects", len(cap), "int")
    exam = clear("credit_exam")
    assert all(v > 0 for v in exam)
    M("ExamCreditSubjects", len(exam), "int")
    mat_dual = row(qc, subject="MAT", term="credit_dual_only")
    mat_exam = row(qc, subject="MAT", term="credit_exam")
    # the text says the interval of the examination-credit coefficient in
    # mathematics includes zero
    assert float(mat_dual["p"]) < LEVEL <= float(mat_exam["p"])
    M("MatDualCredit", mat_dual["estimate"], "+.2f")
    M("MatExamCredit", mat_exam["estimate"], "+.2f")
    fg = clear("fg:First Generation")
    assert all(v < 0 for v in fg)
    M("FirstGenGradeMin", min(abs(v) for v in fg), ".2f")
    M("FirstGenGradeMax", max(abs(v) for v in fg), ".2f")
    M("FirstGenSubjects", len(fg), "int")

    # --------------------------- counts that the text writes as words
    # The format "word" prints seven, and "Word" prints Seven for the start
    # of a sentence. Each value is the expression of the numeral macro of
    # the same quantity, or the output or constant named here.
    # subjects classed as quantitative (the numeral is \LinkQuantSubjects)
    M("QuantSubjectsWord", len(quant), "word")
    M("QuantSubjectsCapitalWord", len(quant), "Word")
    # the plan classes these subjects as quantitative before estimation;
    # those with enough entrants are the quantitative subjects modeled
    plan_quant = const(RUN, "QUANT")
    assert {r["subject"] for r in quant} < set(plan_quant)
    M("PlanQuantSubjectsCapitalWord", len(plan_quant), "Word")
    # subjects whose verbal coefficient is above the mathematics
    # coefficient (grade outcome), and those where the difference passes
    # false-discovery control
    below = [r for r in grade if float(r["verbal"]) > float(r["math"])]
    passing_diff = [r for r in below if r["bh_diff"] == "1"]
    assert {r["subject"] for r in passing_diff} == {"POL", "ANT"}
    M("VerbalAboveMathSubjectsWord", len(below), "word")
    M("VerbalAboveMathPassingWord", len(passing_diff), "word")
    # variance between schools and districts with one decimal, for the
    # sentence that also prints the share within schools
    d, s, e = shares("math")
    M("VarBetweenOnePct", 100 * (d + s), ".1f")
    # subjects whose grade model holds fewer students than the minimum that
    # admits a subject (the grade models use graded first attempts only)
    below = [r["subject"] for r in grade if int(r["students"]) < minimum]
    M("SubjectsGradeBelowMinimumWord", len(below), "word")

    # The entry cohorts of the plan as first written: the default window of
    # module_c/mc_data.py, which the restricted run narrows from its first
    # cohort (deviation D1).
    plan_first = const("module_c/mc_data.py", "FIRST_COHORT")
    plan_last = const("module_c/mc_data.py", "LAST_COHORT")
    assert plan_first < res["first_cohort"] and plan_last == res["last_cohort"]
    M("PlanCohortsWord", plan_last - plan_first + 1, "word")

    # Years between an entrant's senior year and the CRDC cycle of the
    # school snapshot: the cycle nearest the senior year, as cycle_of() of
    # mc_data.py chooses it among the cycles of its constant CYCLES. The
    # largest lag of the cohorts of this run is read from the cohort flow,
    # and the largest lag of the earlier cohorts of the plan is computed
    # with the same rule.
    cycle_years = const("module_c/mc_data.py", "CYCLES")

    def lag(cohort):
        return min(abs(cohort - year) for year in cycle_years)

    cohort_flow = C(BASE + "stage0_cohort_flow.csv")
    assert [int(r["cohort"]) for r in cohort_flow] == list(
        range(res["first_cohort"], res["last_cohort"] + 1))
    assert all(int(r["lag_years"]) == lag(int(r["cohort"]))
               for r in cohort_flow)
    M("SnapshotMaxLagWord", max(int(r["lag_years"]) for r in cohort_flow),
      "word")
    M("SnapshotMaxLagEarlierWord",
      max(lag(c) for c in range(plan_first, res["first_cohort"])), "word")
    # The one exception to that lag: the earliest cycle records dual
    # enrollment as an indicator only, so for the entrants assigned to it
    # the data step takes the dual-enrollment rate from the next cycle.
    # Its distance from the senior year of those entrants, and how many
    # linked entrants it concerns.
    cycles = const("module_c/mc_data.py", "CYCLES")   # spring year: cycle
    first_cycle, next_cycle = sorted(cycles)[0], sorted(cycles)[1]
    early = [r for r in cohort_flow if r["crdc_cycle"] == cycles[first_cycle]]
    assert early and cycles[next_cycle] == "2015-16"
    M("DualSubstituteMaxLagWord",
      max(next_cycle - int(r["cohort"]) for r in early), "word")
    M("DualSubstituteLinked", sum(int(r["linked"]) for r in early), "int")

    # Sensitivity runs of H1 (the variants of run_sensitivity, one row
    # each): the estimate is positive in every run, and the text names the
    # runs whose interval reaches zero.
    sens = C(BASE + "sensitivity.csv")
    assert fmt(row(sens, variant="primary")["h1_index_on_gap"], ".4f") == fmt(
        h1["estimate"], ".4f")
    assert all(float(r["h1_index_on_gap"]) > 0 for r in sens)
    reaching = [r["variant"] for r in sens if float(r["h1_lo"]) <= 0]
    assert reaching == ["entrants through Fall 2015", "CAP flag set"], reaching
    M("SensitivityRunsWord", len(sens), "word")
    M("SensitivityReachingZeroWord", len(reaching), "word")

    # folds of the first prediction task, which hold out whole sending
    # schools: the default of folds_by_group, which rev5_module_c.py calls
    # without the argument
    M("FoldsWord", default_arg(RUN, "folds_by_group", "k"), "word")
    # levels of the scale of the entry mathematics course (the secondary
    # outcome entry_math_level): the distinct values of MAT_LEVEL
    M("EntryLevelsWord",
      len(set(const("module_c/mc_data.py", "MAT_LEVEL").values())), "word")
    return M.items
