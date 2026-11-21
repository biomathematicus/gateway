"""Linkage of students to sending schools and districts: coverage of the
school crosswalk, disposition of the students, selection audits, and the
sending profiles, for the students active between Fall 2014 and Fall 2019.

Population. A student is active in the window when the course-record table
(OIR) holds at least one course record of theirs in a term from
`config.S_START` (Fall 2014) to `config.S_END` (Fall 2019). Every quantity
is computed twice: for the whole extract (`extract`, which reproduces the
earlier numbered analyses 005, 006, 008, 009, 011, 021, and 025 and serves
as the check of this program) and for the students active in the window
(`window`, which the manuscript reports).

Counting. Each student counts once. The earlier analyses joined students to
the crosswalk on name and city, and four name and city pairs hold several
ZIP rows, so their totals held 270 students twice; `legacy_check` rebuilds
those totals to show that this program reads the same records.

Data handling. Student rows are read into memory, reduced to aggregates,
and discarded when the program ends. Nothing is cached and nothing is
written to a database. Every exported count rests on at least `MIN_CELL`
students; smaller cells are pooled or withheld, and the stats file says
how many. Analysis uses SQL, lists, and numpy arrays.

Outputs (figures/student_success):
    linkage_profile_stats.json     every quantity for the active students,
                                   and the totals of the extract
    linkage_profile_check.json     local check file: the same profile for
                                   the whole extract and the earlier
                                   totals rebuilt (not released)
    linkage_profile_provision.csv  window: credit arrival by provision band
    linkage_profile_poverty.csv    window: histogram of sending poverty
    linkage_profile_districts.csv  window: ten largest sending districts

Run:  python student_success/linkage_profile.py
"""
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyodbc

PKG = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG.parent))
import config  # noqa: E402
from gateway import db as gdb  # noqa: E402

FIG = PKG.parent / "figures" / "student_success"
ROOT_FIG = PKG.parent / "figures"

MIN_CELL = 10
#: usable crosswalk decisions in the order the stages were added
USABLE = ("auto", "auto_adj", "auto_vint", "auto_ccd")
#: order in which a student with several recorded names is classified
PRIORITY = USABLE + ("private", "rejected", "none")
#: unsuccessful outcome in the first mathematics course (analysis 025)
FIRST_COURSE_DFW = ("D", "D+", "D-", "F", "W", "IN", "NC", "NR")
#: provision bands: share of the school's students in AP mathematics (%)
BAND_EDGES = (2.0, 5.0)
BANDS = ("0. offers no AP maths", "1. under 2%", "2. 2-5%", "3. over 5%")
#: SAIPE vintages averaged for the sending-district poverty rate
POVERTY_VINTAGES = (2010, 2018)
POVERTY_BIN = 2.5            # width of the histogram bins, percentage points
POVERTY_MAX = 60.0
TOP_DISTRICTS = 10
#: distance diagnostics (miles)
PRIMARY_MILES = 10.0
STRICT_MILES = 5.0
FAR_MILES = 100.0
ZERO_MILES = 0.25            # "zero-mile spike" of analysis 008
# a school ZIP recorded with its leading zero dropped and padded on the
# wrong side: a Houston home (770xx) with a school that reads as New
# Jersey (077xx)
MISREAD_HOME_PREFIX, MISREAD_SCHOOL_PREFIX = "770", "077"
EARTH_MILES = 3958.7613
EDGE_CYCLE = "2017-18"       # directory of the crosswalk and school points
SCHOOL_TABLE_CYCLE = "2017-18"


