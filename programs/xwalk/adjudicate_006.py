"""
Adjudicate the 39 `review` rows from the high-school crosswalk (report 006).

Each decision is recorded WITH ITS REASON and written to a new decision value
`auto_adj` (accepted on review) or `rejected` (candidate refused). Nothing is
silently promoted to `auto`: a downstream query can always exclude
machine-adjudicated matches by filtering `decision = 'auto'` alone.

The rejections fall into four recurring kinds, and naming them is more useful
than the individual calls:

  PRIVATE      the UTSA school is private and simply is not in the NCES public
               universe; the "candidate" is an unrelated public school that
               happens to share a city and a word.
  WRONG-LEVEL  the candidate is an intermediate/middle campus, not the high
               school (e.g. `LITTLE CYPRESS INT`).
  WRONG-NETWORK  both are charters in the same city but different operators
               (KIPP vs Jubilee, Star vs NYOS).
  WRONG-CAMPUS the candidate is the district's main campus while the UTSA name
               specifies a separate one (`South San HS-West`).

A rejected row keeps `ncessch = NULL`. A wrong LEAID is worse than a null.
"""

from __future__ import annotations

import io
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402

FIGDIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "figures"))

# hs_name -> (verdict, reason).  verdict: True = accept, False = reject
CALLS: dict[str, tuple[bool, str]] = {
    # --- accepted: abbreviation / truncation of the same school -------------
    "Legacy of Edu Excel (Lee) HS": (True, "LEE H S was renamed Legacy of Educational Excellence"),
    "Academy of Creative Education": (True, "truncation: ACADEMY OF CREATIVE ED"),
    "Carver High School": (True, "Houston Carver H S for Applied Tech/Engineering/Arts"),
    "School of Sci & Technology": (True, "ampersand expansion"),
    "Westchester Acad-Intl Studies": (True, "abbreviation expansion"),
    "Grulla High School": (True, "district prefix on the NCES side"),
    "Robert Turner Col & Car HS": (True, "abbreviation expansion"),
    "Thelma Salinas Early Clg HS": (True, "middle name + STEM on the NCES side"),
    "School of Business & Mgmt": (True, "ampersand + abbreviation expansion"),
    "Shirleen Zacharias Early Coll": (True, "truncation of the same academy"),
    "KJ Gilliam Collegiate Academy": (True, "initials expanded to Kathlyn Joy"),
    "SA School For Inquiry": (True, "SA = San Antonio"),
    "Colorado River Coll Academy": (True, "Coll = Collegiate"),
    "New Direction Learning Center": (True, "LRN CTR abbreviation"),
    "Young Womens Leadership Acad": (True, "apostrophe + abbreviation"),
    "YES Prep Public -Fifth Ward": (True, "Fifth Ward = 5TH WARD"),
    "Richard Milburn Charter School": (True, "same operator, Killeen campus"),
    "City View Jr Sr High School": (True, "Jr Sr = JUNIOR/SENIOR"),
    "Winfree Acad Charter School": (True, "exact, Richardson campus"),
    "Premier High School-Ft Worth": (True, "Ft Worth = FORT WORTH"),
    "Imagine Int'l Academy Texas": (True, "Imagine International Academy of North Texas"),
    "Premier HS of Plugerville": (True, "UTSA misspelling of Pflugerville"),
    "Evolution Academy Chrtr Sch": (True, "abbreviation expansion"),
    "Eastside Memorial Green Tech": (True, "Eastside Memorial Green Tech at the Johnston campus"),
    "STEM Early College High School": (True, "Harlandale ISD STEM ECHS, the only SA STEM ECHS"),
    "San Antonio Positive Solutions": (True, "same charter, city prefix on the UTSA side"),

    # --- rejected ----------------------------------------------------------
    "San Antonio Christian School": (False, "PRIVATE - candidate SAN ANTONIO CAN ACADEMY is an unrelated charter"),
    "Christian Acad of San Antonio": (False, "PRIVATE - candidate is Harmony Science Academy, unrelated"),
    "Hill School Of Fort Worth": (False, "PRIVATE - candidate is Harmony School of Innovation, unrelated"),
    "Westwood School": (False, "PRIVATE Montessori - candidate is a DISD magnet, and a middle campus"),
    "KIPP Univ PREP HS-San Antonio": (False, "WRONG-NETWORK - KIPP is not Jubilee"),
    "Star Charter School": (False, "WRONG-NETWORK - Star is not NYOS"),
    "San Antonio Techology Academy": (False, "WRONG-NETWORK - not SAN ANTONIO CAN ACADEMY"),
    "Little Cypress-Mauriceville HS": (False, "WRONG-LEVEL - candidate LITTLE CYPRESS INT is intermediate"),
    "Higgs Carter King": (False, "WRONG-SCHOOL - Higgs Carter King G&T Charter is not M L King Academy"),
    "South San HS-West": (False, "WRONG-CAMPUS - UTSA names the West campus; candidate is the main H S"),
    "Memorial High School": (False, "UNRESOLVED - candidate is a San Antonio ECHS; UTSA city is New Braunfels"),
    "American Youthworks Charter": (False, "UNRESOLVED - Premier H S American Youthworks is a different operator"),
    "Energized for STEM Acad - West": (False, "AMBIGUOUS - margin 0.007 between West and Southwest campuses"),
}


