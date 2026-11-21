"""Module C data assembly (analysis_plan.md, Sections 2 to 5).

Student rows are read from the institutional source in place and held in
memory only; this module writes nothing to disk. The identifier is
replaced inside the query by a SHA-256 surrogate under a random per-run
salt, so the surrogate is a join key for one run and nothing else.
School and district context is read from GATEWAY and joined in memory.

Arrays and plain lists throughout; cross-referencing in SQL; no
dataframes.
"""
import csv
import os
import sys
from pathlib import Path

import numpy as np
import pyodbc
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
CODE = HERE.parent
sys.path.insert(0, str(CODE))
from gateway import db  # noqa: E402
from student_success import config as _ss  # noqa: E402

FIRST_COHORT, LAST_COHORT, LAST_Q2_COHORT = 2009, 2019, 2018
CYCLES = {2014: "2013-14", 2016: "2015-16", 2018: "2017-18"}
SCHOOL_SUBJ = ("calculus", "ap_math", "ap_science", "dual")
DIST_CSV = CODE / "figures" / "008_coord_distances.csv"

# entry mathematics level (stage0_maps.md, section 2)
MAT_LEVEL = {203: 0, 213: 0,
             1023: 1, 1033: 1, 1043: 1, 1053: 1, 1073: 1, 1153: 1, 1163: 1,
             1093: 2,
             1133: 3, 1193: 3, 1194: 3, 1214: 3,
             1223: 4, 1224: 4, 2213: 4, 2214: 4, 2233: 4}
DFW_CODES = {"D+", "D", "D-", "F", "W", "NC"}
OK_CODES = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "CR"}

_FLD = [f"MAT{c}_{r}_GRDE" for r in ("AP", "DUAL", "CLEP")
        for c in ("1073", "1093", "1214", "1224")]


def _has(route: str) -> str:
    return " or ".join(
        f"(max({f}) is not null and ltrim(rtrim(max({f}))) <> '')"
        for f in _FLD if f"_{route}_" in f)


_FT = "min(try_cast(FIRSTTERMCODE as float))"
SQL_STUDENTS = f"""
with S as (
  select IDENTIFIER, {_FT} ft,
         max(case when STUDENTTYPE = 'New' then 1 else 0 end) is_new,
         max(CAP) cap, max(FA_APPLIED) fa, max(AGINum) agi,
         max(PELLSTATUS) pell, max(FIRSTGENERATIONSTATUS) fg,
         max(GENDER) gender, max(ETHNICITY) eth,
         max(HIGHEST_SATACT_MATH) hm, max(HIGHEST_SATACT_ERW) he,
         min(ltrim(rtrim(HIGHSCHOOLNAME))) hs_name,
         min(ltrim(rtrim(HIGHSCHOOLCITY))) hs_city,
         min(ltrim(rtrim(ZIPCODE))) zip,
         case when {_has('AP')} then 1 else 0 end ap,
         case when {_has('DUAL')} then 1 else 0 end dual,
         case when {_has('CLEP')} then 1 else 0 end clep
  from OIR group by IDENTIFIER)
select convert(varchar(64), hashbytes('SHA2_256', ? + IDENTIFIER), 2),
       cast(floor(ft) as int), cap, fa, agi, pell, fg, gender, eth, hm, he,
       hs_name, hs_city, zip, ap, dual, clep
from S
where is_new = 1 and abs(ft - floor(ft) - 0.66) < 0.01
  and ft between __FIRST__.6 and {LAST_COHORT}.7
"""

# term dimension: ordered index = 3 * year + season (0 spring, 1 summer,
# 2 fall). Entry fall has offset 0; the first-year window is offsets 0-2.
_TIX = ("cast(floor({c}) as int) * 3 + case when {c} - floor({c}) < 0.2 "
        "then 0 when {c} - floor({c}) < 0.5 then 1 else 2 end")