# --------------------------------------------------------------------------
# small statistics on lists and arrays
# --------------------------------------------------------------------------
def _float(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _text(x):
    return None if x is None else str(x).strip()


def pct(num, den):
    return 100.0 * num / den if den else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def welch(a, b):
    """difference of means b - a with its unequal-variance z statistic"""
    a = np.array([x for x in a if x is not None], dtype=float)
    b = np.array([x for x in b if x is not None], dtype=float)
    if len(a) < 30 or len(b) < 30:
        return None
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    diff = float(b.mean() - a.mean())
    return {"mean_a": float(a.mean()), "mean_b": float(b.mean()),
            "diff": diff, "se": se, "z": diff / se if se else None,
            "n_a": int(len(a)), "n_b": int(len(b))}


def clustered(a, b):
    """the same contrast with schools as clusters: `a` and `b` are lists of
    (value, school). Every school lies in one group, so the variance of
    the difference is the sum of the two clustered variances of a mean."""
    out = []
    for rows in (a, b):
        rows = [(v, k) for v, k in rows if v is not None]
        vals = np.array([v for v, _ in rows], dtype=float)
        m = float(vals.mean())
        by = defaultdict(float)
        for v, k in rows:
            by[k] += v - m
        g = len(by)
        var = sum(x * x for x in by.values()) / len(rows) ** 2
        out.append((m, var * g / (g - 1), g))
    se = math.sqrt(out[0][1] + out[1][1])
    return {"se_clustered": se,
            "z_clustered": (out[1][0] - out[0][0]) / se if se else None,
            "n_schools_a": out[0][2], "n_schools_b": out[1][2]}


def wquantile(v, w, q):
    """weighted quantile with midpoint interpolation (analyses 005, 008)"""
    v, w = np.asarray(v, dtype=float), np.asarray(w, dtype=float)
    i = np.argsort(v)
    v, w = v[i], w[i]
    c = (np.cumsum(w) - 0.5 * w) / w.sum()
    return float(np.interp(q, c, v))


def wmedian_step(x, w):
    """weighted median as the first value whose cumulative weight reaches
    half of the total (the rule of the sending-poverty figure)"""
    x, w = np.asarray(x, dtype=float), np.asarray(w, dtype=float)
    i = np.argsort(x)
    cw = np.cumsum(w[i])
    return float(x[i][np.searchsorted(cw, 0.5 * cw[-1])])


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2)
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_MILES * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------
SQL_OIR = """
select IDENTIFIER,
       ltrim(rtrim(HIGHSCHOOLNAME)),
       ltrim(rtrim(HIGHSCHOOLCITY)),
       case when HIGHSCHOOLZIP is null then null
            else right('00000' + ltrim(rtrim(HIGHSCHOOLZIP)), 5) end,
       ltrim(rtrim(HIGHSCHOOLSTATE)),
       case when ZIPCODE is null or ltrim(rtrim(ZIPCODE)) = '' then null
            else right('00000' + ltrim(rtrim(ZIPCODE)), 5) end,
       case when HIGHSCHOOLZIP is null or ltrim(rtrim(HIGHSCHOOLZIP)) = ''
            then 0 else 1 end,
       max(case when try_cast(CURRENTTERM as float) between ? and ?
                then 1 else 0 end)
from OIR
group by IDENTIFIER, ltrim(rtrim(HIGHSCHOOLNAME)),
         ltrim(rtrim(HIGHSCHOOLCITY)),
         case when HIGHSCHOOLZIP is null then null
              else right('00000' + ltrim(rtrim(HIGHSCHOOLZIP)), 5) end,
         ltrim(rtrim(HIGHSCHOOLSTATE)),
         case when ZIPCODE is null or ltrim(rtrim(ZIPCODE)) = '' then null
              else right('00000' + ltrim(rtrim(ZIPCODE)), 5) end,
         case when HIGHSCHOOLZIP is null or ltrim(rtrim(HIGHSCHOOLZIP)) = ''
              then 0 else 1 end
"""

_CREDIT = " or ".join(f"MAT{c}_{{k}}_GRDE is not null"
                      for c in ("1073", "1093", "1214", "1224"))
SQL_OIR2 = f"""
select IDENTIFIER,
       min(STUDENTTYPE), min(PELLSTATUS), min(FIRSTGENERATIONSTATUS),
       min(ltrim(rtrim(HIGHSCHOOLNAME))), min(ltrim(rtrim(HIGHSCHOOLCITY))),
       min(ltrim(rtrim(HIGHSCHOOLSTATE))),
       max(case when {_CREDIT.format(k="AP")} then 1 else 0 end),
       max(case when {_CREDIT.format(k="DUAL")} then 1 else 0 end),
       max(HIGHEST_SATACT_MATH)
from OIR2
group by IDENTIFIER
"""

# the first mathematics course of each student; ties within the first term
# are broken by course title so that the choice is reproducible
SQL_FIRST_MAT = """
select IDENTIFIER, grade from (
  select IDENTIFIER, SHRTCKG_GRDE_CODE_FINAL as grade,
         row_number() over (
             partition by IDENTIFIER
             order by try_cast(CURRENTTERMCODE as float),
                      SHRTCKN_CRSE_TITLE, SHRTCKG_GRDE_CODE_FINAL) as rn
  from OIR2
  where SHRTCKN_SUBJ_CODE = 'MAT' and SHRTCKG_GRDE_CODE_FINAL is not null
) t where rn = 1
"""

SQL_RECORDS = """
select count(*),
       sum(case when try_cast(CURRENTTERM as float) between ? and ?
                then 1 else 0 end),
       min(try_cast(CURRENTTERM as float)), max(try_cast(CURRENTTERM as float))
from OIR
"""

SQL_SCHOOL_TABLE = "select leaid, schid, total, apmath, algii from HIGHSCHOOLS"


