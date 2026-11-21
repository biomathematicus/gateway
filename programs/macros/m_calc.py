"""Macros of the district Calculus panels (manuscript Figure 1).

Source: figures/paper0/figCalculusPanels_stats.json, written by
programs/paper0/course_panels_figure.py.
"""
from texmacros import J, Macros, fmt

TITLE = "District Calculus enrollment (Figure 1)"
SOURCE = "figures/paper0/figCalculusPanels_stats.json"


def build():
    s = J("paper0/figCalculusPanels_stats.json")
    M = Macros("Calc")
    us, tx, un = s["per_hs_student"], s["texas"], s["per_hs_student_unweighted"]
    lm = s["bexar_landmarks"]
    ah, ed = lm["Alamo Heights ISD"], lm["Edgewood ISD"]
    ns, ne = lm["Northside ISD"], lm["North East ISD"]

    M("Districts", s["n_districts"], "int")
    M("DistrictsWithIncome", s["n_with_income"], "int")
    M("DistrictsZero", s["districts_reporting_zero"], "int")
    M("DistrictsAboveDisplay", s["districts_above_display"], "int")
    M("BexarDistricts", s["n_bexar"], "int")

    # national fit: enrollees per high-school student on the poverty rate
    M("MeanPerHundred", 100 * us["mean"], ".1f")
    M("Slope", us["slope"], "s.3f")
    M("SlopeSE", us["se_state_cluster"], ".3f")
    M("SeatsPerTenPoints", 10 * us["slope"], "a.1f")
    M("RelDecline", us["rel10_pct"], "a.1f")
    M("RelSigned", us["rel10_pct"], "s.1f")
    M("RelDeclineRounded", us["rel10_pct"], "a.0f")
    M("SlopeUnweighted", un["slope"], "s.3f")
    M("SlopeUnweightedSE", un["se_state_cluster"], ".3f")

    # Texas
    M("TexasDistricts", tx["n_districts"], "int")
    M("TexasSlope", tx["slope"], "s.3f")
    M("TexasSlopeSE", tx["se_robust"], ".3f")
    M("TexasRelDecline", tx["rel10_pct"], "a.1f")

    # the school districts of Bexar County named in the text
    M("AlamoPovertyPct", 100 * ah["pov_rate"], ".0f")
    M("EdgewoodPovertyPct", 100 * ed["pov_rate"], ".0f")
    M("AlamoPerHundred", 100 * ah["per_hs_student"], ".1f")
    M("EdgewoodPerHundred", 100 * ed["per_hs_student"], ".1f")
    M("AlamoRatio", ah["ratio_to_national"], ".1f")
    M("AlamoRatioTwo", ah["ratio_to_national"], ".2f")
    M("EdgewoodRatio", ed["ratio_to_national"], ".2f")
    # the text gives one value for the two largest districts
    assert fmt(ns["ratio_to_national"], ".2f") == fmt(ne["ratio_to_national"], ".2f")
    M("LargestTwoRatio", ns["ratio_to_national"], ".2f")
    M("SanAntonioRatio", lm["San Antonio ISD"]["ratio_to_national"], ".2f")

    # district income: weighted mean of tract median household incomes.
    # The text rounds the ends of the county's range to the ten thousand:
    # "near" the low end, "above" the high end.
    low = max(ed["income_k"], lm["San Antonio ISD"]["income_k"])
    M("IncomeLowNear", round(low / 10) * 10 * 1000, "int")
    M("IncomeHighAbove", (ah["income_k"] // 10) * 10 * 1000, "int")
    M("IncomeCorr", s["income"]["weighted_pearson"], ".2f")
    M("IncomeSpearman", s["income"]["spearman"], ".2f")
    M("IncomePovertyCorr", s["income_poverty_pearson_unweighted"], "s.2f")
    return M.items
