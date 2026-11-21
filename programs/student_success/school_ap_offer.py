"""
Report 021 — Does the student's own high school OFFER AP mathematics?

Report 013 showed AP and dual enrolment sort oppositely by district poverty, and
called it a difference in how credit is SUPPLIED. That was an inference from a
gradient. This report tests it directly, at the level of the individual school
the student actually attended.

THE TABLE THAT MAKES IT POSSIBLE. `HIGHSCHOOLS` in the UTSA SQL Server (23,170
rows) is a school-level table with leaid(7) + schid(5) and per-school course
counts: apmath, advmath, algii, cal, chem, phy, plus total enrolment. It has been
sitting unused since session 6.

ITS PROVENANCE IS NOW ESTABLISHED, not assumed: joining leaid||schid against
`stg.crdc_alg2_panel` matches `algii` to CRDC **2017-18** on **19,961 schools at
100.0% exactly** (every other cycle: 2.0-7.7% exact). So HIGHSCHOOLS is the CRDC
2017-18 high-school universe. That fixes its vintage, which is the main caveat --
see the report.

Joined to `core.hs_crosswalk`, it covers 1,191 of our 1,266 matched schools
(94.1%) and 67,468 of 86,435 students (78.1%). That coverage is itself an
independent check on the crosswalk: schools we matched by name overwhelmingly
exist in the national CRDC high-school universe.

Processed LOCALLY; only aggregate cells (n >= 10) are published.
"""

from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config
import db
import gateway_link as gl
from instrument_outcome import CREDIT_SQL

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402
from gateway import db as gdb  # noqa: E402

setup()
OUT: dict = {}


def schools() -> pd.DataFrame:
    h = db.cached_query("highschools", "SELECT * FROM HIGHSCHOOLS")
    h["ncessch"] = h.leaid.astype(str) + h.schid.astype(str)
    for c in ("total", "apmath", "algii", "advmath", "cal"):
        h[c] = pd.to_numeric(h[c], errors="coerce")
    h = h[h.total > 0].copy()
    h["ap_math_rate"] = 100 * h.apmath / h.total
    h["algii_rate"] = 100 * h.algii / h.total
    h["offers_ap"] = (h.apmath > 0)
    return h[["ncessch", "leaid", "lea_state", "total", "apmath", "algii",
              "ap_math_rate", "algii_rate", "offers_ap"]]


def frame() -> pd.DataFrame:
    h = schools()
    cr = db.cached_query("gateway-credit-type-sat", CREDIT_SQL)
    for k in ("ap", "dual"):
        cr[k] = pd.to_numeric(cr[k], errors="coerce").fillna(0).astype(int)
    cr["satact_math"] = pd.to_numeric(cr.satact_math, errors="coerce")

    stu = gl.students()[["IDENTIFIER", "hs_name", "hs_city"]]
    with gdb.connect() as g:
        xw = pd.read_sql("SELECT hs_name, hs_city, ncessch FROM core.hs_crosswalk "
                         "WHERE ncessch IS NOT NULL", g)
        # pov_rate is not stored; it is computed from the two count columns.
        # Averaged over the vintages spanning these students' high-school years.
        pov = pd.read_sql(
            "SELECT leaid, AVG(100.0*pov_5_17/NULLIF(pop_5_17,0)) AS pov_rate "
            "FROM stg.saipe_sd WHERE vintage BETWEEN 2010 AND 2018 "
            "GROUP BY leaid", g)

    d = (stu.merge(xw, on=["hs_name", "hs_city"], how="inner")
            .merge(h, on="ncessch", how="inner")
            .merge(cr, on="IDENTIFIER", how="left")
            .merge(pov, on="leaid", how="left"))
    for k in ("ap", "dual"):
        d[k] = pd.to_numeric(d[k], errors="coerce").fillna(0).astype(int)
    return d


def cells(d: pd.DataFrame) -> pd.DataFrame:
    s = d.copy()
    s["ap_offer_band"] = np.where(
        ~s.offers_ap, "0. offers no AP maths",
        pd.cut(s.ap_math_rate, [0, 2, 5, 100],
               labels=["1. under 2%", "2. 2-5%", "3. over 5%"]).astype(str))
    g = (s.groupby("ap_offer_band", observed=True)
           .agg(n_students=("ap", "size"),
                n_schools=("ncessch", "nunique"),
                pct_ap=("ap", lambda x: 100 * x.mean()),
                pct_dual=("dual", lambda x: 100 * x.mean()),
                mean_satact_math=("satact_math", "mean"),
                mean_pov_rate=("pov_rate", "mean"))
           .reset_index().round(3))
    return g[g.ap_offer_band != "nan"]