def read_institution():
    """student rows, in memory only"""
    lo, hi = float(config.S_START) - 0.005, float(config.S_END) + 0.005
    with pyodbc.connect(config.CONN_STRING, timeout=30) as cn:
        cur = cn.cursor()
        oir = [tuple(r) for r in cur.execute(SQL_OIR, lo, hi).fetchall()]
        records = tuple(cur.execute(SQL_RECORDS, lo, hi).fetchone())
        oir2 = [tuple(r) for r in cur.execute(SQL_OIR2).fetchall()]
        first = {r[0]: _text(r[1]) for r in
                 cur.execute(SQL_FIRST_MAT).fetchall()}
        table = [tuple(r) for r in cur.execute(SQL_SCHOOL_TABLE).fetchall()]
    return oir, oir2, first, table, records


def read_public():
    """public lookups of the project database"""
    out = {}
    with gdb.connect() as cn, cn.cursor() as cur:
        cur.execute("select hs_name, hs_city, hs_zip, n_students, ncessch, "
                    "leaid, decision from core.hs_crosswalk")
        out["xw"] = cur.fetchall()
        cur.execute(
            "select leaid, avg(100.0 * pov_5_17 / nullif(pop_5_17, 0)), "
            "avg(pop_5_17), max(name) from stg.saipe_sd "
            "where vintage between %s and %s and state_fips = '48' "
            "group by leaid", POVERTY_VINTAGES)
        out["saipe_tx"] = cur.fetchall()
        cur.execute("select ncessch, lat, lon, zip5 from raw_xwalk.edge_school "
                    "where cycle = %s", (EDGE_CYCLE,))
        out["edge"] = cur.fetchall()
        cur.execute("select zcta5, match_quality from raw_xwalk.zcta_tract_best")
        out["best"] = cur.fetchall()
        cur.execute("select zcta5, count(*) from raw_xwalk.zcta_tract_frac "
                    "group by zcta5")
        out["ntracts"] = cur.fetchall()
        cur.execute("select zcta5, n_tracts from context_zcta.oa_zcta")
        out["ntracts_oa"] = cur.fetchall()
        cur.execute("select zcta5 from context_zcta.oa_zcta "
                    "where kfr_p25 is not null")
        out["oa"] = [r[0] for r in cur.fetchall()]
        cur.execute("select cycle, combokey, alg2_tot from stg.crdc_alg2_panel "
                    "where alg2_tot is not null")
        out["alg2"] = cur.fetchall()
    return out


def data_root() -> Path:
    """folder of the raw public files (GATEWAY_DATA, or data/ beside or
    above the programs folder)"""
    cands = [os.environ.get("GATEWAY_DATA"), PKG.parent.parent / "data",
             PKG.parent.parent.parent / "data"]
    for c in cands:
        if c and Path(c).exists():
            return Path(c)
    raise FileNotFoundError("raw data folder not found; set GATEWAY_DATA")


def zcta_centroids():
    """2010 ZCTA gazetteer: internal point of each ZCTA"""
    out = {}
    with open(data_root() / "geo" / "Gaz_zcta_national.txt",
              encoding="latin-1") as fh:
        head = [h.strip() for h in fh.readline().split("\t")]
        ig, ia, io = (head.index(k) for k in
                      ("GEOID", "INTPTLAT", "INTPTLONG"))
        for line in fh:
            p = line.split("\t")
            la, lo = _float(p[ia]), _float(p[io])
            if la is not None and lo is not None:
                out[p[ig].strip().zfill(5)] = (la, lo)
    return out


# --------------------------------------------------------------------------
# the frames
# --------------------------------------------------------------------------
class Crosswalk:
    def __init__(self, rows):
        self.row = {}                      # (name, city, zip) -> record
        self.by_nc = defaultdict(list)     # (name, city) -> records
        for name, city, zp, n, ncessch, leaid, decision in rows:
            rec = {"key": (name, city, zp), "n": int(n or 0),
                   "ncessch": ncessch, "leaid": leaid, "decision": decision}
            self.row[(name, city, zp)] = rec
            self.by_nc[(name, city)].append(rec)

    def best(self, recs):
        """the record that classifies a student with several names"""
        return min(recs, key=lambda r: (PRIORITY.index(r["decision"]),
                                        -r["n"]))


