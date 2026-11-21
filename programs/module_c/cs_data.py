"""Class-size addendum: sections and first attempts with their section
(Economics/Paper0/module_c/class_size_addendum.md, Sections 2 to 4).

Extends the Module C assembly without changing it. Student rows are read
in place and held in memory only; nothing is written to disk here. The
student identifier and the instructor identifier are replaced inside the
query by SHA-256 surrogates under the random per-run salt, so neither
leaves the database in the clear and the surrogates are join keys for
one run only.

`with_outcomes=False` builds a query that selects no grade field at all:
the outcome-blind mode used for the Stage 0 checks before the freeze.

Arrays and plain lists; cross-referencing in SQL; no dataframes.
"""
import numpy as np
import pyodbc

import mc_data as D
from student_success import config as _ss

LECTURE = "Lecture face-to-face"
LECTURE_ANY = {"Lecture face-to-face", "Lecture, internet",
               "Lecture, Hybrid internet", "Lect,interactiveTV,facetoface",
               "Lecture, interactive TV", "Lect, multimedia, face-to-face"}
MIN_SECTION = 10          # sections with more than this many students
NEXT_OFFSETS = 3          # next-course window: spring, summer, next fall
_TIX = D._TIX.format(c="CURRENTTERM")

SQL_SECTIONS = f"""
select {_TIX}, SHRTCKN_CRN, count(distinct IDENTIFIER),
       convert(varchar(64), hashbytes('SHA2_256',
               ? + max(ltrim(rtrim(PRIMARY_INSTRUCTOR_ID)))), 2),
       count(distinct PRIMARY_INSTRUCTOR_ID), max(STVSCHD_DESC),
       max(SHRTCKN_SUBJ_CODE), max(try_cast(CT_SUBJECT as int))
from OIR
where CURRENTTERM >= __FIRST__.6 and CURRENTTERM <= {D.LAST_COHORT}.7
  and try_cast(CT_SUBJECT as int) < 3000
group by CURRENTTERM, SHRTCKN_CRN
"""

_OUTCOME_COLS = ("O.SHRTCKG_GRDE_CODE_FINAL, O.SHRGRDE_QUALITY_POINTS, "
                 "O.SHRGRDE_GPA_IND")
_BLIND_COLS = ("cast(null as varchar(6)), cast(null as float), "
               "cast(null as char(1))")
SQL_ROWS = f"""
with C as (
  select IDENTIFIER, {D._FT} ft from OIR where STUDENTTYPE = 'New'
  group by IDENTIFIER
  having abs({D._FT} - floor({D._FT}) - 0.66) < 0.01
     and {D._FT} between __FIRST__.6 and {D.LAST_Q2_COHORT}.7),
T as (select distinct CURRENTTERM tc,
             {D._TIX.format(c='CURRENTTERM')} tix from OIR)
select convert(varchar(64), hashbytes('SHA2_256', ? + O.IDENTIFIER), 2),
       O.SHRTCKN_SUBJ_CODE, try_cast(O.CT_SUBJECT as int), T.tix,
       T.tix - (cast(floor(C.ft) as int) * 3 + 2), O.SHRTCKN_CRN,
       __COLS__
from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
       join T on T.tc = O.CURRENTTERM
where T.tix - (cast(floor(C.ft) as int) * 3 + 2) between 0 and {NEXT_OFFSETS}
  and try_cast(O.CT_SUBJECT as int) < 3000
"""


def load_sections(salt: str) -> dict:
    """every lower-division section of the window, keyed by (term, CRN)

    Section size counts every student holding a row in the section,
    whatever the student's entry cohort or grade outcome.
    """
    with pyodbc.connect(_ss.CONN_STRING, timeout=20) as cn:
        rows = cn.cursor().execute(D._sql(SQL_SECTIONS), salt).fetchall()
    # The instructor label is the smallest section key the instructor
    # holds in the window: an integer that depends on neither the salt
    # nor the order in which rows arrive, so bootstrap draws reproduce.
    # A section without an instructor is its own group.
    label, sec = {}, {}
    for tix, crn, n, inst, n_inst, sched, subj, num in rows:
        key = int(tix) * 1000000 + int(crn)
        if inst is not None:
            label[inst] = min(label.get(inst, key), key)
    for tix, crn, n, inst, n_inst, sched, subj, num in rows:
        key = int(tix) * 1000000 + int(crn)
        sec[(int(tix), int(crn))] = {
            "size": int(n), "inst": -key if inst is None else label[inst],
            "n_inst": int(n_inst), "sched": (sched or "").strip(),
            "subj": (subj or "").strip(), "num": num}
    return sec


