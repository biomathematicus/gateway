"""
Recover the remaining unresolved high schools using the CCD school universe.

Report 006 §7 established what the previous attempt lacked. The CRDC extracts
carry only STATE, so candidates could be blocked on state alone; at a threshold
of 0.80 that "recovered" a 6th-grade school, a DISTRICT and an alternative-
education centre as high schools, and the pass had to be tightened to 0.90,
yielding almost nothing. The diagnosis then was: this needs a directory that
carries CITY.

The CCD School Universe does, and more:

    NCESSCH  LEAID  SCHNAM  LCITY  LSTATE  LZIP  GSLO  GSHI  STATUS  TYPE

  * LCITY restores the strong block, so the ordinary crosswalk thresholds
    (score >= 0.72 with a margin) are safe again rather than reckless;
  * GSLO/GSHI give a REAL high-school test — highest grade in 9..12 — instead of
    the name-pattern heuristic that let `DUNBAR 6TH GR SCH` through;
  * it exists for years EDGE does not: 2010-11 and 2013-14 are downloadable
    where EDGE geocodes 404.

Vintages used: CCD 2013-14 and 2010-11 — both inside the UTSA attendance window
(students entered from Fall 2009) and both EARLIER than the EDGE 2017-18
directory the main crosswalk used, which is where schools that later closed
still exist.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402
from gateway import paths  # noqa: E402
from xwalk.hs_crosswalk import citykey, norm, score, toks  # noqa: E402

GEO = paths.data_dir("geo")
FIGDIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "figures"))

SRC = {"2013-14": "ccd_sc132a/sc132a.txt", "2010-11": "ccd_sc102a/sc102a.txt"}
KEEP = ["NCESSCH", "LEAID", "SCHNAM", "LCITY", "LSTATE", "LZIP", "GSLO", "GSHI"]
HS_GRADES = {"09", "10", "11", "12", "9"}


def ccd_directory() -> pd.DataFrame:
    frames = []
    for cycle, rel in SRC.items():
        p = os.path.join(GEO, rel)
        if not os.path.isfile(p):
            print(f"  ! {cycle}: missing {rel}", flush=True)
            continue
        rows = []
        with open(p, encoding="latin-1") as fh:
            rd = csv.DictReader(fh, delimiter="\t")
            for r in rd:
                if (r.get("LSTATE") or "").strip() != "TX":
                    continue
                rows.append({k: (r.get(k) or "").strip() for k in KEEP})
        d = pd.DataFrame(rows)
        d["cycle"] = cycle
        frames.append(d)
        print(f"  {cycle}: {len(d):,} TX schools", flush=True)
    dd = pd.concat(frames, ignore_index=True)
    dd["ncessch"] = dd["NCESSCH"].str.strip().str.zfill(12)
    dd["leaid"] = dd["ncessch"].str[:7]
    dd["name"] = dd["SCHNAM"]
    dd["city_n"] = dd["LCITY"].map(citykey)
    # a REAL high-school test: highest grade served is 9-12
    dd["is_hs"] = dd["GSHI"].str.zfill(2).isin({"09", "10", "11", "12"})
    dd = dd.sort_values("cycle").drop_duplicates(subset=["ncessch"], keep="first")
    dd["n_norm"] = dd["name"].map(norm)
    dd["n_toks"] = dd["name"].map(toks)
    return dd


def main() -> int:
    with db.connect() as c:
        x = pd.read_sql("SELECT * FROM core.hs_crosswalk", c)
        seen = pd.read_sql("SELECT DISTINCT ncessch FROM raw_xwalk.edge_school "
                           "WHERE cycle='2017-18' AND state='TX'", c)
    # retry unresolved AND revisit anything a prior CCD pass promoted
    x.loc[x.decision == "auto_ccd", ["ncessch", "leaid", "edge_name"]] = None
    x.loc[x.decision == "auto_ccd", "decision"] = "none"
    todo = x[x.decision == "none"].copy()
    print(f"unresolved to retry: {len(todo)} names, "
          f"{int(todo.n_students.sum()):,} students", flush=True)

    print("building CCD TX directory ...", flush=True)
    d = ccd_directory()
    print(f"  {len(d):,} TX schools; {int(d.is_hs.sum()):,} are high schools "
          f"by grade span (GSHI in 09-12)", flush=True)

    by_city: dict[str, list] = defaultdict(list)
    for r in d.itertuples():
        if r.is_hs:
            by_city[r.city_n].append(r)
    all_hs = [r for r in d.itertuples() if r.is_hs]

    rows, acc = [], 0
    for r in todo.itertuples():
        un, ut = norm(r.hs_name), toks(r.hs_name)
        ck = citykey(r.hs_city)
        cands = by_city.get(ck, [])
        block = "city" if cands else "statewide"
        if not cands:
            cands = all_hs
        best, best_s, second, why = None, -1.0, -1.0, ""
        for cd in cands:
            s, w = score(ut, un, cd)
            if s > best_s:
                second, best, best_s, why = best_s, cd, s, w
            elif s > second:
                second = s
        margin = best_s - max(second, 0.0)
        # city block restores the ordinary thresholds; statewide stays strict
        ok = best is not None and (
            (block == "city" and best_s >= 0.72 and margin >= 0.05)
            or (block == "statewide" and best_s >= 0.90 and margin >= 0.15))
        rows.append({"hs_name": r.hs_name, "hs_city": r.hs_city,
                     "n_students": r.n_students,
                     "cand": best.name if best else None,
                     "cand_ncessch": best.ncessch if best else None,
                     "cand_leaid": best.leaid if best else None,
                     "cand_cycle": best.cycle if best else None,
                     "cand_city": best.LCITY if best else None,
                     "in_edge_1718": (best.ncessch in set(seen.ncessch)) if best else None,
                     "block": block, "score": round(best_s, 3),
                     "margin": round(margin, 3), "accept": ok})
        if ok:
            acc += 1
    res = pd.DataFrame(rows).sort_values("n_students", ascending=False)

    for i, r in x.iterrows():
        if r.decision != "none":
            continue
        m = res[res.hs_name == r.hs_name]
        if len(m) and bool(m.accept.iloc[0]):
            x.at[i, "decision"] = "auto_ccd"
            x.at[i, "ncessch"] = m.cand_ncessch.iloc[0]
            x.at[i, "leaid"] = m.cand_leaid.iloc[0]
            x.at[i, "edge_name"] = m.cand.iloc[0]
            x.at[i, "why"] = (f"CCD {m.cand_cycle.iloc[0]} recovery, "
                              f"block={m.block.iloc[0]}, score {m.score.iloc[0]}, "
                              f"margin {m.margin.iloc[0]}")

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
    out = {"retried_names": int(len(todo)),
           "retried_students": int(todo.n_students.sum()),
           "recovered_names": int(acc)}
    for dec in ("auto", "auto_adj", "auto_vint", "auto_ccd",
                "private", "rejected", "none"):
        sub = x[x.decision == dec]
        out[f"n_names_{dec}"] = int(len(sub))
        out[f"n_students_{dec}"] = int(sub.n_students.sum())
    usable = x[x.decision.str.startswith("auto")]
    out["pct_students_usable"] = round(100 * usable.n_students.sum() / tot, 1)
    out["n_distinct_leaid"] = int(usable.leaid.nunique())

    res.to_csv(os.path.join(FIGDIR, "011_ccd_recovery.csv"), index=False)
    x.sort_values("n_students", ascending=False).to_csv(
        os.path.join(FIGDIR, "006_hs_crosswalk.csv"), index=False)
    with open(os.path.join(FIGDIR, "011_stats.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))
    print()
    print("top recoveries:")
    print(res[res.accept].head(12)[
        ["hs_name", "cand", "cand_city", "cand_cycle", "score", "n_students"]
    ].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