def course_frame(oir, xw):
    """one entry per student of the course-record table"""
    stu = {}
    for sid, name, city, zp, state, home, has_hs_zip, act in oir:
        s = stu.setdefault(sid, {"active": False, "names": set(),
                                 "homes": set(), "pairs": set(),
                                 "any_name": False, "tx": False})
        s["active"] = s["active"] or bool(act)
        if home:
            s["homes"].add(home)
        if home and has_hs_zip:
            s["pairs"].add((home, zp))
        if name:
            s["any_name"] = True
            if state == "TX":
                s["tx"] = True
                s["names"].add((name, city, zp))
    missing = 0
    for s in stu.values():
        recs = []
        for k in s["names"]:
            if k in xw.row:
                recs.append(xw.row[k])
            else:
                missing += 1
        s["recs"] = recs
        s["best"] = xw.best(recs) if recs else None
    return stu, missing


def student_frame(oir2, first, xw, active):
    """one entry per student of the per-student table"""
    out = {}
    dfw = set(FIRST_COURSE_DFW)
    for (sid, stype, pell, fgen, name, city, state, ap, dual, sat) in oir2:
        stype, pell, fgen = _text(stype), _text(pell), _text(fgen)
        # The crosswalk is joined on name and city, as the linked models
        # join it. A recorded Texas name that the crosswalk does not hold
        # (the two tables spell a few names differently) was never
        # resolved and counts as unresolved.
        recs = xw.by_nc.get((name, city), []) if name else []
        never = False
        if not name:
            group = "no_school"
        elif recs:
            d = xw.best(recs)["decision"]
            group = ("matched" if d in USABLE else
                     "unresolved" if d == "none" else d)
        elif state != "TX":
            group = "outside_texas"
        else:
            group, never = "unresolved", True
        g = first.get(sid)
        out[sid] = {
            "active": bool(active.get(sid, False)),
            "group": group, "recs": recs, "never_matched": never,
            "school": (name, city),
            "legacy_recs": xw.by_nc.get((name, city), []),
            "ap": int(ap or 0), "dual": int(dual or 0),
            "sat": _float(sat),
            "pell": 1.0 if pell == "Pell Paid" else 0.0,
            "first_gen": (1.0 if fgen == "First Generation" else
                          0.0 if fgen == "Not First Generation" else None),
            "first_dfw": (None if g is None else
                          1.0 if g.upper() in dfw else 0.0),
            "transfer": 1.0 if stype == "Transfer" else 0.0,
        }
    return out


# --------------------------------------------------------------------------
# the quantities
# --------------------------------------------------------------------------
def coverage(stu):
    """staged coverage of the crosswalk among students with a Texas
    high-school name, each student once"""
    tx = [s for s in stu.values() if s["tx"]]
    stage = Counter(s["best"]["decision"] if s["best"] else "none" for s in tx)
    base = len(tx)
    out = {"n_students": len(stu), "n_texas_name": base,
           "n_no_name": sum(1 for s in stu.values() if not s["any_name"]),
           "n_name_outside_texas": sum(1 for s in stu.values()
                                       if s["any_name"] and not s["tx"]),
           "n_by_decision": dict(stage), "stages": []}
    run = 0
    for d in USABLE:
        run += stage.get(d, 0)
        out["stages"].append({"stage": d, "n_added": stage.get(d, 0),
                              "n_usable": run, "pct_usable": pct(run, base)})
    out["n_usable"] = run
    out["pct_usable"] = pct(run, base)
    keys = {k for s in tx for k in s["names"]}
    out["n_name_rows"] = len(keys)
    out["n_names"] = len({k[0] for k in keys})
    recs = {r["key"]: r for s in tx for r in s["recs"]}
    out["n_name_rows_by_decision"] = dict(Counter(
        r["decision"] for r in recs.values()))
    out["n_private"] = stage.get("private", 0)
    out["pct_private"] = pct(stage.get("private", 0), base)
    schools = {s["best"]["ncessch"] for s in tx
               if s["best"] and s["best"]["decision"] in USABLE}
    out["n_matched_schools"] = len(schools)
    out["n_matched_districts"] = len({
        s["best"]["leaid"] for s in tx
        if s["best"] and s["best"]["decision"] in USABLE})
    return out, schools


def disposition(frame):
    n = Counter(s["group"] for s in frame.values())
    return {"n_students": len(frame), "n_by_group": dict(n),
            "n_unresolved_absent_from_crosswalk": sum(
                1 for s in frame.values() if s["never_matched"])}


AUDIT = ("ap", "dual", "sat", "pell", "first_gen", "first_dfw", "transfer")


