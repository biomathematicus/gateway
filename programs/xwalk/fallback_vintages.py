"""
Recover unmatched high schools using EARLIER vintages.

The crosswalk (report 006) matched against EDGE 2017-18. UTSA students entered
from Fall 2009, so a school that CLOSED or was RENAMED before 2017-18 cannot be
in that directory at all — which is the systematic part of the residual 6.2%.

NCES publishes no EDGE geocode file for 2011-12 or 2013-14 (both 404). But the
CRDC extracts themselves carry `SCH_NAME` alongside `LEAID`/`COMBOKEY` for every
cycle, so the five CRDC archives ARE a school-name directory reaching back to
2011-12 — no new download required.

TRADE-OFF, and it is why this pass is deliberately conservative:
  EDGE carries city, ZIP and coordinates; the CRDC school files carry only
  state. So candidates here can be blocked on STATE ONLY, a far weaker block
  than city. A weak block with a permissive threshold produces confident
  nonsense (report 006 §3c). This pass therefore requires a HIGH score AND a
  clear margin, and everything it accepts is marked `auto_vint` so it can be
  excluded independently of `auto` and `auto_adj`.
"""

from __future__ import annotations

import glob
import io
import json
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402
from gateway import paths  # noqa: E402
import re  # noqa: E402
from xwalk.hs_crosswalk import NOT_HS, norm, score, toks, trig  # noqa: E402

# The first run of this pass accepted, at score>=0.80 with state-only blocking:
#   Dunbar High School      -> DUNBAR 6TH GR SCH            (a 6th grade school)
#   North Lamar High School -> NORTH LAMAR ISD              (the DISTRICT)
#   North Crowley H S       -> NORTH CROWLEY H S 9TH GRADE CAMPUS
#   Fort Davis H S          -> FORT DAVIS AEC               (alt-ed centre)
# i.e. roughly half of a 140-student gain was wrong. `NOT_HS` did not catch
# these shapes. A wrong LEAID is worse than a null, so the bar is raised and the
# exclusion list extended. This is a deliberately tiny, clean recovery.
FIRST_RUN_SCORE = 0.80   # threshold of the revoked first run described above
RECOVERY_SCORE = 0.90    # threshold of the standing run
RECOVERY_MARGIN = 0.15   # margin over the runner-up in the standing run

NOT_HS_EXTRA = re.compile(
    r"(ISD|CISD|DISTRICT|AEC|DAEP|ALTER|ALTERNATIVE|\d+(ST|ND|RD|TH)\s*GR|"
    r"GRADE\s*CAMPUS|GR\s*SCH|9TH|6TH|7TH|8TH|JJAEP|BOOT|DETENTION)", re.I)

DATA = paths.data_dir("CRDC")
FIGDIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "figures"))

# one file per cycle that carries SCH_NAME + LEAID + COMBOKEY
SRC = {
    "2011-12": "2011-12-crdc-data/**/*13-4 - Students enrolled in Algebra II.xlsx",
    "2013-14": "2013-14-crdc-data/**/05-3 Other Math Courses and Classes.xlsx",
    "2015-16": "2015-16-crdc-data/**/CRDC 2015-16 School Data.csv",
}
KEEP = ["LEA_STATE", "LEAID", "SCHID", "SCH_NAME"]


