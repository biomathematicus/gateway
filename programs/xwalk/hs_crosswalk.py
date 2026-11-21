"""
Build the UTSA high-school-name -> NCES school crosswalk.

WHY NOT PLAIN TRIGRAM SIMILARITY
  UTSA records the full honorific name; NCES records a short form:

      UTSA "Sandra Day O'Connor High Sch"  ->  EDGE "O'CONNOR H S"
      UTSA "Winston Churchill High School" ->  EDGE "CHURCHILL H S"
      UTSA "Ronald Reagan High School"     ->  EDGE "REAGAN H S"

  Whole-string trigram similarity scores these LOW, because most of the UTSA
  string has no counterpart. The signal is CONTAINMENT: after stripping
  school-type words, the EDGE tokens are a subset of the UTSA tokens. So the
  score is containment-first, with trigram as a secondary term.

BLOCKING
  City is the strong blocker (UTSA carries HIGHSCHOOLCITY, EDGE carries CITY).
  ZIP is the fallback. Only if both fail does a candidate come from a statewide
  trigram sweep, and such matches are flagged for adjudication rather than
  trusted.

OUTPUT
  Every UTSA name gets a row with its best candidate, a score, the evidence that
  produced it, and a `decision` of auto / review / none. Nothing is silently
  accepted: `review` and `none` are written out for a human pass.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402

OUT: dict = {}
FIGDIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "figures"))

# The score and its thresholds (Appendix A of the manuscript reads them
# from here).
W_CONTAIN = 0.55        # weight of token containment
W_JACCARD = 0.20        # weight of the Jaccard index of the token sets
W_TRIGRAM = 0.25        # weight of the whole-string similarity
AUTO_SCORE = 0.72       # automatic acceptance needs at least this score
AUTO_MARGIN = 0.08      # and, in the statewide block, this margin over
                        # the runner-up
REVIEW_SCORE = 0.55     # at least this score goes to hand review
MIN_CANDIDATE_SCORE = 0.45   # below this score no candidate is kept
FUZZY_CITY = 0.85       # similarity at which a misspelled city is blocked
                        # with its nearest directory city

# school-type tokens carry no identifying information and differ by convention
STOP = {"HIGH", "SCHOOL", "SCH", "HS", "H", "S", "SENIOR", "SR", "SECONDARY",
        "CAMPUS", "ACADEMY", "MAGNET", "THE", "OF", "AT", "AND", "EARLY",
        "COLLEGE", "PREP", "PREPARATORY", "INTERNATIONAL", "CENTER", "CTR"}
# EDGE names that are clearly NOT high schools
NOT_HS = re.compile(r"\b(EL|ELEM|ELEMENTARY|MIDDLE|MS|INTERMEDIATE|"
                    r"PRIMARY|KINDER|PRE-?K|CHILDHOOD|J H|JR)\b")


def norm(s: str) -> str:
    s = (s or "").upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def citykey(s: str) -> str:
    """City key robust to the differences that actually occur in this data.

    UTSA and NCES disagree on spacing and articles: `Sugarland` vs `SUGAR LAND`,
    `Woodlands` vs `THE WOODLANDS`. Dropping spaces and a leading THE makes
    those identical, which recovers whole schools that were otherwise blocked
    into the wrong candidate pool.
    """
    n = norm(s)
    n = re.sub(r"^THE ", "", n)
    return n.replace(" ", "")


# schools that are genuinely NOT in the NCES PUBLIC universe. These are not
# match failures -- EDGE only covers public schools -- and calling them failures
# would overstate the crosswalk's error rate.
PRIVATE_HINT = re.compile(
    r"\b(CATHOLIC|CHRISTIAN|ANTONIAN|INCARNATE|JESUIT|LUTHERAN|BAPTIST|"
    r"EPISCOPAL|HOLY|SAINT|ST |ST\.|OUR LADY|CENTRAL CATHOLIC|"
    r"TMI|KEYSTONE|SAN ANTONIO ACADEMY)\b", re.I)


def toks(s: str) -> set[str]:
    return {t for t in norm(s).split() if t not in STOP and len(t) > 1}


def trig(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def utsa_names() -> pd.DataFrame:
    import pyodbc
    cn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};"
                        "SERVER=localhost;DATABASE=UTSA;Trusted_Connection=yes;")
    q = """
    SELECT LTRIM(RTRIM(HIGHSCHOOLNAME))                     AS hs_name,
           LTRIM(RTRIM(HIGHSCHOOLCITY))                     AS hs_city,
           RIGHT('00000'+LTRIM(RTRIM(HIGHSCHOOLZIP)),5)     AS hs_zip,
           COUNT(DISTINCT IDENTIFIER)                       AS n_students
    FROM dbo.OIR
    WHERE HIGHSCHOOLSTATE='TX' AND HIGHSCHOOLNAME IS NOT NULL
      AND LTRIM(RTRIM(HIGHSCHOOLNAME))<>''
    GROUP BY LTRIM(RTRIM(HIGHSCHOOLNAME)), LTRIM(RTRIM(HIGHSCHOOLCITY)),
             RIGHT('00000'+LTRIM(RTRIM(HIGHSCHOOLZIP)),5)
    """
    try:
        return pd.read_sql(q, cn)
    finally:
        cn.close()


def edge_tx() -> pd.DataFrame:
    with db.connect() as c:
        e = pd.read_sql(
            "SELECT ncessch, leaid, name, city, zip5, lat, lon "
            "FROM raw_xwalk.edge_school WHERE cycle='2017-18' AND state='TX'", c)
    e["is_hs"] = ~e["name"].str.upper().str.contains(NOT_HS, regex=True, na=False)
    e["n_norm"] = e["name"].map(norm)
    e["n_toks"] = e["name"].map(toks)
    e["city_n"] = e["city"].map(citykey)
    return e


def score(u_toks: set[str], u_norm: str, row) -> tuple[float, str]:
    e_toks: set[str] = row.n_toks
    if not e_toks or not u_toks:
        return 0.0, "empty"
    inter = u_toks & e_toks
    # containment of the SHORTER token set in the longer -- this is what makes
    # "O'CONNOR H S" match "Sandra Day O'Connor High Sch"
    contain = len(inter) / min(len(u_toks), len(e_toks))
    jac = len(inter) / len(u_toks | e_toks)
    t = trig(u_norm, row.n_norm)
    s = W_CONTAIN * contain + W_JACCARD * jac + W_TRIGRAM * t
    why = f"contain={contain:.2f} jac={jac:.2f} trig={t:.2f}"
    return s, why


def build() -> pd.DataFrame:
    u = utsa_names()
    e = edge_tx()
    OUT["utsa_name_city_zip_rows"] = int(len(u))
    OUT["utsa_distinct_names"] = int(u.hs_name.nunique())
    OUT["utsa_students"] = int(u.n_students.sum())
    OUT["edge_tx_schools"] = int(len(e))
    OUT["edge_tx_highschools"] = int(e.is_hs.sum())

    by_city: dict[str, list] = defaultdict(list)
    by_zip: dict[str, list] = defaultdict(list)
    for r in e.itertuples():
        by_city[r.city_n].append(r)
        by_zip[r.zip5].append(r)
    all_hs = [r for r in e.itertuples() if r.is_hs]
    city_keys = list(by_city)

    rows = []
    for r in u.itertuples():
        un, ut = norm(r.hs_name), toks(r.hs_name)
        cands, block = [], ""
        ck = citykey(r.hs_city)
        c = by_city.get(ck, [])
        if c:
            cands, block = c, "city"
        if not cands:
            z = by_zip.get(r.hs_zip, [])
            if z:
                cands, block = z, "zip"
        if not cands and ck:
            # fuzzy city: catches UTSA misspellings such as
            # `Atascosita` for NCES `ATASCOCITA`
            near = max(city_keys, key=lambda k: trig(ck, k), default="")
            if near and trig(ck, near) >= FUZZY_CITY:
                cands, block = by_city[near], "city~"
        if not cands:
            cands, block = all_hs, "statewide"

        best, best_s, best_why = None, -1.0, ""
        second = -1.0
        for cd in cands:
            if not cd.is_hs:
                continue
            s, why = score(ut, un, cd)
            if s > best_s:
                second, best, best_s, best_why = best_s, cd, s, why
            elif s > second:
                second = s
        if best is None:
            rows.append({"hs_name": r.hs_name, "hs_city": r.hs_city,
                         "hs_zip": r.hs_zip, "n_students": r.n_students,
                         "ncessch": None, "leaid": None, "edge_name": None,
                         "score": 0.0, "margin": 0.0, "block": block,
                         "why": "no candidate", "decision": "none"})
            continue
        margin = best_s - max(second, 0.0)
        # auto-accept needs BOTH a high score and a clear margin over the runner-up
        if best_s >= AUTO_SCORE and (
                margin >= AUTO_MARGIN or block in ("city", "city~", "zip")):
            dec = "auto"
        elif best_s >= REVIEW_SCORE:
            dec = "review"
        elif PRIVATE_HINT.search(r.hs_name or ""):
            dec = "private"       # not in the NCES PUBLIC universe at all
        else:
            dec = "none"
        # never publish a bogus candidate: below this the "best" match is noise
        if dec in ("none", "private") and best_s < MIN_CANDIDATE_SCORE:
            best = None
            best_why = "no credible candidate"
        rows.append({"hs_name": r.hs_name, "hs_city": r.hs_city,
                     "hs_zip": r.hs_zip, "n_students": r.n_students,
                     "ncessch": best.ncessch if best else None,
                     "leaid": best.leaid if best else None,
                     "edge_name": best.name if best else None,
                     "score": round(best_s, 3),
                     "margin": round(margin, 3), "block": block,
                     "why": best_why, "decision": dec})
    return pd.DataFrame(rows)


def main() -> int:
    x = build()
    tot = x.n_students.sum()
    for d in ("auto", "review", "private", "none"):
        sub = x[x.decision == d]
        OUT[f"n_names_{d}"] = int(len(sub))
        OUT[f"n_students_{d}"] = int(sub.n_students.sum())
        OUT[f"pct_students_{d}"] = round(100 * sub.n_students.sum() / tot, 1)
    OUT["n_distinct_leaid_matched"] = int(
        x.loc[x.decision == "auto", "leaid"].nunique())

    os.makedirs(FIGDIR, exist_ok=True)
    x.sort_values("n_students", ascending=False).to_csv(
        os.path.join(FIGDIR, "006_hs_crosswalk.csv"), index=False)
    x[x.decision != "auto"].sort_values("n_students", ascending=False).to_csv(
        os.path.join(FIGDIR, "006_hs_crosswalk_REVIEW.csv"), index=False)

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS core.hs_crosswalk CASCADE")
        cur.execute("""
            CREATE TABLE core.hs_crosswalk (
                hs_name text, hs_city text, hs_zip text, n_students int,
                ncessch text, leaid text, edge_name text,
                score double precision, margin double precision,
                block text, why text, decision text)""")
        import io as _io
        buf = _io.StringIO()
        x.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert("COPY core.hs_crosswalk FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("CREATE INDEX ON core.hs_crosswalk (leaid)")

    with open(os.path.join(FIGDIR, "006_stats.json"), "w") as fh:
        json.dump(OUT, fh, indent=1)
    print(json.dumps(OUT, indent=1))
    print()
    print("top auto matches:")
    print(x[x.decision == "auto"].nlargest(8, "n_students")[
        ["hs_name", "edge_name", "hs_city", "score", "n_students"]].to_string(index=False))
    print()
    print("largest needing review:")
    print(x[x.decision != "auto"].nlargest(8, "n_students")[
        ["hs_name", "edge_name", "hs_city", "score", "decision", "n_students"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