def audit(frame):
    """the groups of the disposition on observable characteristics, and the
    contrast of the unresolved with the matched"""
    groups = defaultdict(list)
    for s in frame.values():
        groups[s["group"]].append(s)
        groups["all"].append(s)
    cells = {}
    for g, rows in groups.items():
        if len(rows) < MIN_CELL:
            continue
        cell = {"n_students": len(rows)}
        for k in AUDIT:
            vals = [r[k] for r in rows if r[k] is not None]
            m = mean(vals)
            if k != "sat" and m is not None:
                m *= 100.0
            cell[("mean_" if k == "sat" else "pct_") + k] = m
            cell["n_" + k] = len(vals)
        cells[g] = cell
    tests = {}
    for k in AUDIT:
        t = welch([s[k] for s in groups["matched"]],
                  [s[k] for s in groups["unresolved"]])
        if t:
            t.update(clustered(
                [(s[k], s["school"]) for s in groups["matched"]],
                [(s[k], s["school"]) for s in groups["unresolved"]]))
            tests[k] = t
    return {"cells": cells, "matched_vs_unresolved": tests}


def school_table(rows):
    """the school-level table of the institutional database (a copy of the
    CRDC 2017-18 high-school universe)"""
    out = {}
    for leaid, schid, total, apmath, algii in rows:
        t = _float(total)
        key = f"{_text(leaid)}{_text(schid)}"
        out[key] = {"total": t, "apmath": _float(apmath),
                    "algii": _float(algii)}
    return out


def table_vintage(table, alg2):
    """share of schools whose Algebra II count equals the CRDC count, by
    cycle: the cycle with exact agreement is the vintage of the table"""
    by = defaultdict(lambda: [0, 0])
    for cycle, key, tot in alg2:
        h = table.get(key)
        if h is None or h["algii"] is None:
            continue
        by[cycle][0] += 1
        by[cycle][1] += int(float(tot) == h["algii"])
    return {c: {"n_schools": n, "n_equal": e, "pct_equal": pct(e, n)}
            for c, (n, e) in sorted(by.items())}


def band(h):
    """provision band of a school; a school with no recorded AP mathematics
    enrollment (zero or blank) is in the first band"""
    if not (h["apmath"] is not None and h["apmath"] > 0):
        return BANDS[0]
    rate = 100.0 * h["apmath"] / h["total"]
    return (BANDS[1] if rate <= BAND_EDGES[0] else
            BANDS[2] if rate <= BAND_EDGES[1] else BANDS[3])


def provision(frame, table):
    """credit arrival by the AP mathematics provision of the sending school"""
    cells = {b: {"n": 0, "ap": 0, "dual": 0, "schools": set(),
                 "blank": set()} for b in BANDS}
    n = 0
    for s in frame.values():
        if s["group"] != "matched":
            continue
        rec = next(r for r in s["recs"] if r["decision"] in USABLE)
        h = table.get(rec["ncessch"])
        if h is None or not (h["total"] and h["total"] > 0):
            continue
        c = cells[band(h)]
        n += 1
        c["n"] += 1
        c["ap"] += s["ap"]
        c["dual"] += s["dual"]
        c["schools"].add(rec["ncessch"])
        if h["apmath"] is None:
            c["blank"].add(rec["ncessch"])
    out = {"n_students": n,
           "n_schools": len(set().union(*(c["schools"]
                                          for c in cells.values()))),
           "n_schools_blank_ap": len(cells[BANDS[0]]["blank"]),
           "cells": []}
    for b in BANDS:
        c = cells[b]
        assert c["n"] >= MIN_CELL, b
        out["cells"].append({
            "ap_offer_band": b, "n_students": c["n"],
            "n_schools": len(c["schools"]),
            # size of the schools of the band (public school data)
            "median_school_enrollment": float(np.median(
                [table[k]["total"] for k in c["schools"]])),
            "pct_ap": pct(c["ap"], c["n"]),
            "pct_dual": pct(c["dual"], c["n"])})
    return out


