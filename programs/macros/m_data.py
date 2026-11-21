"""Macros of the data appendix (Appendix C): the sizes of the sources as
the analyses read them, and the source-data flaws with their standing
corrections.

Sources, all under programs/figures:
  001_stats.json            analysis/stability.py: the SAIPE district series
  022_stats.json            student_success/provision_stability.py: explicit
                            zeros and the offering indicator, by CRDC cycle
  024_stats.json            analysis/algebra2_robust.py: the ladder of
                            minimum district sizes
  ingest/data_inventory_stats.json
                            ingest/data_inventory.py: the public tables of
                            the project database as loaded (rows, the
                            Algebra II item of the CRDC school panel by
                            cycle, the districts with more enrollees than
                            children, the district frames of the course
                            families), and the stored school key of the
                            2015-16 raw file
  paper0/figCourseGradients_stats.json
                            paper0/course_gradient_figure.py: the frames of
                            the course-family comparison
Parameters are read from the constants of ingest/crdc_panel.py (the CRDC
cycles), ingest/crdc_courses.py (the course families of each cycle),
ingest/edge_schools.py (the cycles of the geocodes), analysis/
algebra2_robust.py (the minimum number of children), and paper0/
course_gradient_figure.py (the core courses of the district frames).

The row counts of the public tables as loaded (the last column of the table
of sources) come from ingest/data_inventory.py, which counts them in the
project database. The loaders rebuild the 2015-16 school key before
loading, so the same program reads the stored key from the raw file. The
counts of the institutional records are in m_pop.py and m_xwalk.py.

Two counts that the text shares with Figure 1 (the districts of the common
frame and the districts of Bexar County) are printed with the macros of
m_calc.py; this module asserts that the outputs agree.
"""
import ast
import math

from texmacros import C, J, PROGRAMS, Macros, const, fmt, row

TITLE = "Data appendix: sources and source-data flaws (Appendix C)"
SOURCE = ("figures/001_stats.json, 022_stats.json, 024_stats.json, "
          "ingest/data_inventory_stats.json, "
          "paper0/figCourseGradients_stats.json")

CYCLE = "2017-18"            # the cycle of the district analyses
EARLIEST = "2011-12"         # the first CRDC cycle of the five-cycle panel
EARLIEST_COURSES = "2013-14"  # the first cycle of the course-family table
DAMAGED_KEY_CYCLE = "2015-16"  # the cycle whose wide file ships a damaged key


def course_families():
    """{cycle: set of course families} of the SUBJECTS specification of
    ingest/crdc_courses.py. The specification is written {cycle: {family:
    columns}} for the first cycle and {cycle: dict(_COMMON, family=columns)}
    for the later ones, which const() cannot evaluate, so the family names
    are read from the syntax tree of the program."""
    tree = ast.parse((PROGRAMS / "ingest/crdc_courses.py")
                     .read_text(encoding="utf-8"))
    value = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            value[node.targets[0].id] = node.value
    common = set(ast.literal_eval(value["_COMMON"]))
    spec = value["SUBJECTS"]
    assert isinstance(spec, ast.Dict), type(spec)
    out = {}
    for key, val in zip(spec.keys, spec.values):
        cycle = ast.literal_eval(key)
        if isinstance(val, ast.Dict):
            out[cycle] = {ast.literal_eval(k) for k in val.keys}
        else:
            assert (isinstance(val, ast.Call) and val.func.id == "dict"
                    and len(val.args) == 1
                    and val.args[0].id == "_COMMON"), ast.dump(val)
            out[cycle] = common | {kw.arg for kw in val.keywords}
    return out


