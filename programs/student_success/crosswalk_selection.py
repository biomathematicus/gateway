"""
Report 025 — Do the unmatched students bias reports 013-024?

Every district- or school-linked finding in this programme (013, 015, 018, 021)
runs on the ~90% of students whose high school matched `core.hs_crosswalk`. The
standing queue item was to recover more of the remainder with the CCD directory.

THAT ITEM IS ALREADY DONE -- it IS report 011, and `xwalk/ccd_recovery.py` is the
script. What is left is a RESIDUAL of 221 names / 4,189 students that no method
resolved, and inspecting them shows why: heavy abbreviation
("South Tx HS for Hlth Prof"), misspelling ("Atascosita", "Sugarland"), a school
named for one town but located in another ("Gregory-Portland High School" in
Gregory), and combined junior/senior campuses. Recovering those needs LOOSER
matching, and report 006 section 7 already proved where that leads: at score
>= 0.80 with state-only blocking it "recovered" a 6th-grade school, a DISTRICT,
and an alternative-education centre as high schools.

So the useful question is not "can we match more" but "does it matter that we
cannot". This report answers that instead, using only observables we already
hold and performing no new matching.

THE TEST. Compare matched against unmatched students on characteristics that
appear in the findings -- SAT/ACT mathematics, Pell, first-generation status,
and the AP/dual split that reports 013-020 are built on. If the groups look
alike, the ~10% loss is close to random and the findings generalise. If they
differ, every district-linked result inherits that selection and must say so.

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
from courses import canon
from instrument_outcome import COURSE_SQL, CREDIT_SQL, DFW

sys.path.insert(0, os.path.dirname(config.PKG_DIR))
from analysis.style import FIGDIR, INK2, MUTED, SERIES, finish, setup  # noqa: E402
from gateway import db as gdb  # noqa: E402

setup()
OUT: dict = {}

#: how `decision` maps onto the groups that matter analytically
GROUP = {"auto": "matched", "auto_adj": "matched", "auto_ccd": "matched",
         "auto_vint": "matched", "private": "private (outside NCES)",
         "none": "unresolved", "rejected": "rejected"}


def frame() -> pd.DataFrame:
    s = gl.students()
    cr = db.cached_query("gateway-credit-type-sat", CREDIT_SQL)
    for k in ("ap", "dual"):
        cr[k] = pd.to_numeric(cr[k], errors="coerce").fillna(0).astype(int)

    c = db.cached_query("mat-course-attempts", COURSE_SQL)
    c["course"] = c.title.map(canon)
    c["term_n"] = pd.to_numeric(c.term, errors="coerce")
    first = (c.sort_values(["IDENTIFIER", "term_n"])
               .drop_duplicates("IDENTIFIER", keep="first"))
    first = first.assign(first_dfw=first.grade.astype(str).str.strip()
                         .str.upper().isin(DFW).astype(int))[
        ["IDENTIFIER", "first_dfw"]]

    with gdb.connect() as g:
        xw = pd.read_sql("SELECT hs_name, hs_city, decision FROM core.hs_crosswalk", g)

    d = (s.merge(cr[["IDENTIFIER", "ap", "dual"]], on="IDENTIFIER", how="left")
          .merge(first, on="IDENTIFIER", how="left")
          .merge(xw, on=["hs_name", "hs_city"], how="left"))
    d["group"] = d.decision.map(GROUP).fillna("no HS recorded")
    for k in ("ap", "dual"):
        d[k] = pd.to_numeric(d[k], errors="coerce").fillna(0).astype(int)
    d["satact_math"] = pd.to_numeric(d.satact_math, errors="coerce")
    # these are LABELS, not flags -- `pd.to_numeric` silently NaNs the lot
    d["pell"] = d.pell.eq("Pell Paid").astype(float)
    d["first_gen"] = np.where(
        d.first_gen.isin(["First Generation", "Not First Generation"]),
        d.first_gen.eq("First Generation").astype(float), np.nan)
    d["is_transfer"] = d.student_type.eq("Transfer").astype(float)
    return d


def cells(d: pd.DataFrame) -> pd.DataFrame:
    g = (d.groupby("group", observed=True)
           .agg(n_students=("ap", "size"),
                pct_ap=("ap", lambda x: 100 * x.mean()),
                pct_dual=("dual", lambda x: 100 * x.mean()),
                mean_satact_math=("satact_math", "mean"),
                pct_pell=("pell", lambda x: 100 * np.nanmean(x)),
                pct_first_gen=("first_gen", lambda x: 100 * np.nanmean(x)),
                pct_first_dfw=("first_dfw", lambda x: 100 * np.nanmean(x)),
                pct_transfer=("is_transfer", lambda x: 100 * np.nanmean(x)))
           .reset_index().round(3))
    return g.sort_values("n_students", ascending=False)


def gap_test(d: pd.DataFrame, col: str) -> dict:
    """Matched vs unresolved, two-sample, unequal variance."""
    a = d.loc[d.group == "matched", col].astype(float).dropna()
    b = d.loc[d.group == "unresolved", col].astype(float).dropna()
    if len(a) < 30 or len(b) < 30:
        return {}
    se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
    diff = float(b.mean() - a.mean())
    return {"measure": col, "matched": round(float(a.mean()), 3),
            "unresolved": round(float(b.mean()), 3),
            "diff": round(diff, 3), "se": round(se, 3),
            "z": round(diff / se, 2) if se else None,
            "n_matched": int(len(a)), "n_unresolved": int(len(b))}


def fig(g: pd.DataFrame, tests: pd.DataFrame) -> str:
    keep = ["matched", "unresolved", "private (outside NCES)"]
    m = g[g.group.isin(keep)].set_index("group").reindex(keep).dropna(how="all")
    measures = [("pct_ap", "AP credit %"), ("pct_dual", "Dual credit %"),
                ("pct_pell", "Pell %"), ("pct_first_dfw", "DFW, first course %")]
    x = np.arange(len(measures))
    w = 0.26
    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    for j, grp in enumerate(m.index):
        vals = [float(m.loc[grp, c]) for c, _ in measures]
        pos = x + (j - 1) * w
        ax.bar(pos, vals, w * 0.9, color=SERIES[j], label=grp, zorder=3)
        for p, v in zip(pos, vals):
            ax.text(p, v + 0.8, f"{v:.0f}", ha="center", fontsize=8.5,
                    color=SERIES[j], fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([lab for _, lab in measures], fontsize=9)
    ax.set_ylabel("%")
    ax.legend(loc="upper left", fontsize=9)
    return finish(fig, ax, "025_crosswalk_selection",
                  "Unresolved students are not a random sample of the rest",
                  "Students whose high school could not be matched to an NCES "
                  "identifier, against those that could. Every district- and "
                  "school-linked finding in reports 013-024 runs on the matched "
                  "group only. SAT/ACT mathematics is compared in the report "
                  "text rather than here, being on a different scale.")


def main() -> int:
    d = frame()
    OUT["n_students"] = int(len(d))
    g = cells(d)
    OUT["cells"] = g.to_dict("records")

    matched = int(g.loc[g.group == "matched", "n_students"].sum())
    OUT["pct_matched"] = round(100 * matched / len(d), 1)

    tests = pd.DataFrame([t for t in
                          (gap_test(d, c) for c in
                           ["satact_math", "ap", "dual", "pell", "first_gen",
                            "first_dfw", "is_transfer"]) if t])
    OUT["tests"] = tests.to_dict("records")

    OUT["figures"] = [fig(g, tests)]
    gl.publish(g, "utsa_crosswalk_selection", ["group"])
    g.to_csv(os.path.join(FIGDIR, "025_groups.csv"), index=False)
    tests.to_csv(os.path.join(FIGDIR, "025_tests.csv"), index=False)
    with open(os.path.join(FIGDIR, "025_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(g.to_string(index=False))
    print("\n--- matched vs unresolved ---")
    print(tests.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
