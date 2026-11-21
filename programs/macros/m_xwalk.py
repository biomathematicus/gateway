"""Macros of the linkage of students to sending schools and districts:
the school crosswalk and its coverage, the disposition of the students,
the selection audits, and the sending profiles. Every student count is of
the students active between Fall 2014 and Fall 2019.

Sources: figures/student_success/linkage_profile_stats.json, written by
programs/student_success/linkage_profile.py; constants of
programs/xwalk/hs_crosswalk.py, programs/xwalk/fallback_vintages.py, and
programs/student_success/linkage_profile.py.
"""
from texmacros import J, Macros, const

TITLE = "Linkage to sending schools and districts"
SOURCE = "figures/student_success/linkage_profile_stats.json"

XW = "xwalk/hs_crosswalk.py"
LP = "student_success/linkage_profile.py"


def build():
    s = J("student_success/linkage_profile_stats.json")
    M = Macros("Xwalk")
    a = s["active"]
    cov, disp, aud = a["coverage"], a["disposition"]["n_by_group"], a["audit"]

    # ---- the matching score and its thresholds
    M("WeightContain", const(XW, "W_CONTAIN"), ".2f")
    M("WeightJaccard", const(XW, "W_JACCARD"), ".2f")
    M("WeightTrigram", const(XW, "W_TRIGRAM"), ".2f")
    M("AutoScore", const(XW, "AUTO_SCORE"), ".2f")
    M("AutoMargin", const(XW, "AUTO_MARGIN"), ".2f")
    M("MinCandidateScore", const(XW, "MIN_CANDIDATE_SCORE"), ".2f")
    M("FirstRunScore", const("xwalk/fallback_vintages.py",
                             "FIRST_RUN_SCORE"), ".2f")
    M("RecoveryScore", const("xwalk/fallback_vintages.py",
                             "RECOVERY_SCORE"), ".2f")

    # ---- the crosswalk and its staged coverage
    rows_all = s["crosswalk"]["n_name_rows_by_decision"]
    M("NameRowsAll", s["crosswalk"]["n_name_rows"], "int")
    # name rows that went to hand review: accepted and rejected
    M("ReviewRows", rows_all["auto_adj"] + rows_all["rejected"], "int")
    M("NameRows", cov["n_name_rows"], "int")
    stage = {x["stage"]: x for x in cov["stages"]}
    assert list(stage) == list(const(LP, "USABLE"))
    M("StageAutoPct", stage["auto"]["pct_usable"], ".1f")
    M("StageAdjudicatedPct", stage["auto_adj"]["pct_usable"], ".1f")
    M("StageVintagePct", stage["auto_vint"]["pct_usable"], ".1f")
    assert stage["auto_ccd"]["pct_usable"] == cov["pct_usable"]
    M("CoveragePct", cov["pct_usable"], ".1f")
    M("UsableStudents", cov["n_usable"], "int")
    M("PrivateNames", cov["n_name_rows_by_decision"]["private"], "int")
    M("PrivateNamedStudents", cov["n_private"], "int")
    M("PrivateNamedPct", cov["pct_private"], ".1f")
    M("RecoveredInDirectoryPct",
      a["directory_recovery"]["pct_in_original_directory"], ".0f")
    M("MatchedSchools", cov["n_matched_schools"], "int")
    M("MatchedDistricts", cov["n_matched_districts"], "int")
    M("SchoolsInTablePct", cov["pct_matched_schools_in_table"], ".1f")

    # ---- the school-level table and the cycle it copies
    vc = s["school_table"]["vintage_check"]
    cyc = const(LP, "SCHOOL_TABLE_CYCLE")
    M("TableCycleSchools", vc[cyc]["n_schools"], "int")
    M("TableCycleEqualPct", vc[cyc]["pct_equal"], ".1f")
    other = [v["pct_equal"] for k, v in vc.items() if k != cyc]
    M("TableOtherCyclesLow", min(other), ".1f")
    M("TableOtherCyclesHigh", max(other), ".1f")

    # ---- disposition of the students of the per-student table
    assert sum(disp.values()) == a["disposition"]["n_students"]
    M("Matched", disp["matched"], "int")
    M("OutsideTexas", disp["outside_texas"], "int")
    M("Unresolved", disp["unresolved"], "int")
    M("Private", disp["private"], "int")
    M("NoSchool", disp["no_school"], "int")
    M("Rejected", disp["rejected"], "int")

    # ---- selection audit: the unresolved against the matched
    cell, test = aud["cells"], aud["matched_vs_unresolved"]
    for key, name, spec in (("dual", "Dual", ".1f"), ("ap", "Ap", ".2f"),
                            ("pell", "Pell", ".1f"),
                            ("first_dfw", "FirstCourse", ".1f")):
        M(f"Unresolved{name}Pct", cell["unresolved"][f"pct_{key}"], spec)
        M(f"Matched{name}Pct", cell["matched"][f"pct_{key}"], spec)
        M(f"{name}Z", test[key]["z"], "s.2f")
        M(f"{name}ZClustered", test[key]["z_clustered"], "s.2f")
    M("UnresolvedScore", cell["unresolved"]["mean_sat"], ".0f")
    M("MatchedScore", cell["matched"]["mean_sat"], ".0f")
    M("ScoreZ", test["sat"]["z"], "s.2f")
    M("ScoreZClustered", test["sat"]["z_clustered"], "s.2f")
    # the largest of the school-clustered statistics, in absolute value
    M("MaxZClustered", max(abs(test[k]["z_clustered"]) for k in
                           ("dual", "ap", "sat", "pell", "first_dfw")), ".1f")
    M("UnresolvedSchools", test["dual"]["n_schools_b"], "int")
    M("MatchedFirstGenPct", cell["matched"]["pct_first_gen"], ".1f")

    # ---- the students with no Texas school to resolve
    for g, name in (("outside_texas", "OutsideTexas"),
                    ("no_school", "NoSchool"), ("all", "All")):
        M(f"{name}TransferPct", cell[g]["pct_transfer"], ".1f")
        M(f"{name}ApPct", cell[g]["pct_ap"], ".1f")
        M(f"{name}DualPct", cell[g]["pct_dual"], ".1f")
    M("PrivatePellPct", cell["private"]["pct_pell"], ".1f")
    M("PrivateFirstGenPct", cell["private"]["pct_first_gen"], ".1f")

    # ---- sending-school provision and arriving credit
    pr = a["provision"]
    bands = const(LP, "BANDS")
    lo = next(c for c in pr["cells"] if c["ap_offer_band"] == bands[0])
    hi = next(c for c in pr["cells"] if c["ap_offer_band"] == bands[-1])
    M("ProvisionStudents", pr["n_students"], "int")
    M("ProvisionSchools", pr["n_schools"], "int")
    M("NoApBandApPct", lo["pct_ap"], ".1f")
    M("NoApBandDualPct", lo["pct_dual"], ".1f")
    M("TopBandApPct", hi["pct_ap"], ".1f")
    M("TopBandDualPct", hi["pct_dual"], ".1f")
    # lower edge of the top band: share of the school's students in AP
    # mathematics, in percent
    M("TopBandEdgePct", const(LP, "BAND_EDGES")[-1], ".0f")
    M("NoApBandMedianEnrollment", lo["median_school_enrollment"], "int")
    M("TopBandMedianEnrollment", hi["median_school_enrollment"], "int")

    # ---- child poverty of the sending districts
    sp = a["sending_poverty"]
    M("PovertyStudents", sp["n_students"], "int")
    M("PovertyDistricts", sp["n_districts"], "int")
    M("PovertyMedianStudents", sp["median_student_weighted"], ".1f")
    M("PovertyMedianChildren", sp["median_child_weighted"], ".1f")
    M("PovertyMedianGap", sp["median_child_weighted"]
      - sp["median_student_weighted"], ".1f")
    M("LargestBinLow", sp["largest_bin"]["low"], ".0f")
    M("LargestBinHigh", sp["largest_bin"]["high"], ".1f")
    M("LargestBinPct", sp["largest_bin"]["pct_students"], ".0f")
    top = {t["name"]: t for t in sp["top_districts"]}
    ns = top["Northside Independent School District"]
    ne = top["North East Independent School District"]
    # the two largest senders, as the text says
    assert [t["name"] for t in sp["top_districts"][:2]] == [ns["name"],
                                                            ne["name"]]
    M("NorthsideStudents", ns["n_students"], "int")
    M("NorthsidePovertyPct", ns["pov_rate"], ".1f")
    M("NorthEastStudents", ne["n_students"], "int")
    M("NorthEastPovertyPct", ne["pov_rate"], ".1f")

    # ---- the home-ZIP branch
    d, n = a["distance"], a["neighborhood"]
    zz, pt = d["zip_to_zip"], d["zip_to_school_point"]
    M("DistanceNinetieth", zz["p90"], ".1f")
    M("DistanceNinetyFifth", zz["p95"], ".1f")
    M("FarMiles", const(LP, "FAR_MILES"), ".0f")
    assert zz["far_top_home_prefix"] == "782"     # San Antonio ZIP codes
    M("FarLocalHomePct", zz["far_top_home_share"], ".1f")
    M("PrimaryMiles", const(LP, "PRIMARY_MILES"), ".0f")
    M("StrictMiles", const(LP, "STRICT_MILES"), ".0f")
    M("WithinPrimaryPct", zz["pct_within_primary"], ".1f")
    M("PointWithinPrimaryPct", pt["point_pct_within_primary"], ".1f")
    M("ZipZeroPct", pt["zip_pct_zero"], ".1f")
    M("PointZeroPct", pt["point_pct_zero"], ".1f")
    # students whose school ZIP reads as another state because a leading
    # zero was dropped (Houston homes paired with New Jersey ZIP codes)
    assert zz["n_misread_school_zip"] is not None
    M("MisreadZipStudents", zz["n_misread_school_zip"], "int")
    M("BestTractSharePct", 100 * n["best_tract_share_median"], ".0f")
    M("TractsPerZip", n["tracts_with_context_per_zip_mean"], ".1f")
    M("BestTractShareAllZips",
      s["tract_assignment"]["best_tract_share_median_unweighted"], ".3f")
    M("ContextCoveragePct", n["pct_covered"], ".1f")
    return M.items