def sending_poverty(stu, saipe):
    """child poverty of the sending districts, weighted by the students
    each district sent and by the children each district holds"""
    sent = Counter()
    for s in stu.values():
        b = s["best"]
        if s["tx"] and b and b["decision"] in USABLE and b["leaid"]:
            sent[b["leaid"]] += 1
    rows = [(l, float(p), float(k or 0), nm) for l, p, k, nm in saipe
            if p is not None]
    pov = np.array([r[1] for r in rows])
    kids = np.array([r[2] for r in rows])
    w = np.array([float(sent.get(r[0], 0)) for r in rows])
    edges = np.arange(0.0, POVERTY_MAX + POVERTY_BIN, POVERTY_BIN)
    h_stu, _ = np.histogram(pov, bins=edges, weights=w)
    h_kid, _ = np.histogram(pov, bins=edges, weights=kids)
    # no exported bin may rest on fewer than MIN_CELL students: a small bin
    # is pooled into its neighbor on the side of the median
    counts = h_stu.copy()
    mid = int(np.argmax(counts))
    pooled = 0
    for i in list(range(0, mid)) + list(range(len(counts) - 1, mid, -1)):
        if 0 < counts[i] < MIN_CELL:
            j = i + 1 if i < mid else i - 1
            counts[j] += counts[i]
            counts[i] = 0
            pooled += 1
    assert not ((counts > 0) & (counts < MIN_CELL)).any()
    order = np.argsort(-w)[:TOP_DISTRICTS]
    top = [{"leaid": rows[i][0], "name": rows[i][3], "n_students": int(w[i]),
            "pov_rate": float(pov[i])} for i in order]
    assert all(t["n_students"] >= MIN_CELL for t in top)
    big = int(np.argmax(counts))
    return {
        "n_students": int(w.sum()),
        "n_students_outside_frame": int(sum(sent.values()) - w.sum()),
        "n_districts": int((w > 0).sum()),
        "median_student_weighted": wmedian_step(pov, w),
        "median_child_weighted": wmedian_step(pov, kids),
        "largest_bin": {"low": float(edges[big]),
                        "high": float(edges[big + 1]),
                        "pct_students": pct(float(counts[big]),
                                            float(counts.sum()))},
        "n_bins_pooled": pooled,
        "top_districts": top,
        "histogram": [{"bin_low": float(edges[i]),
                       "bin_high": float(edges[i + 1]),
                       "pct_texas_children": pct(float(h_kid[i]),
                                                 float(h_kid.sum())),
                       "pct_students": pct(float(counts[i]),
                                           float(counts.sum()))}
                      for i in range(len(counts))],
    }


def distances(stu, xw, zc, edge):
    """home ZIP to high school, measured two ways. Each student has weight
    one, shared among their recorded pairs."""
    # (a) ZIP centroid to ZIP centroid, every student with both ZIPs
    v, w, far_home = [], [], Counter()
    misread = set()
    n_pairs = n_ungeo = 0.0
    for s in stu.values():
        k = len(s["pairs"])
        for home, hz in s["pairs"]:
            n_pairs += 1.0 / k
            if (home.startswith(MISREAD_HOME_PREFIX) and hz
                    and hz.startswith(MISREAD_SCHOOL_PREFIX)):
                misread.add(id(s))
            if home not in zc or hz not in zc:
                n_ungeo += 1.0 / k
                continue
            d = haversine(*zc[home], *zc[hz])
            v.append(d)
            w.append(1.0 / k)
            if d > FAR_MILES:
                far_home[home[:3]] += 1.0 / k
    v, w = np.array(v), np.array(w)
    tot = w.sum()
    far = sum(far_home.values())
    top = max(far_home, key=far_home.get) if far_home else None
    out = {"zip_to_zip": {
        "n_students": float(n_pairs), "n_geocoded": float(tot),
        "p50": wquantile(v, w, 0.50), "p90": wquantile(v, w, 0.90),
        "p95": wquantile(v, w, 0.95),
        "pct_within_strict": pct(w[v <= STRICT_MILES].sum(), tot),
        "pct_within_primary": pct(w[v <= PRIMARY_MILES].sum(), tot),
        "pct_same_zip": pct(w[v < 0.001].sum(), tot),
        "pct_far": pct(far, tot), "n_far": float(far),
        "far_top_home_prefix": top,
        "far_top_home_share": pct(far_home[top], far) if top else None,
        # withheld when fewer than MIN_CELL students show the pattern
        "n_misread_school_zip": (len(misread) if len(misread) >= MIN_CELL
                                 else None)}}
    # (b) ZIP centroid to the point of the resolved school
    pt, zz, ww = [], [], []
    for s in stu.values():
        b = s["best"]
        if not (s["tx"] and b and b["decision"] in USABLE and s["homes"]):
            continue
        e = edge.get(b["ncessch"])
        if e is None or e[0] is None or e[2] not in zc:
            continue
        homes = [h for h in s["homes"] if h in zc]
        for h in homes:
            pt.append(haversine(*zc[h], e[0], e[1]))
            zz.append(haversine(*zc[h], *zc[e[2]]))
            ww.append(1.0 / len(homes))
    pt, zz, ww = np.array(pt), np.array(zz), np.array(ww)
    tot = ww.sum()
    out["zip_to_school_point"] = {
        "n_students": float(tot),
        "point_pct_zero": pct(ww[pt < ZERO_MILES].sum(), tot),
        "point_pct_within_strict": pct(ww[pt <= STRICT_MILES].sum(), tot),
        "point_pct_within_primary": pct(ww[pt <= PRIMARY_MILES].sum(), tot),
        "zip_pct_zero": pct(ww[zz < ZERO_MILES].sum(), tot),
        "zip_pct_within_primary": pct(ww[zz <= PRIMARY_MILES].sum(), tot)}
    return out


