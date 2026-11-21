"""Macros of the national position of the institution (College Scorecard
locator figure, manuscript Appendix B.5).

Sources: figures/paper0/figScorecardLocator_stats.json (the coordinates of
UT San Antonio, the locally weighted expectation of completion at its Pell
share, and the residual, per data year) and
figures/paper0/figScorecardLocator_data.csv (one row per institution and
data year), both written by programs/paper0/scorecard.py.

The two data years of the figure are the keys of the statistics file: the
earlier one is the baseline vintage, the later one the current vintage.
"""
from texmacros import C, J, Macros, const

TITLE = "National position of the institution (College Scorecard)"
SOURCE = ("figures/paper0/figScorecardLocator_stats.json, "
          "figures/paper0/figScorecardLocator_data.csv")


def build():
    s = J("paper0/figScorecardLocator_stats.json")
    data = C("paper0/figScorecardLocator_data.csv")
    unit = str(const("paper0/scorecard.py", "UTSA_UNITID"))
    M = Macros("Score")
    years = sorted(s)
    assert len(years) == 2 and years == sorted({r["data_year"] for r in data})
    for year, tag in zip(years, ("Baseline", "Current")):
        st = s[year]
        rows = [r for r in data if r["data_year"] == year]
        own = [r for r in rows if r["unitid"] == unit]
        assert len(own) == 1, (year, len(own))
        own = own[0]
        # the statistics file holds the same coordinates at three decimals
        assert len(rows) == st["n_institutions"]
        assert int(float(own["ugds"])) == st["utsa_ugds"]
        assert abs(float(own["c150_4"]) - st["utsa_c150_4"]) < 0.0005
        assert abs(float(own["pctpell"]) - st["utsa_pctpell"]) < 0.0005
        # the residual is completion minus the expectation
        assert abs(st["utsa_c150_4"] - st["lowess_expectation"]
                   - st["residual"]) < 0.0015

        # institutions of the comparison population in the data year
        M(tag + "Institutions", st["n_institutions"], "int")
        # UT San Antonio: undergraduates, completion within 150% of normal
        # time (first-time, full-time entrants), share of Pell recipients
        M(tag + "Undergraduates", own["ugds"], "int")
        M(tag + "Completion", own["c150_4"], ".3f")
        M(tag + "PellShare", own["pctpell"], ".3f")
        # completion expected at that Pell share (locally weighted fit over
        # the institutions of the data year), and the residual
        M(tag + "ExpectedCompletion", st["lowess_expectation"], ".3f")
        M(tag + "Residual", st["residual"], "+.3f")
    # the same residuals in percentage points of the completion rate, with
    # their direction in words: below the fitted value in the baseline
    # data year, above it in the current one
    lo, hi = s[years[0]]["residual"], s[years[1]]["residual"]
    assert lo < 0 < hi
    M("BaselinePointsBelow", 100 * lo, "a.1f")
    M("CurrentPointsAbove", 100 * hi, "a.1f")
    # share of the institutions that enter each local fit
    M("LowessFraction", const("paper0/scorecard.py", "LOWESS_FRAC"), ".1f")
    # data years (vintages) of the figure, written as a word in the text
    M("VintagesWord", len(years), "word")
    return M.items