def load_rows(salt: str, sid: list, sec: dict, with_outcomes: bool) -> dict:
    """first attempts, one row per student-course, with the section

    A first attempt is the earliest term holding a row for the course
    (the Module C rule). `nsec` counts the distinct sections the student
    holds in that term for the course; rows with `nsec` above one have
    no single section and stay out of the class-size models.
    """
    pos = {s: i for i, s in enumerate(sid)}
    sql = D._sql(SQL_ROWS).replace(
        "__COLS__", _OUTCOME_COLS if with_outcomes else _BLIND_COLS)
    with pyodbc.connect(_ss.CONN_STRING, timeout=20) as cn:
        rows = cn.cursor().execute(sql, salt).fetchall()
    acc = {}
    for s, subj, num, tix, off, crn, code, qp, ind in rows:
        i = pos.get(s)
        if i is None or num is None:
            continue
        code = (code or "").strip()
        key = (i, subj.strip(), int(num))
        cur = acc.get(key)
        if cur is None or tix < cur[0]:
            cur = acc[key] = [tix, off, set(), [], 0, 0]
        elif tix > cur[0]:
            continue
        cur[2].add(int(crn))
        if ind == "Y" and qp is not None:
            cur[3].append(float(qp))
        if code in D.DFW_CODES:
            cur[4] = 1
        if code in D.DFW_CODES or code in D.OK_CODES:
            cur[5] = 1
    m = len(acc)
    C = {"stu": np.zeros(m, dtype=int), "subj": np.empty(m, dtype=object),
         "num": np.zeros(m, dtype=int), "tix": np.zeros(m, dtype=int),
         "off": np.zeros(m, dtype=int), "nsec": np.zeros(m, dtype=int),
         "size": np.zeros(m), "inst": np.zeros(m, dtype=np.int64),
         "secid": np.zeros(m, dtype=np.int64),
         "sched": np.empty(m, dtype=object),
         "grade": np.full(m, np.nan), "dfw": np.full(m, np.nan)}
    for r, ((i, subj, num), (tix, off, crns, qps, dfw, valid)) in \
            enumerate(acc.items()):
        C["stu"][r], C["subj"][r], C["num"][r] = i, subj, num
        C["tix"][r], C["off"][r], C["nsec"][r] = tix, off, len(crns)
        C["sched"][r] = ""
        if len(crns) == 1:
            crn = next(iter(crns))
            s = sec.get((int(tix), crn))
            if s is not None:
                C["size"][r], C["inst"][r] = s["size"], s["inst"]
                C["sched"][r] = s["sched"]
                C["secid"][r] = int(tix) * 1000000 + crn
        if qps:
            C["grade"][r] = float(np.mean(qps))
        if valid:
            C["dfw"][r] = float(dfw)
    return C


def next_math(C: dict) -> dict:
    """the next mathematics course after a mathematics first attempt in
    the entry fall

    For each origin row (MAT, offset 0), the next course is the student's
    first attempt at a different MAT course in the earliest later term of
    the window (offsets 1 to NEXT_OFFSETS); ties go to the course with
    the highest entry-mathematics level. Returns arrays aligned with the
    origin rows: `row` (index into C) and `nxt` (index into C, -1 when
    the student takes no later mathematics course in the window).
    """
    mat = np.flatnonzero(C["subj"] == "MAT")
    later = {}
    for r in mat:
        if 1 <= C["off"][r] <= NEXT_OFFSETS:
            i = int(C["stu"][r])
            key = (int(C["tix"][r]), -D.MAT_LEVEL.get(int(C["num"][r]), -1),
                   int(C["num"][r]))
            if i not in later or key < later[i][0]:
                later[i] = (key, r)
    origin = [r for r in mat if C["off"][r] == 0]
    nxt = np.array([later.get(int(C["stu"][r]), (None, -1))[1]
                    for r in origin], dtype=int)
    return {"row": np.array(origin, dtype=int), "nxt": nxt}