def neighborhood(stu, best, ntracts, oa, ntracts_oa):
    """the home-ZIP branch: coverage by ZCTA-level context, and how poorly
    one tract would stand for a student's ZIP"""
    oa = set(oa)
    n = cov = 0
    q, t, w = [], [], []
    t2, w2 = [], []
    for s in stu.values():
        n += 1
        cov += int(any(h in oa for h in s["homes"]))
        homes = [h for h in s["homes"] if h in best]
        for h in homes:
            q.append(float(best[h]))
            t.append(float(ntracts.get(h, 0)))
            w.append(1.0 / len(homes))
        homes = [h for h in s["homes"] if h in ntracts_oa]
        for h in homes:
            t2.append(float(ntracts_oa[h]))
            w2.append(1.0 / len(homes))
    q, t, w = np.array(q), np.array(t), np.array(w)
    t2, w2 = np.array(t2), np.array(w2)
    return {"n_students": n, "n_with_home_zip": sum(
                1 for s in stu.values() if s["homes"]),
            "n_covered": cov, "pct_covered": pct(cov, n),
            "best_tract_share_median": wquantile(q, w, 0.5),
            "tracts_per_zip_mean": float((t * w).sum() / w.sum()),
            "tracts_with_context_per_zip_mean": float(
                (t2 * w2).sum() / w2.sum())}


def directory_recovery(stu, path):
    """of the students whose school the CCD directory pass recovered, the
    share whose school had been in the original directory"""
    acc = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["accept"] == "True":
                acc[(r["hs_name"], r["hs_city"])] = r["in_edge_1718"] == "True"
    n = k = 0
    for s in stu.values():
        b = s["best"]
        if not (b and b["decision"] == "auto_ccd"):
            continue
        key = b["key"][:2]
        if key in acc:
            n += 1
            k += int(acc[key])
    return {"n_students": n, "n_in_original_directory": k,
            "pct_in_original_directory": pct(k, n),
            "n_names": len(acc)}


# --------------------------------------------------------------------------
# the earlier totals, rebuilt as the earlier programs counted them
# --------------------------------------------------------------------------
def legacy_check(xw, frame, table):
    by = Counter()
    for r in xw.row.values():
        by[r["decision"]] += r["n"]
    base = sum(by.values())
    run, stages = 0, {}
    for d in USABLE:
        run += by[d]
        stages[d] = round(pct(run, base), 1)
    g = Counter()
    n021 = 0
    sch021 = set()
    label = {"auto": "matched", "auto_adj": "matched", "auto_ccd": "matched",
             "auto_vint": "matched", "private": "private", "none": "unresolved",
             "rejected": "rejected"}
    for s in frame.values():
        if not s["legacy_recs"]:
            g["no HS recorded"] += 1
        for r in s["legacy_recs"]:
            g[label[r["decision"]]] += 1
            h = table.get(r["ncessch"]) if r["ncessch"] else None
            if h is not None and h["total"] and h["total"] > 0:
                n021 += 1
                sch021.add(r["ncessch"])
    return {"crosswalk_base_rows_sum": base, "crosswalk_stage_pct": stages,
            "crosswalk_students_by_decision": dict(by),
            "disposition_with_join_duplicates": dict(g),
            "disposition_total_with_join_duplicates": sum(g.values()),
            "provision_students_any_candidate_school": n021,
            "provision_schools_any_candidate_school": len(sch021)}


# --------------------------------------------------------------------------
def profile(stu, frame, pub, xw, table, zc, edge):
    cov, schools = coverage(stu)
    cov["pct_with_name"] = pct(cov["n_students"] - cov["n_no_name"],
                               cov["n_students"])
    cov["n_absent_from_student_table"] = cov["n_students"] - len(frame)
    in_table = {k for k in schools if k in table
                and table[k]["total"] and table[k]["total"] > 0}
    cov["n_matched_schools_in_table"] = len(in_table)
    cov["pct_matched_schools_in_table"] = pct(len(in_table), len(schools))
    return {
        "coverage": cov,
        "disposition": disposition(frame),
        "audit": audit(frame),
        "provision": provision(frame, table),
        "sending_poverty": sending_poverty(stu, pub["saipe_tx"]),
        "distance": distances(stu, xw, zc, edge),
        "neighborhood": neighborhood(stu, dict(pub["best"]),
                                     dict(pub["ntracts"]), pub["oa"],
                                     dict(pub["ntracts_oa"])),
        "directory_recovery": directory_recovery(
            stu, ROOT_FIG / "011_ccd_recovery.csv"),
    }