def main() -> int:
    with db.connect() as c:
        x = pd.read_sql("SELECT * FROM core.hs_crosswalk", c)

    rev = x[x.decision == "review"].copy()
    unseen = sorted(set(rev.hs_name) - set(CALLS))
    if unseen:
        print(f"!! {len(unseen)} review rows have no call and stay 'review': {unseen}")

    acc = rej = 0
    for i, r in x.iterrows():
        if r.decision != "review":
            continue
        call = CALLS.get(r.hs_name)
        if call is None:
            continue
        ok, why = call
        if ok:
            x.at[i, "decision"] = "auto_adj"
            x.at[i, "why"] = f"{r.why} | ADJUDICATED ACCEPT: {why}"
            acc += 1
        else:
            x.at[i, "decision"] = "rejected"
            x.at[i, "ncessch"] = None
            x.at[i, "leaid"] = None
            x.at[i, "edge_name"] = None
            x.at[i, "why"] = f"ADJUDICATED REJECT: {why}"
            rej += 1

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS core.hs_crosswalk CASCADE")
        cur.execute("""
            CREATE TABLE core.hs_crosswalk (
                hs_name text, hs_city text, hs_zip text, n_students int,
                ncessch text, leaid text, edge_name text,
                score double precision, margin double precision,
                block text, why text, decision text)""")
        buf = io.StringIO()
        x.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert("COPY core.hs_crosswalk FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("CREATE INDEX ON core.hs_crosswalk (leaid)")

    tot = x.n_students.sum()
    out = {"accepted_on_review": acc, "rejected_on_review": rej}
    for d in ("auto", "auto_adj", "review", "private", "rejected", "none"):
        sub = x[x.decision == d]
        out[f"n_names_{d}"] = int(len(sub))
        out[f"n_students_{d}"] = int(sub.n_students.sum())
        out[f"pct_students_{d}"] = round(100 * sub.n_students.sum() / tot, 1)
    usable = x[x.decision.isin(["auto", "auto_adj"])]
    out["pct_students_usable"] = round(100 * usable.n_students.sum() / tot, 1)
    out["n_distinct_leaid"] = int(usable.leaid.nunique())

    x.sort_values("n_students", ascending=False).to_csv(
        os.path.join(FIGDIR, "006_hs_crosswalk.csv"), index=False)
    x[~x.decision.isin(["auto", "auto_adj"])].sort_values(
        "n_students", ascending=False).to_csv(
        os.path.join(FIGDIR, "006_hs_crosswalk_UNMATCHED.csv"), index=False)
    with open(os.path.join(FIGDIR, "006_adjudication.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