def build():
    M = Macros("Data")

    # (the populations of the institutional analyses are in m_pop.py and
    # m_xwalk.py)

    # ------------------------------------------------ table of sources
    # SAIPE district series
    sa = J("001_stats.json")
    M("SaipeVintages", sa["n_vintages"], "int")
    ever, always = sa["n_leaid_ever"], sa["n_leaid_all_years"]
    M("SaipeDistrictsEver", ever, "int")
    M("SaipeDistrictsEveryVintage", always, "int")
    # share of the district identifiers that appear in every vintage
    M("SaipeDistrictsEveryVintagePct", 100 * always / ever, ".1f")

    # CRDC: the cycles of the school panel and the course families loaded
    cycles = const("ingest/crdc_panel.py", "SPEC")
    stab = J("022_stats.json")
    zero = {r["cycle"]: r for r in stab["zero_rate_by_cycle"]}
    assert set(zero) == set(cycles), (sorted(zero), sorted(cycles))
    M("CrdcCycles", len(cycles), "int")

    fam = course_families()
    assert EARLIEST_COURSES == min(fam)
    later = [fam[c] for c in fam if c != EARLIEST_COURSES]
    assert all(f == later[0] for f in later), "later cycles differ"
    assert later[0] == set(const("paper0/course_gradient_figure.py",
                                 "SUBJECTS")), "loader and figure differ"
    assert fam[EARLIEST_COURSES] < later[0]
    M("CourseFamilies", len(later[0]), "int")
    M("CourseFamiliesEarliestCycle", len(fam[EARLIEST_COURSES]), "int")

    # the public tables as loaded: rows counted in the project database
    inv = J("ingest/data_inventory_stats.json")
    par = inv["parameters"]
    assert par["primary_cycle"] == CYCLE
    assert par["earliest_cycle"] == EARLIEST
    assert par["damaged_key_cycle"] == DAMAGED_KEY_CYCLE
    size = inv["tables"]
    assert size["saipe_district_year"]["n_vintages"] == sa["n_vintages"]
    M("SaipeRows", size["saipe_district_year"]["n_rows"], "int")

    # the Algebra II item of the CRDC school panel, by cycle
    by = inv["crdc_alg2_by_cycle"]
    assert set(by) == set(cycles)
    assert size["crdc_school_cycle"]["n_cycles"] == len(cycles)
    for c in by:
        # the schools with a count are the schools of the stability analysis
        assert by[c]["n_schools_alg2_count"] == zero[c]["n"], c
        assert (fmt(100 * by[c]["n_schools_alg2_zero"]
                    / by[c]["n_schools_alg2_count"], ".2f")
                == fmt(zero[c]["pct_zero"], ".2f")), c
    M("CrdcSchoolCycleRows", size["crdc_school_cycle"]["n_rows"], "int")
    M("CrdcDistrictCycleRows", size["crdc_district_cycle"]["n_rows"], "int")
    course = size["crdc_course_school"]
    assert ({c: r["n_course_families"] for c, r in course["by_cycle"].items()}
            == {c: len(f) for c, f in fam.items()}), "table and loader differ"
    M("CourseFamilyRows", course["n_rows"], "int")

    # geocodes, neighborhood context, and the two relationship tables
    assert (set(size["edge_school_cycle"]["by_cycle"])
            == set(const("ingest/edge_schools.py", "CYCLES")))
    M("EdgeSchoolRows", size["edge_school_cycle"]["n_rows"], "int")
    M("AtlasTracts", size["opportunity_atlas_tract"]["n_rows"], "int")
    M("AtlasZctas", size["opportunity_atlas_zcta"]["n_rows"], "int")
    M("ZctaTractWeights", size["zcta_tract_weights"]["n_rows"], "int")
    M("DistrictTractShares", size["district_tract_shares"]["n_rows"], "int")

    # Inventory of the public input files (ingest/source_inventory.py,
    # data_sources.csv at the root of the repository): how many files it
    # lists, how many have the recorded hash on disk, and how many
    # archives the acquisition manifest (data_manifest.csv) records.
    src = J("data_sources_stats.json")
    assert src["files_with_recorded_hash_on_disk"] == src["files"]
    M("SourceFiles", src["files"], "int")
    M("ManifestArchivesWord", src["manifest_archives"], "word")


    # ------------------------------------------------- explicit zeros
    # share of schools with an explicit zero for Algebra II, by cycle
    assert EARLIEST == min(zero)
    after = [zero[c]["pct_zero"] for c in zero if c != EARLIEST]
    assert zero[EARLIEST]["pct_zero"] > max(after)
    M("AlgTwoZeroPctEarliestCycle", zero[EARLIEST]["pct_zero"], ".2f")
    M("AlgTwoZeroPctLaterMin", min(after), ".2f")
    M("AlgTwoZeroPctLaterMax", max(after), ".2f")

    # the offering indicator ("reports a non-negative Algebra II count"):
    # agreement between pairs of cycles over all schools, and Cohen's kappa
    pairs = stab["pairwise_all"]
    agree = [p["pct_agree_offers_UNINFORMATIVE"] for p in pairs]
    kappa = [p["kappa"] for p in pairs]
    assert all(math.isfinite(k) for k in kappa)
    # the text gives one rounded value of kappa for every pair of cycles
    assert len({fmt(k, ".0f") for k in kappa}) == 1
    M("OfferAgreePctMin", min(agree), ".0f")
    M("OfferAgreePctMax", max(agree), ".0f")
    M("OfferKappa", max(kappa, key=abs), ".0f")

    # ------------------------------- reporting rate and the skip code
    # schools with an Algebra II count per district of the cycle: excess
    # of the earliest cycle over the mean of the later cycles, in percent
    rate = {c: by[c]["n_schools_alg2_count"] / by[c]["n_districts"]
            for c in by}
    rest = [rate[c] for c in rate if c != EARLIEST]
    assert rate[EARLIEST] > max(rest)
    excess = 100 * (rate[EARLIEST] / (sum(rest) / len(rest)) - 1)
    assert math.isclose(
        excess, inv["reporting_rate"]["pct_excess_over_later_mean"])
    M("ReportingRateExcessPct", excess, ".0f")

    # schools per cycle whose Algebra II item holds the skip code: mean of
    # the cycles that use reserve codes, rounded to the unit of the program
    skip = inv["alg2_skip_code"]
    coded = skip["cycles_with_reserve_codes"]
    assert set(coded) == set(by) - {EARLIEST}
    per_cycle = sum(by[c]["n_schools_skip_code"] for c in coded) / len(coded)
    unit = skip["rounding_unit"]
    M("AlgTwoSkipCodeSchoolsRounded", unit * round(per_cycle / unit), "int")
    # share of schools that hold an Algebra II count, mean of those cycles
    share = [100 * by[c]["n_schools_alg2_count"] / by[c]["n_schools"]
             for c in coded]
    M("AlgTwoSchoolsWithCountPct", sum(share) / len(share), ".0f")

    # schools of the primary cycle that hold an Algebra II count, over
    # every school of the public-use file. The school panel keeps the
    # schools with a numeric district identifier, and its count is the
    # one of the stability analysis.
    held = inv["alg2_count_schools"]
    assert held["cycle"] == CYCLE
    assert (held["numeric_district_id"]["n_schools_alg2_count"]
            == zero[CYCLE]["n"])
    M("AlgTwoSchoolsWithCount",
      held["all_schools"]["n_schools_alg2_count"], "int")

    # Algebra II enrollment of the cycle with the damaged stored key, on
    # the rebuilt key
    M("AlgTwoEnrolleesRebuiltKey",
      by[DAMAGED_KEY_CYCLE]["alg2_enrollees"], "int")
    # the same cycle read with the key as the raw file stores it: schools
    # of the file, schools lost when one row per stored key is kept, and
    # the Algebra II enrollment that survives
    sk = inv["stored_key_2015_16"]
    assert sk["alg2_enrollees_rebuilt_key"] == by[DAMAGED_KEY_CYCLE][
        "alg2_enrollees"]
    M("StoredKeySchools", sk["n_schools"], "int")
    M("StoredKeySchoolsLost", sk["n_schools_lost_under_stored_key"], "int")
    M("AlgTwoEnrolleesStoredKey", sk["alg2_enrollees_stored_key"], "int")
    M("StoredKeyEnrollmentLostPct", sk["pct_enrollment_lost"], ".0f")

    # ------------------------------------------- frame-mismatch ratios
    # Algebra II enrollees per child aged 5 to 17 on the poverty rate,
    # under a ladder of minimum district sizes (children aged 5 to 17)
    rob = J("024_stats.json")
    floor = const("analysis/algebra2_robust.py", "MIN_POP")
    steps = const("analysis/algebra2_robust.py", "POP_LADDER")
    assert rob["min_pop_5_17"] == floor
    ladder = [r for r in rob["pop_ladder"] if r["cycle"] == CYCLE]
    assert [r["min_pop_5_17"] for r in ladder] == steps
    every = row(ladder, min_pop_5_17=min(steps))     # no district left out
    kept = row(ladder, min_pop_5_17=floor)           # at the standing floor
    assert min(steps) < floor and every["n"] > kept["n"]

    # standard error of the population-weighted national slope with and
    # without clustering on states (identical point estimate)
    cs = [r for r in rob["cross_section"] if r["cycle"] == CYCLE
          and r["scope"] == "national"
          and r["weighting"] == "population-weighted"]
    assert len(cs) == 1
    M("SlopeSeStateClustered", cs[0]["se_clustered"], ".4f")
    M("SlopeSeNaive", cs[0]["se_naive"], ".4f")
    M("SlopeSeRatio", cs[0]["se_clustered"] / cs[0]["se_naive"], ".0f")

    M("MinChildren", floor, "int")
    M("AlgTwoDistrictsNoFloor", every["n"], "int")
    M("AlgTwoPerChildMax", every["max_alg2_per_child"], ".1f")
    M("AlgTwoPerChildMaxFloor", kept["max_alg2_per_child"], ".2f")
    # the unweighted slope changes sign; the weighted slope does not move
    assert every["slope_unweighted"] > 0 > kept["slope_unweighted"]
    M("UnweightedSlopeNoFloor", every["slope_unweighted"], "+.3f")
    M("UnweightedSlopeFloor", kept["slope_unweighted"], "s.3f")
    assert (fmt(every["slope_weighted"], "s.3f")
            == fmt(kept["slope_weighted"], "s.3f"))
    M("WeightedSlope", every["slope_weighted"], "s.3f")
    # distance between the unweighted and the weighted slope at the floor
    M("SlopeGapFloor", kept["slope_unweighted"] - kept["slope_weighted"],
      "a.3f")
    # range of the weighted slope over the whole ladder
    weighted = [r["slope_weighted"] for r in ladder]
    assert max(weighted) < 0
    M("WeightedSlopeLadderFlattest", max(weighted), "s.4f")
    M("WeightedSlopeLadderSteepest", min(weighted), "s.4f")

    # the districts with more Algebra II enrollees than children, counted
    # in the project database on the districts of the ladder
    mis = inv["frame_mismatch"]
    assert mis["cycle"] == CYCLE and mis["min_children"] == floor
    for fit, step in ((mis["fits"]["all_districts"], every),
                      (mis["fits"]["at_least_min_children"], kept)):
        assert fit["n_districts"] == step["n"]
        assert (fmt(fit["max_ratio"], ".2f")
                == fmt(step["max_alg2_per_child"], ".2f"))
        for k in ("slope_unweighted", "slope_weighted"):
            assert fmt(fit[k], "s.4f") == fmt(step[k], "s.4f"), k
    # the fit that leaves out only the districts with a ratio above one:
    # the unweighted slope is already negative, and the weighted slope
    # prints the same in all three fits
    only = mis["fits"]["without_ratio_above_one"]
    assert only["slope_unweighted"] < 0
    assert (every["n"] - only["n_districts"]
            == mis["ratio_above_one"]["n_districts"])
    assert (fmt(only["slope_weighted"], "s.3f")
            == fmt(every["slope_weighted"], "s.3f"))
    M("UnweightedSlopeWithoutMismatch", only["slope_unweighted"], "s.3f")
    above = mis["ratio_above_one"]
    # the floor on children removes each of those districts
    assert above["n_below_min_children"] == above["n_districts"]
    M("MismatchMedianChildren", above["median_children"], "int")

    # (the students with a misread school ZIP are counted by
    # student_success/linkage_profile.py: \XwalkMisreadZipStudents)

    # ------------------------------------- frames of the course families
    grad = J("paper0/figCourseGradients_stats.json")
    assert grad["primary_cycle"] == CYCLE
    fr = grad["cycles"][CYCLE]
    main, neutral = fr["figure5_frame"], fr["neutral_frame"]
    for f in (main, neutral):
        assert f["child"]["n_districts"] == f["hs"]["n_districts"]
    # the common frame is printed with \CalcDistricts, and the districts of
    # Bexar County with \CalcBexarDistricts
    calc = J("paper0/figCalculusPanels_stats.json")
    assert calc["cycle"] == CYCLE
    assert calc["n_districts"] == main["child"]["n_districts"]
    assert calc["n_bexar"] == grad["bexar_" + CYCLE]["n_districts"]
    M("NeutralFrameDistricts", neutral["child"]["n_districts"], "int")
    # districts that the neutral frame adds to the common frame (no
    # Algebra II reported, enrollment in other core courses), and the
    # children aged 5 to 17 they hold: differences of the frame totals of
    # the figure, which equal the group as ingest/data_inventory.py counts
    # it in the project database.
    added = neutral["child"]["n_districts"] - main["child"]["n_districts"]
    children = (neutral["child"]["denominator_total"]
                - main["child"]["denominator_total"])
    assert added > 0 and children > 0
    own = inv["course_frames"][CYCLE]
    assert par["core_courses"] == const("paper0/course_gradient_figure.py",
                                        "HS_CORE")
    assert (par["min_children"] == floor
            == const("paper0/course_gradient_figure.py", "MIN_POP"))
    for name, frame in (("common_frame", main), ("neutral_frame", neutral)):
        assert own[name]["n_districts"] == frame["child"]["n_districts"]
        assert own[name]["children"] == frame["child"]["denominator_total"]
    assert (own["alg2_frame_incomplete_total"]["n_districts"]
            == fr["n_incomplete_excluded"])
    group = own["no_alg2_other_core"]
    assert (added, children) == (group["n_districts"], group["children"])
    assert group["complete_totals"]["n_districts"] == added
    M("NoAlgTwoDistricts", added, "int")
    M("NoAlgTwoChildren", children, "int")
    # districts serving high-school grades with no enrollment in any of
    # the core courses, and the children aged 5 to 17 they hold
    M("NoCoreDistricts", own["no_core_enrollment"]["n_districts"], "int")
    M("NoCoreChildren", own["no_core_enrollment"]["children"], "int")

    # ------------------------------------- counts the text writes as words
    M("CrdcCyclesWord", len(cycles), "word")
    # districts with more Algebra II enrollees than children aged 5 to 17
    M("MismatchDistrictsWord", above["n_districts"], "word")
    M("MismatchDistrictsCapitalWord", above["n_districts"], "Word")
    # districts of the Algebra II frame with an incomplete total in some
    # course family, in the primary cycle and in the two other cycles of
    # the course-family comparison
    other = sorted(c for c in grad["cycles"] if c != CYCLE)
    assert len(other) == 2 and other[0] < CYCLE < other[1]
    M("IncompleteDistrictsCapitalWord", fr["n_incomplete_excluded"], "Word")
    M("IncompleteDistrictsEarlierWord",
      grad["cycles"][other[0]]["n_incomplete_excluded"], "word")
    M("IncompleteDistrictsLaterWord",
      grad["cycles"][other[1]]["n_incomplete_excluded"], "word")
    # core high-school mathematics and science courses of the frames
    M("CoreCoursesWord", len(par["core_courses"]), "word")
    return M.items