def main() -> int:
    oir, oir2, first, table_rows, records = read_institution()
    pub = read_public()
    xw = Crosswalk(pub["xw"])
    table = school_table(table_rows)
    zc = zcta_centroids()
    edge = {k: (_float(la), _float(lo), z) for k, la, lo, z in pub["edge"]}

    stu, missing = course_frame(oir, xw)
    active = {sid: s["active"] for sid, s in stu.items()}
    frame = student_frame(oir2, first, xw, active)

    out = {
        "window": {"from_term": config.S_START, "to_term": config.S_END,
                   "rule": "at least one course record in a term of the "
                           "window (course-record table)"},
        "parameters": {
            "min_cell": MIN_CELL, "usable_decisions": list(USABLE),
            "first_course_dfw": list(FIRST_COURSE_DFW),
            "band_edges_pct": list(BAND_EDGES),
            "poverty_vintages": list(POVERTY_VINTAGES),
            "poverty_bin": POVERTY_BIN, "primary_miles": PRIMARY_MILES,
            "strict_miles": STRICT_MILES, "far_miles": FAR_MILES,
            "edge_cycle": EDGE_CYCLE},
        "course_records": {
            "n_extract": int(records[0]), "n_in_window": int(records[1]),
            "first_term": float(records[2]), "last_term": float(records[3])},
        "tract_assignment": {
            "n_zctas": len(pub["best"]),
            "best_tract_share_median_unweighted": float(np.median(
                [float(q) for _, q in pub["best"]]))},
        "crosswalk": {
            "n_name_rows": len(xw.row),
            "n_name_rows_by_decision": dict(Counter(
                r["decision"] for r in xw.row.values())),
            "n_name_city_pairs_with_several_zip_rows": sum(
                1 for v in xw.by_nc.values() if len(v) > 1),
            "n_recorded_names_absent_from_crosswalk": missing},
        "school_table": {
            "n_schools": len(table),
            "vintage_check": table_vintage(table, pub["alg2"])},
    }
    # The whole extract is profiled only to check this program against the
    # earlier analyses. That profile goes to a local file; the released
    # statistics hold the totals of the extract and the active students.
    extract = profile(stu, frame, pub, xw, table, zc, edge)
    check = {"legacy_check": legacy_check(xw, frame, table),
             "extract": extract}
    out["extract_totals"] = {
        "n_students": extract["coverage"]["n_students"],
        "n_students_of_credit_table": extract["disposition"]["n_students"],
        "n_absent_from_student_table":
            extract["coverage"]["n_absent_from_student_table"]}
    w_stu = {k: s for k, s in stu.items() if s["active"]}
    w_frame = {k: s for k, s in frame.items() if s["active"]}
    out["active"] = profile(w_stu, w_frame, pub, xw, table, zc, edge)

    FIG.mkdir(parents=True, exist_ok=True)
    with open(FIG / "linkage_profile_check.json", "w",
              encoding="utf-8") as fh:
        json.dump(check, fh, indent=1)
    with open(FIG / "linkage_profile_stats.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    a = out["active"]
    with open(FIG / "linkage_profile_provision.csv", "w", newline="",
              encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["ap_offer_band", "n_students", "n_schools", "pct_ap",
                     "pct_dual"])
        for c in a["provision"]["cells"]:
            wr.writerow([c["ap_offer_band"], c["n_students"], c["n_schools"],
                         f"{c['pct_ap']:.3f}", f"{c['pct_dual']:.3f}"])
    with open(FIG / "linkage_profile_poverty.csv", "w", newline="",
              encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["bin_low", "bin_high", "pct_texas_children",
                     "pct_students"])
        for h in a["sending_poverty"]["histogram"]:
            wr.writerow([h["bin_low"], h["bin_high"],
                         f"{h['pct_texas_children']:.3f}",
                         f"{h['pct_students']:.3f}"])
    with open(FIG / "linkage_profile_districts.csv", "w", newline="",
              encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["leaid", "name", "n_students", "pov_rate_2010_2018"])
        for t in a["sending_poverty"]["top_districts"]:
            wr.writerow([t["leaid"], t["name"], t["n_students"],
                         f"{t['pov_rate']:.2f}"])

    for pop, p in (("extract", extract), ("active", out["active"])):
        c, d = p["coverage"], p["disposition"]
        print(f"{pop}: {c['n_students']:,} students, "
              f"{c['n_texas_name']:,} with a Texas high-school name, "
              f"{c['pct_usable']:.1f}% reached; per-student table "
              f"{d['n_students']:,}: {d['n_by_group']}")
    print("legacy check:", json.dumps(check["legacy_check"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