SQL_COURSES = f"""
with C as (
  select IDENTIFIER, {_FT} ft from OIR where STUDENTTYPE = 'New'
  group by IDENTIFIER
  having abs({_FT} - floor({_FT}) - 0.66) < 0.01
     and {_FT} between __FIRST__.6 and {LAST_Q2_COHORT}.7),
T as (select distinct CURRENTTERM tc,
             {_TIX.format(c='CURRENTTERM')} tix from OIR)
select convert(varchar(64), hashbytes('SHA2_256', ? + O.IDENTIFIER), 2),
       O.SHRTCKN_SUBJ_CODE, try_cast(O.CT_SUBJECT as int), T.tix,
       O.SHRTCKG_GRDE_CODE_FINAL, O.SHRGRDE_QUALITY_POINTS,
       O.SHRGRDE_GPA_IND
from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
       join T on T.tc = O.CURRENTTERM
where T.tix - (cast(floor(C.ft) as int) * 3 + 2) between 0 and 2
  and try_cast(O.CT_SUBJECT as int) < 3000
"""


def set_first_cohort(year: int) -> None:
    """restrict the population to entrants of Fall `year` and later

    Added 2026-11-19 for the deviation recorded in Section 17 of the
    analysis plan (cohorts Fall 2014 through Fall 2019). The registered
    run used the default, Fall 2009.
    """
    global FIRST_COHORT
    FIRST_COHORT = int(year)


def _sql(template: str) -> str:
    return template.replace("__FIRST__", str(FIRST_COHORT))


def cycle_of(cohort: int) -> tuple[str, int]:
    """nearest eligible CRDC cycle to the senior spring; ties to earlier"""
    best = min(CYCLES, key=lambda c: (abs(cohort - c), c))
    return CYCLES[best], abs(cohort - best)


def load_students(salt: str) -> dict:
    with pyodbc.connect(_ss.CONN_STRING, timeout=20) as cn:
        rows = cn.cursor().execute(_sql(SQL_STUDENTS), salt).fetchall()
    n = len(rows)
    f = lambda j, d=np.nan: np.array(  # noqa: E731
        [d if r[j] is None else float(r[j]) for r in rows])
    applied = np.array([r[3] == "Applied" for r in rows])
    agi = f(4)
    agi[~applied] = np.nan           # 'No FAFSA' holds a negative sentinel
    return {
        "n": n, "sid": [r[0] for r in rows],
        "cohort": np.array([r[1] for r in rows], dtype=int),
        "cap": f(2, 0.0), "applied": applied, "agi": agi,
        "pell": np.array([r[5] == "Pell Paid" for r in rows], dtype=float),
        "fg": [(r[6] or "Unknown").strip() for r in rows],
        "gender": [(r[7] or "Unknown").strip() for r in rows],
        "eth": [(r[8] or "Unknown").strip() for r in rows],
        "hm": f(9), "he": f(10),
        "hs_name": [r[11] or "" for r in rows],
        "hs_city": [r[12] or "" for r in rows],
        "zip": [(r[13] or "")[:5] for r in rows],
        "ap": f(14, 0.0), "dual": f(15, 0.0), "clep": f(16, 0.0),
    }