def crdc_directory() -> pd.DataFrame:
    frames = []
    for cycle, pat in SRC.items():
        hits = [h for h in glob.glob(os.path.join(DATA, pat), recursive=True)
                if "~$" not in h]
        if not hits:
            print(f"  ! {cycle}: no source", flush=True)
            continue
        p = hits[0]
        if p.lower().endswith(".csv"):
            d = pd.read_csv(p, dtype=str, encoding="latin-1", low_memory=False,
                            usecols=lambda c: c in KEEP)
        else:
            d = pd.read_excel(p, dtype=str)
            d = d[[c for c in d.columns if c in KEEP]]
        d = d[d.get("LEA_STATE", "") == "TX"]
        leaid = d["LEAID"].astype(str).str.strip().str.zfill(7)
        schid = d["SCHID"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        frames.append(pd.DataFrame({
            "cycle": cycle, "leaid": leaid,
            "ncessch": leaid + schid.str.zfill(5),
            "name": d["SCH_NAME"].astype(str).str.strip()}))
        print(f"  {cycle}: {len(frames[-1]):,} TX schools", flush=True)
    dd = pd.concat(frames, ignore_index=True)
    dd = dd[dd.leaid.str.fullmatch(r"\d{7}", na=False)]
    # keep the EARLIEST cycle a school appears in -- that is the vintage that
    # recovers a school which later closed
    dd = dd.sort_values("cycle").drop_duplicates(subset=["ncessch"], keep="first")
    up = dd["name"].str.upper()
    dd["is_hs"] = (~up.str.contains(NOT_HS, regex=True, na=False)
                   & ~up.str.contains(NOT_HS_EXTRA, regex=True, na=False))
    dd["n_norm"] = dd["name"].map(norm)
    dd["n_toks"] = dd["name"].map(toks)
    return dd


def main() -> int:
    with db.connect() as c:
        x = pd.read_sql("SELECT * FROM core.hs_crosswalk", c)
        seen = pd.read_sql(
            "SELECT DISTINCT ncessch FROM raw_xwalk.edge_school "
            "WHERE cycle='2017-18' AND state='TX'", c)
    # retry both unresolved rows AND anything a previous run of this pass
    # promoted, so tightening the rule can REVOKE an earlier bad match
    x.loc[x.decision == "auto_vint", ["ncessch", "leaid", "edge_name"]] = None
    x.loc[x.decision == "auto_vint", "decision"] = "none"
    todo = x[x.decision == "none"].copy()
    print(f"unresolved to retry: {len(todo)} names, "
          f"{int(todo.n_students.sum()):,} students", flush=True)

    print("building CRDC school-name directory (TX) ...", flush=True)
    dirn = crdc_directory()
    # only schools ABSENT from EDGE 2017-18 can explain a 2017-18 miss
    old = dirn[~dirn.ncessch.isin(set(seen.ncessch))]
    old_hs = [r for r in old.itertuples() if r.is_hs]
    print(f"  directory {len(dirn):,} TX schools; "
          f"{len(old):,} absent from EDGE 2017-18 ({len(old_hs):,} look like HS)",
          flush=True)

    rows, acc = [], 0
    for r in todo.itertuples():
        un, ut = norm(r.hs_name), toks(r.hs_name)
        best, best_s, second, why = None, -1.0, -1.0, ""
        for cd in old_hs:
            s, w = score(ut, un, cd)
            if s > best_s:
                second, best, best_s, why = best_s, cd, s, w
            elif s > second:
                second = s
        margin = best_s - max(second, 0.0)
        # STRICT: state-only blocking means a permissive threshold would
        # manufacture matches. Require a high score AND a clear margin.
        ok = (best is not None and best_s >= RECOVERY_SCORE
              and margin >= RECOVERY_MARGIN)
        rows.append({"hs_name": r.hs_name, "hs_city": r.hs_city,
                     "n_students": r.n_students,
                     "cand": best.name if best else None,
                     "cand_ncessch": best.ncessch if best else None,
                     "cand_leaid": best.leaid if best else None,
                     "cand_cycle": best.cycle if best else None,
                     "score": round(best_s, 3), "margin": round(margin, 3),
                     "accept": ok})
        if ok:
            acc += 1
    res = pd.DataFrame(rows).sort_values("n_students", ascending=False)

    for i, r in x.iterrows():
        if r.decision != "none":
            continue
        m = res[res.hs_name == r.hs_name]
        if len(m) and bool(m.accept.iloc[0]):
            x.at[i, "decision"] = "auto_vint"
            x.at[i, "ncessch"] = m.cand_ncessch.iloc[0]
            x.at[i, "leaid"] = m.cand_leaid.iloc[0]
            x.at[i, "edge_name"] = m.cand.iloc[0]
            x.at[i, "why"] = (f"VINTAGE RECOVERY from CRDC {m.cand_cycle.iloc[0]} "
                              f"(absent from EDGE 2017-18); score "
                              f"{m.score.iloc[0]} margin {m.margin.iloc[0]}")

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
    for d in ("auto", "auto_adj", "auto_vint", "private", "rejected", "none"):
        sub = x[x.decision == d]
        out[f"n_names_{d}"] = int(len(sub))
        out[f"n_students_{d}"] = int(sub.n_students.sum())
    usable = x[x.decision.isin(["auto", "auto_adj", "auto_vint"])]
    out["pct_students_usable"] = round(100 * usable.n_students.sum() / tot, 1)
    out["n_distinct_leaid"] = int(usable.leaid.nunique())

    res.to_csv(os.path.join(FIGDIR, "009_vintage_recovery.csv"), index=False)
    x.sort_values("n_students", ascending=False).to_csv(
        os.path.join(FIGDIR, "006_hs_crosswalk.csv"), index=False)
    with open(os.path.join(FIGDIR, "009_stats.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))
    print()
    print("top recoveries:")
    print(res[res.accept].head(10)[
        ["hs_name", "cand", "cand_cycle", "score", "n_students"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