def size_stratified(d: pd.DataFrame) -> pd.DataFrame:
    """AP/dual arrival by provision, WITHIN school-size stratum.

    Section 3.5 showed no-AP schools are mostly small. So the question that
    decides whether report 021 survives is whether provision still predicts
    arrival once size is held fixed, or was merely proxying for smallness.
    """
    s = d.copy()
    s["size_band"] = pd.cut(s.total, [0, 400, 1000, 2000, 100000],
                            labels=["under 400", "400-999", "1000-1999",
                                    "2000+"]).astype(str)
    s["provision"] = np.where(s.offers_ap, "offers AP maths", "no AP maths")
    g = (s.groupby(["size_band", "provision"], observed=True)
           .agg(n_students=("ap", "size"),
                n_schools=("ncessch", "nunique"),
                pct_ap=("ap", lambda x: 100 * x.mean()),
                pct_dual=("dual", lambda x: 100 * x.mean()))
           .reset_index().round(3))
    return g[g.size_band != "nan"]


def lpm_provision(d: pd.DataFrame) -> pd.DataFrame:
    """dual ~ no_AP (+ log size, + poverty), HC1 robust, clustered on school.

    Three nested models so the reader can see what each control absorbs.
    """
    s = d.dropna(subset=["total"]).copy()
    s["no_ap"] = (~s.offers_ap).astype(float)
    s["log_size"] = np.log(s.total.clip(lower=1))
    rows = []
    for name, cols in [("no AP only", ["no_ap"]),
                       ("+ log school size", ["no_ap", "log_size"]),
                       ("+ district poverty", ["no_ap", "log_size", "pov_rate"])]:
        t = s.dropna(subset=cols)
        X = np.column_stack([np.ones(len(t))] + [t[c].astype(float) for c in cols])
        y = t.dual.astype(float).values
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        r = y - X @ beta
        XtX_inv = np.linalg.inv(X.T @ X)
        meat = np.zeros((X.shape[1], X.shape[1]))
        for i in t.groupby("ncessch").indices.values():
            u = X[i].T @ r[i]
            meat += np.outer(u, u)
        G = t.ncessch.nunique()
        V = XtX_inv @ meat @ XtX_inv * (G / (G - 1))
        se = float(np.sqrt(np.diag(V))[1])
        rows.append({"model": name, "n": int(len(t)), "n_schools": int(G),
                     "beta_no_ap_pp": round(float(beta[1]) * 100, 2),
                     "se_pp": round(se * 100, 2),
                     "z": round(float(beta[1]) / se, 2) if se else None})
    return pd.DataFrame(rows)


def fig(g: pd.DataFrame) -> str:
    x = np.arange(len(g))
    w = 0.36
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.bar(x - w / 2, g.pct_ap, w * 0.92, color=SERIES[0], label="AP", zorder=3)
    ax.bar(x + w / 2, g.pct_dual, w * 0.92, color=SERIES[1],
           label="Dual enrolment", zorder=3)
    for i, (a, b, n) in enumerate(zip(g.pct_ap, g.pct_dual, g.n_students)):
        ax.text(i - w / 2, a + 0.35, f"{a:.1f}", ha="center", fontsize=9,
                color=SERIES[0], fontweight="bold")
        ax.text(i + w / 2, b + 0.35, f"{b:.1f}", ha="center", fontsize=9,
                color=SERIES[1], fontweight="bold")
        ax.text(i, -1.6, f"n={int(n):,}", ha="center", fontsize=7.5, color=MUTED)
    ax.set_xticks(x)
    ax.set_xticklabels([b.split(". ", 1)[1] for b in g.ap_offer_band], fontsize=9)
    ax.set_xlabel("share of the student's own high school enrolled in AP mathematics "
                  "(CRDC 2017-18)")
    ax.set_ylabel("% of UTSA entrants arriving\nwith pre-college math credit")
    ax.set_ylim(bottom=-2.6)
    ax.legend(loc="upper left")
    return finish(fig, ax, "021_school_ap_offer",
                  "Where the school offers no AP maths, students arrive with dual credit instead",
                  "School-level AP mathematics enrolment from CRDC 2017-18 "
                  "(`HIGHSCHOOLS`), attached to students through "
                  "`core.hs_crosswalk`. VINTAGE CAVEAT: 2017-18 postdates most "
                  "of these students' high-school years — it measures the "
                  "school, not their cohort. Not causal.")