def load_context(keys: set) -> dict:
    """crosswalk, school measures by cycle, district poverty, distances"""
    ctx = {"xw": {}, "school": {c: {} for c in CYCLES.values()},
           "saipe": {}, "dist": {}}
    with db.connect() as cn, cn.cursor() as cur:
        cur.execute("select hs_name, hs_city, ncessch, leaid "
                    "from core.hs_crosswalk where decision like 'auto%%' "
                    "and ncessch is not null")
        for name, city, nces, lea in cur.fetchall():
            if (name, city) in keys:
                ctx["xw"][(name, city)] = (nces, lea)
        schools = sorted({v[0] for v in ctx["xw"].values()})
        cur.execute("""
            select a.cycle, a.combokey, a.enr_total, a.hs_enr_est,
                   a.serves_hs, c.subject, c.enr, c.rc
            from stg.crdc_course_school_attr a
            left join stg.crdc_course_school c
              on c.cycle = a.cycle and c.combokey = a.combokey
             and c.subject = any(%s)
            where a.cycle = any(%s) and a.combokey = any(%s)""",
                    (list(SCHOOL_SUBJ), list(CYCLES.values()), schools))
        for cyc, key, enr, hs, serves, subj, e, rc in cur.fetchall():
            r = ctx["school"][cyc].setdefault(
                key, {"enr": enr, "hs": hs, "serves": bool(serves)})
            if subj is None:
                continue
            if e is not None:
                r[subj] = float(e)
            elif rc == -9 and serves:
                r[subj] = 0.0          # skip logic: zero classes
            else:
                r[subj] = np.nan       # any other code is missing
        cur.execute("select leaid, vintage, pop_5_17, pov_5_17 "
                    "from stg.saipe_sd where vintage between %s and %s "
                    "and pop_5_17 > 0 and pov_5_17 is not null",
                    (FIRST_COHORT - 4, LAST_COHORT - 1))
        for lea, v, pop, pov in cur.fetchall():
            ctx["saipe"][(lea, int(v))] = (float(pov) / float(pop),
                                           float(pop))
    with open(DIST_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ctx["dist"][(r["home_zip"], r["hs_name"], r["hs_city"])] = \
                float(r["miles_pt"])
    return ctx


def assemble(S: dict, ctx: dict) -> dict:
    """student-level analysis arrays; A['linked'] marks the linked sample"""
    n = S["n"]
    A = dict(S)
    nan = lambda: np.full(n, np.nan)  # noqa: E731
    A["school"] = np.full(n, "", dtype=object)
    A["district"] = np.full(n, "", dtype=object)
    A["lag"] = np.zeros(n)
    for k in ("calc", "apm", "aps", "dualr", "sch_enr", "pov", "dpop",
              "miles"):
        A[k] = nan()
    A["cycle"] = np.empty(n, dtype=object)
    raw = {"calculus": "calc", "ap_math": "apm", "ap_science": "aps",
           "dual": "dualr"}
    for i in range(n):
        co = int(S["cohort"][i])
        cyc, lag = cycle_of(co)
        A["cycle"][i], A["lag"][i] = cyc, lag
        hit = ctx["xw"].get((S["hs_name"][i], S["hs_city"][i]))
        if hit is None:
            continue
        nces = hit[0]
        lea = nces[:7]                 # district: first seven digits
        A["school"][i], A["district"][i] = nces, lea
        A["miles"][i] = ctx["dist"].get(
            (S["zip"][i], S["hs_name"][i], S["hs_city"][i]), np.nan)
        sc = ctx["school"][cyc].get(nces)
        if sc and sc["hs"] and sc["hs"] > 0:
            A["sch_enr"][i] = sc["enr"] or np.nan
            for subj, key in raw.items():
                src = sc
                if subj == "dual" and cyc == "2013-14":
                    # 2013-14 holds a dual-enrollment indicator only;
                    # the rate comes from the 2015-16 cycle
                    src = ctx["school"]["2015-16"].get(nces)
                    if not (src and src["hs"] and src["hs"] > 0):
                        continue
                v = src.get(subj, np.nan)
                A[key][i] = v / src["hs"]
        vals = [ctx["saipe"][(lea, v)][0] for v in range(co - 4, co)
                if (lea, v) in ctx["saipe"]]
        if vals:
            A["pov"][i] = float(np.mean(vals))
        pop = ctx["saipe"].get((lea, co - 1))
        if pop:
            A["dpop"][i] = pop[1]

    # winsorize school rates at the 99th percentile within cycle and
    # standardize Calculus and AP mathematics within cycle across the
    # sending schools (one vote per school)
    A["none_calc"] = (A["calc"] == 0).astype(float)
    A["none_apm"] = (A["apm"] == 0).astype(float)
    z = {k: nan() for k in ("calc", "apm")}
    for cyc in CYCLES.values():
        m = (A["cycle"] == cyc) & (A["school"] != "")
        for key in raw.values():
            ok = m & np.isfinite(A[key])
            if not ok.any():
                continue
            _, first = np.unique(A["school"][ok], return_index=True)
            sv = A[key][ok][first]                 # one value per school
            cap = np.percentile(sv, 99)
            A[key][ok] = np.minimum(A[key][ok], cap)
            if key in z:
                sv = np.minimum(sv, cap)
                z[key][ok] = (A[key][ok] - sv.mean()) / sv.std()
    A["index"] = (z["calc"] + z["apm"]) / 2

    # scores standardized within entry cohort; AGI rank within cohort
    # among aid applicants (zero and negative values included)
    A["zm"], A["zv"], A["agi_rank"] = nan(), nan(), nan()
    for co in np.unique(S["cohort"]):
        c = S["cohort"] == co
        for raw_k, zk in (("hm", "zm"), ("he", "zv")):
            ok = c & np.isfinite(S[raw_k])
            A[zk][ok] = (S[raw_k][ok] - S[raw_k][ok].mean()) / \
                S[raw_k][ok].std()
        ok = c & S["applied"] & np.isfinite(S["agi"])
        A["agi_rank"][ok] = rankdata(S["agi"][ok]) / ok.sum()
    A["score_missing"] = (~(np.isfinite(A["zm"]) &
                            np.isfinite(A["zv"]))).astype(float)
    A["agi_nonpos"] = (S["applied"] & (S["agi"] <= 0)).astype(float)
    A["no_fafsa"] = (~S["applied"]).astype(float)
    A["route"] = np.where((S["ap"] > 0) | (S["clep"] > 0), 2,
                          np.where(S["dual"] > 0, 1, 0))
    A["has_key"] = A["school"] != ""
    A["linked"] = (A["has_key"] & np.isfinite(A["index"])
                   & np.isfinite(A["aps"]) & np.isfinite(A["dualr"])
                   & np.isfinite(A["sch_enr"]) & np.isfinite(A["pov"])
                   & np.isfinite(A["dpop"]))
    return A


def load_courses(salt: str, sid: list) -> dict:
    """first attempts in the first-year window, one row per student-course

    A first attempt is the earliest term holding a row for the course.
    When that term holds several rows for the course, the grade is their
    mean over graded rows and DFW is 1 if any row is a D, F, W or NC.
    """
    pos = {s: i for i, s in enumerate(sid)}
    with pyodbc.connect(_ss.CONN_STRING, timeout=20) as cn:
        rows = cn.cursor().execute(_sql(SQL_COURSES), salt).fetchall()
    acc = {}
    for s, subj, num, tix, code, qp, ind in rows:
        i = pos.get(s)
        if i is None or num is None:
            continue
        code = (code or "").strip()
        key = (i, subj.strip(), int(num))
        cur = acc.get(key)
        if cur is None or tix < cur[0]:
            cur = acc[key] = [tix, [], 0, 0]
        elif tix > cur[0]:
            continue
        if ind == "Y" and qp is not None:
            cur[1].append(float(qp))
        if code in DFW_CODES:
            cur[2] = 1
        if code in DFW_CODES or code in OK_CODES:
            cur[3] = 1
    m = len(acc)
    C = {"stu": np.zeros(m, dtype=int), "subj": np.empty(m, dtype=object),
         "num": np.zeros(m, dtype=int), "tix": np.zeros(m, dtype=int),
         "grade": np.full(m, np.nan), "dfw": np.full(m, np.nan)}
    for r, ((i, subj, num), (tix, qps, dfw, valid)) in enumerate(acc.items()):
        C["stu"][r], C["subj"][r], C["num"][r], C["tix"][r] = \
            i, subj, num, tix
        if qps:
            C["grade"][r] = float(np.mean(qps))
        if valid:
            C["dfw"][r] = float(dfw)
    return C


def entry_math_level(C: dict, n: int) -> np.ndarray:
    """level of the first mathematics course in the window; -1 if none"""
    lvl = np.full(n, -1.0)
    first = {}
    for r in np.flatnonzero(C["subj"] == "MAT"):
        L = MAT_LEVEL.get(int(C["num"][r]))
        if L is None:
            continue
        i, t = int(C["stu"][r]), int(C["tix"][r])
        cur = first.get(i)
        if cur is None or t < cur[0]:
            first[i] = [t, L]
        elif t == cur[0]:
            cur[1] = max(cur[1], L)
    for i, (_, L) in first.items():
        lvl[i] = L
    return lvl


def new_salt() -> str:
    return os.urandom(16).hex()