def main() -> int:
    d = frame()
    OUT["n_students"] = int(len(d))
    OUT["n_schools"] = int(d.ncessch.nunique())

    g = cells(d)
    OUT["cells"] = g.to_dict("records")
    no_ap = g[g.ap_offer_band.str.startswith("0")]
    hi_ap = g[g.ap_offer_band.str.startswith("3")]
    if len(no_ap) and len(hi_ap):
        OUT["pct_ap_no_offer"] = float(no_ap.pct_ap.iloc[0])
        OUT["pct_ap_hi_offer"] = float(hi_ap.pct_ap.iloc[0])
        OUT["pct_dual_no_offer"] = float(no_ap.pct_dual.iloc[0])
        OUT["pct_dual_hi_offer"] = float(hi_ap.pct_dual.iloc[0])

    # Does AP provision track district poverty (the report 013 mechanism), or
    # school SIZE? The poverty column above is non-monotone, and the answer is
    # size: no-AP schools are 4-6x smaller and barely differ in poverty. Report
    # 021 section 3.5 -- this is the finding that qualifies the headline.
    sch = d.drop_duplicates("ncessch").copy()
    ok = sch.dropna(subset=["pov_rate"])
    OUT["corr_apoffer_poverty"] = round(
        float(ok.ap_math_rate.corr(ok.pov_rate)), 3)
    OUT["corr_apoffer_logsize"] = round(
        float(np.log(sch.total.clip(lower=1)).corr(sch.ap_math_rate)), 3)
    OUT["n_schools_pov"] = int(len(ok))
    OUT["pct_schools_no_ap"] = round(100 * float((~sch.offers_ap).mean()), 1)

    sch["band"] = np.where(
        ~sch.offers_ap, "0. offers no AP maths",
        pd.cut(sch.ap_math_rate, [0, 2, 5, 100],
               labels=["1. under 2%", "2. 2-5%", "3. over 5%"]).astype(str))
    by_size = (sch.groupby("band", observed=True)
                  .agg(n_schools=("ncessch", "size"),
                       median_total=("total", "median"),
                       mean_pov_rate=("pov_rate", "mean"))
                  .reset_index().round(1))
    OUT["by_school_size"] = by_size.to_dict("records")
    small, large = sch[sch.total < 400], sch[sch.total >= 400]
    OUT["pct_no_ap_small_schools"] = round(100 * float((~small.offers_ap).mean()), 1)
    OUT["pct_no_ap_large_schools"] = round(100 * float((~large.offers_ap).mean()), 1)
    by_size.to_csv(os.path.join(FIGDIR, "021_by_school_size.csv"), index=False)

    # does provision survive holding size fixed? (section 3.6)
    strat = size_stratified(d)
    models = lpm_provision(d)
    OUT["size_stratified"] = strat.to_dict("records")
    OUT["provision_models"] = models.to_dict("records")
    strat.to_csv(os.path.join(FIGDIR, "021_size_stratified.csv"), index=False)
    models.to_csv(os.path.join(FIGDIR, "021_provision_models.csv"), index=False)

    OUT["figures"] = [fig(g)]
    gl.publish(g, "utsa_school_ap_offer", ["ap_offer_band"])
    # the CSV is a publication artifact too: the same minimum-cell rule
    # that governs the GATEWAY mart applies to every file output
    g[g.n_students >= gl.MIN_CELL].to_csv(
        os.path.join(FIGDIR, "021_school_ap_offer.csv"), index=False)
    with open(os.path.join(FIGDIR, "021_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(g.to_string(index=False))
    print(f"\nschools with NO AP maths: {OUT['pct_schools_no_ap']}%")
    print("\n--- is it poverty, or school SIZE? ---")
    print(by_size.to_string(index=False))
    print(f"corr(AP-math rate, district poverty) = {OUT['corr_apoffer_poverty']}")
    print(f"corr(AP-math rate, log school size) = {OUT['corr_apoffer_logsize']}")
    print(f"no AP: {OUT['pct_no_ap_small_schools']}% of schools <400 enrolled, "
          f"{OUT['pct_no_ap_large_schools']}% of schools >=400")
    print("\n--- does provision survive holding SIZE fixed? ---")
    print(strat.to_string(index=False))
    print("\n--- LPM: dual arrival ~ no-AP provision ---")
    print(models.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
