"""
Ingest CRDC course enrollment for every course family into GATEWAY.

PURPOSE. The district exhibits of Paper 0 use Algebra II alone. This
module loads the remaining course families of the CRDC school files so
that the Algebra II poverty gradient can be compared with the gradients
of the other subjects under one estimator and one frame.

CYCLES. 2015-16 (one wide CSV), 2017-18 and 2021-22 (per-topic CSVs)
hold all 15 subjects. 2013-14 (per-topic XLSX) is loaded for the
subjects the Module C school block needs (Algebra II, advanced
mathematics, Calculus, AP, IB); that cycle collected dual enrollment as
an indicator only, so it holds no dual-enrollment count. 2011-12 is left
out for its anomalous zeros.

SUBJECTS (15). Algebra I in grades 7-8, 9-10 and 11-12; Geometry;
Algebra II; Advanced Mathematics; Calculus; Biology; Chemistry; Physics;
AP (at least one course), AP mathematics, AP science; International
Baccalaureate; dual enrollment. Each subject is the sum of its male and
female total columns (plus the single grade-7 count for early Algebra I
in the cycles that split grades 7 and 8).

RESERVE CODES. CRDC stores reserve codes inside the count columns. For
the course items the dominant code is -9 (not applicable / skip logic):
a school without high-school grades skips the item, and so does a
high-school that reports zero classes in the subject (2017-18: Algebra
II classes > 0 at 21,419 schools, and exactly those 21,419 schools hold
a non-negative Algebra II enrollment). Within a district that serves
high-school grades a -9 is therefore a structural zero. Every other
code (-3, -5, -6, -11, -12, -13, blank) is missing data. The staging
table keeps `enr` (NULL when no component is a count) and `rc` (the
most negative reserve code seen among the components, NULL when all
components are counts), so both readings stay recoverable.

KEYS. COMBOKEY is rebuilt as LEAID(7) || SCHID(5); the stored key of
the 2015-16 wide file has its leading zeros stripped.

HIGH-SCHOOL ENROLLMENT ESTIMATE. CRDC public files hold total school
enrollment without a grade split. `hs_enr_est` prorates total
enrollment by the share of the school's K-12 grade flags that are
grades 9-12 (an ungraded school uses its ungraded-detail flags). It is
the denominator of the per-high-school-student robustness measure.

No dataframes: csv module in, COPY out, aggregation in SQL.
"""

from __future__ import annotations

import csv
import glob
import hashlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402

DATA = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "CRDC"))

D1314 = "2013-14-crdc-data/2013-14 CRDC/School/CRDC-collected data file for Schools/"
X1314 = {"Enrollment": "03 Enrollment",
         "School Characteristics": "01 School Characteristics",
         "Other Math": "05-3 Other Math Courses and Classes",
         "AP and IB": ("06 Advanced Placement and International Baccalaureate "
                       "Diploma Programme Enrollment")}
D1718 = ("2017-18-crdc-data/2017-18-crdc-data-corrected-publication 2/"
         "2017-18 Public-Use Files/Data/SCH/CRDC/CSV/")
D2122 = "2021-22-crdc-data/SCH/"
W1516 = "2015-16-crdc-data/Data Files and Layouts/CRDC 2015-16 School Data.csv"

# subject -> (file stem, component columns); one spec per cycle because
# the column vocabulary drifts (geometry in 2015-16, early Algebra I and
# dual enrollment in 2021-22)
_COMMON = {
    "alg1_g0910": ("Algebra I", ["TOT_ALGENR_GS0910_M", "TOT_ALGENR_GS0910_F"]),
    "alg1_g1112": ("Algebra I", ["TOT_ALGENR_GS1112_M", "TOT_ALGENR_GS1112_F"]),
    "alg2": ("Algebra II", ["TOT_MATHENR_ALG2_M", "TOT_MATHENR_ALG2_F"]),
    "adv_math": ("Advanced Mathematics",
                 ["TOT_MATHENR_ADVM_M", "TOT_MATHENR_ADVM_F"]),
    "calculus": ("Calculus", ["TOT_MATHENR_CALC_M", "TOT_MATHENR_CALC_F"]),
    "biology": ("Biology", ["TOT_SCIENR_BIOL_M", "TOT_SCIENR_BIOL_F"]),
    "chemistry": ("Chemistry", ["TOT_SCIENR_CHEM_M", "TOT_SCIENR_CHEM_F"]),
    "physics": ("Physics", ["TOT_SCIENR_PHYS_M", "TOT_SCIENR_PHYS_F"]),
    "ap_any": ("Advanced Placement", ["TOT_APENR_M", "TOT_APENR_F"]),
    "ap_math": ("Advanced Placement",
                ["TOT_APMATHENR_M", "TOT_APMATHENR_F"]),
    "ap_science": ("Advanced Placement",
                   ["TOT_APSCIENR_M", "TOT_APSCIENR_F"]),
    "ib": ("International Baccalaureate", ["TOT_IBENR_M", "TOT_IBENR_F"]),
}
_G0708_SPLIT = ("Algebra I", ["SCH_ALGENR_G07", "TOT_ALGENR_G08_M",
                              "TOT_ALGENR_G08_F"])
SUBJECTS = {
    "2013-14": {
        "alg2": ("Other Math", ["TOT_MATHENR_ALG2_M", "TOT_MATHENR_ALG2_F"]),
        "adv_math": ("Other Math",
                     ["TOT_MATHENR_ADVM_M", "TOT_MATHENR_ADVM_F"]),
        "calculus": ("Other Math",
                     ["TOT_MATHENR_CALC_M", "TOT_MATHENR_CALC_F"]),
        "ap_any": ("AP and IB", ["TOT_APENR_M", "TOT_APENR_F"]),
        "ap_math": ("AP and IB", ["TOT_APMATHENR_M", "TOT_APMATHENR_F"]),
        "ap_science": ("AP and IB", ["TOT_APSCIENR_M", "TOT_APSCIENR_F"]),
        "ib": ("AP and IB", ["TOT_IBENR_M", "TOT_IBENR_F"]),
    },
    "2015-16": dict(_COMMON,
                    alg1_g0708=_G0708_SPLIT,
                    geometry=("Geometry", ["TOT_GEOM_M", "TOT_GEOM_F"]),
                    dual=("Dual Enrollment", ["TOT_DUAL_M", "TOT_DUAL_F"])),
    "2017-18": dict(_COMMON,
                    alg1_g0708=_G0708_SPLIT,
                    geometry=("Geometry", ["TOT_MATHENR_GEOM_M",
                                           "TOT_MATHENR_GEOM_F"]),
                    dual=("Dual Enrollment", ["TOT_DUAL_M", "TOT_DUAL_F"])),
    "2021-22": dict(_COMMON,
                    alg1_g0708=("Algebra I", ["TOT_ALGENR_G0708_M",
                                              "TOT_ALGENR_G0708_F"]),
                    geometry=("Geometry", ["TOT_MATHENR_GEOM_M",
                                           "TOT_MATHENR_GEOM_F"]),
                    dual=("Dual Enrollment", ["TOT_DUALENR_M",
                                              "TOT_DUALENR_F"])),
}
ENR_COLS = {"2013-14": ["TOT_ENR_M", "TOT_ENR_F"],
            "2015-16": ["TOT_ENR_M", "TOT_ENR_F"],
            "2017-18": ["TOT_ENR_M", "TOT_ENR_F"],
            "2021-22": ["TOT_ENR_M", "TOT_ENR_F", "TOT_ENR_X"]}
GRADES = ["KG"] + [f"G{g:02d}" for g in range(1, 13)]
HS = {"G09", "G10", "G11", "G12"}
GRADE_COLS = ([f"SCH_GRADE_{g}" for g in GRADES]
              + ["SCH_GRADE_UG", "SCH_UGDETAIL_ES", "SCH_UGDETAIL_MS",
                 "SCH_UGDETAIL_HS"])
KEYS = ["LEA_STATE", "LEAID", "SCHID", "JJ"]


def _num(v):
    """int count or reserve code; None for a blank or non-numeric cell"""
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _key(row) -> tuple[str, str]:
    leaid = row["LEAID"].strip().zfill(7)
    schid = row["SCHID"].strip().split(".")[0].zfill(5)
    return leaid, leaid + schid


def _read(rel: str, want: list[str]) -> tuple[dict, int]:
    """{combokey: {col: raw}} for the wanted columns of one CRDC file"""
    path = os.path.join(DATA, rel)
    out, n = {}, 0

    def rows():
        if rel.lower().endswith(".xlsx"):
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True)
            for r in wb[wb.sheetnames[0]].iter_rows(values_only=True):
                yield ["" if c is None else str(c) for c in r]
            wb.close()
        else:
            with open(path, encoding="latin-1", newline="") as fh:
                yield from csv.reader(fh)

    it = rows()
    hdr = [c.strip().strip('"').lstrip("﻿").lstrip("ï»¿")
           for c in next(it)]
    miss = [c for c in want if c not in hdr]
    if miss:
        raise SystemExit(f"{rel}: missing columns {miss}")
    idx = {c: hdr.index(c) for c in set(want) | set(KEYS)}
    for r in it:
        if len(r) < len(hdr):
            continue
        row = {c: r[i].strip() for c, i in idx.items()}
        leaid, combo = _key(row)
        if not (leaid.isdigit() and len(leaid) == 7):
            continue
        row["leaid"], row["combokey"] = leaid, combo
        out[combo] = row
        n += 1
    return out, n


def _files(cycle: str) -> dict[str, str]:
    """file stem -> path relative to DATA"""
    if cycle == "2015-16":
        return {"*": W1516}
    stems = {s for s, _ in SUBJECTS[cycle].values()}
    stems |= {"Enrollment", "School Characteristics"}
    if cycle == "2013-14":
        return {s: D1314 + X1314[s] + ".xlsx" for s in stems}
    base = D1718 if cycle == "2017-18" else D2122
    return {s: base + s + ".csv" for s in stems}


def _load_cycle(cycle: str):
    """(school attribute rows, course rows, [(rel, n_rows)])"""
    spec = SUBJECTS[cycle]
    files = _files(cycle)
    need: dict[str, list[str]] = {}
    for stem, cols in spec.values():
        need.setdefault(stem, []).extend(cols)
    need.setdefault("Enrollment", []).extend(ENR_COLS[cycle])
    need.setdefault("School Characteristics", []).extend(GRADE_COLS)

    tables, used = {}, []
    if "*" in files:
        allcols = sorted({c for cols in need.values() for c in cols})
        t, n = _read(files["*"], allcols)
        tables = {stem: t for stem in need}
        used.append((files["*"], n))
    else:
        for stem, cols in need.items():
            tables[stem], n = _read(files[stem], sorted(set(cols)))
            used.append((files[stem], n))

    attrs, courses = [], []
    for combo, ch in tables["School Characteristics"].items():
        flags = {g: ch[f"SCH_GRADE_{g}"].lower() == "yes" for g in GRADES}
        n_k12 = sum(flags.values())
        n_hs = sum(flags[g] for g in HS)
        n_ms = int(flags["G07"]) + int(flags["G08"])    # grades 7 and 8
        if n_k12 == 0 and ch["SCH_GRADE_UG"].lower() == "yes":
            det = [ch[f"SCH_UGDETAIL_{k}"].lower() == "yes"
                   for k in ("ES", "MS", "HS")]
            n_k12, n_hs, n_ms = sum(det), int(det[2]), int(det[1])
        er = tables["Enrollment"].get(combo)
        vals = [_num(er[c]) for c in ENR_COLS[cycle]] if er else []
        good = [v for v in vals if v is not None and v >= 0]
        enr = sum(good) if good else None
        hs_est = (enr * n_hs / n_k12
                  if enr is not None and n_k12 > 0 else None)
        ms_est = (enr * n_ms / n_k12
                  if enr is not None and n_k12 > 0 else None)
        attrs.append((cycle, combo, ch["leaid"], ch["LEA_STATE"],
                      ch["JJ"], enr, n_k12, n_hs, n_hs > 0, hs_est,
                      n_ms, ms_est))
        for subj, (stem, cols) in spec.items():
            r = tables[stem].get(combo)
            if r is None:
                continue
            vals = [_num(r[c]) for c in cols]
            good = [v for v in vals if v is not None and v >= 0]
            codes = [v for v in vals if v is not None and v < 0]
            blank = any(v is None for v in vals)
            e = sum(good) if good else None
            rc = min(codes) if codes else (-99 if blank else None)
            courses.append((cycle, combo, ch["leaid"], subj, e, rc))
    return attrs, courses, used


def _copy(cur, table: str, cols: str, rows) -> None:
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in rows:
        w.writerow(["\\N" if v is None else v for v in r])
    buf.seek(0)
    cur.copy_expert(
        f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
        buf)


DDL = """
DROP VIEW  IF EXISTS mart.course_poverty;
DROP TABLE IF EXISTS core.crdc_course_district;
DROP TABLE IF EXISTS core.crdc_course_district_frame;
DROP TABLE IF EXISTS stg.crdc_course_school;
DROP TABLE IF EXISTS stg.crdc_course_school_attr;

CREATE TABLE stg.crdc_course_school_attr (
    cycle      text NOT NULL,
    combokey   text NOT NULL,
    leaid      text NOT NULL,
    state_pc   text,
    jj         text,
    enr_total  double precision,
    n_k12      smallint,
    n_hs       smallint,
    serves_hs  boolean,
    hs_enr_est double precision,
    n_ms       smallint,
    ms_enr_est double precision,
    PRIMARY KEY (cycle, combokey));

CREATE TABLE stg.crdc_course_school (
    cycle    text NOT NULL,
    combokey text NOT NULL,
    leaid    text NOT NULL,
    subject  text NOT NULL,
    enr      double precision,
    rc       smallint,
    PRIMARY KEY (cycle, combokey, subject));
"""

DERIVE = """
CREATE INDEX ON stg.crdc_course_school (cycle, leaid, subject);
CREATE INDEX ON stg.crdc_course_school_attr (cycle, leaid);

COMMENT ON TABLE stg.crdc_course_school IS
'CRDC school-level course enrollment, one row per school x subject, three
 universe cycles. enr is the sum of the component count columns (NULL
 when no component is a count); rc is the most negative reserve code
 among the components (-99 marks a blank cell). rc = -9 with enr NULL is
 skip logic: no high-school grades, or zero classes in the subject.
 Loaded by code/ingest/crdc_courses.py.';

CREATE TABLE core.crdc_course_district_frame AS
SELECT cycle, leaid,
       min(state_pc)                       AS state_pc,
       count(*)                            AS n_schools,
       count(*) FILTER (WHERE serves_hs)   AS n_hs_schools,
       sum(enr_total)                      AS enr_total,
       sum(hs_enr_est)                     AS hs_enr_est,
       sum(ms_enr_est)                     AS ms_enr_est
FROM stg.crdc_course_school_attr
GROUP BY cycle, leaid;
ALTER TABLE core.crdc_course_district_frame ADD PRIMARY KEY (cycle, leaid);

CREATE TABLE core.crdc_course_district AS
SELECT cycle, leaid, subject,
       sum(enr)                                              AS enrollees,
       count(enr)                                            AS n_reported,
       count(*) FILTER (WHERE enr IS NULL AND rc = -9)       AS n_skip,
       count(*) FILTER (WHERE enr IS NULL
                          AND rc IS DISTINCT FROM -9)        AS n_missing
FROM stg.crdc_course_school
GROUP BY cycle, leaid, subject;
ALTER TABLE core.crdc_course_district
    ADD PRIMARY KEY (cycle, leaid, subject);

-- District x subject on the SAIPE poverty axis. Frame: districts with at
-- least one school serving high-school grades. Within the frame a
-- district whose schools all skip a subject holds zero enrollees.
CREATE VIEW mart.course_poverty AS
SELECT f.cycle,
       y.saipe_vintage                    AS vintage,
       f.leaid,
       f.state_pc,
       s.name,
       s.pop_5_17,
       s.pov_5_17,
       CASE WHEN s.pop_5_17 > 0 THEN s.pov_5_17 / s.pop_5_17 END AS pov_rate,
       f.hs_enr_est,
       f.ms_enr_est,
       f.n_hs_schools,
       c.subject,
       coalesce(c.enrollees, 0)           AS enrollees,
       c.n_reported,
       c.n_missing
FROM core.crdc_course_district_frame f
JOIN core.crdc_course_district c ON c.cycle = f.cycle AND c.leaid = f.leaid
JOIN core.dim_year y  ON y.school_year = f.cycle
JOIN stg.saipe_sd s   ON s.leaid = f.leaid AND s.vintage = y.saipe_vintage
WHERE f.n_hs_schools > 0;
"""


def main() -> int:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(DDL)
        used_all = []
        for cycle in SUBJECTS:
            attrs, courses, used = _load_cycle(cycle)
            _copy(cur, "stg.crdc_course_school_attr",
                  "cycle,combokey,leaid,state_pc,jj,enr_total,n_k12,n_hs,"
                  "serves_hs,hs_enr_est,n_ms,ms_enr_est", attrs)
            _copy(cur, "stg.crdc_course_school",
                  "cycle,combokey,leaid,subject,enr,rc", courses)
            used_all += [(cycle, rel, n) for rel, n in used]
            print(f"  {cycle}: {len(attrs):,} schools, "
                  f"{len(courses):,} school x subject rows", flush=True)
        cur.execute(DERIVE)
        for cycle, rel, n in used_all:
            h = hashlib.sha256()
            with open(os.path.join(DATA, rel), "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 22), b""):
                    h.update(chunk)
            cur.execute("""
                INSERT INTO core.source_file (dataset, vintage, rel_path,
                                              sha256, bytes, source_url,
                                              n_rows)
                VALUES ('crdc_courses', %s, %s, %s, %s,
                        'https://civilrightsdata.ed.gov/data', %s)
                ON CONFLICT (dataset, vintage, rel_path) DO UPDATE
                   SET sha256 = EXCLUDED.sha256, bytes = EXCLUDED.bytes,
                       n_rows = EXCLUDED.n_rows, loaded_at = now()""",
                (cycle, "CRDC/" + rel, h.hexdigest(),
                 os.path.getsize(os.path.join(DATA, rel)), n))

        # reconciliation against the existing Algebra II tables
        cur.execute("""
            SELECT n.cycle, count(*) AS districts,
                   sum(n.enrollees) AS new_total,
                   sum(o.alg2_enrollees) AS old_total,
                   count(*) FILTER (WHERE n.enrollees IS DISTINCT FROM
                                          o.alg2_enrollees) AS n_diff
            FROM core.crdc_course_district n
            JOIN core.crdc_district_panel o
              ON o.cycle = n.cycle AND o.leaid = n.leaid
            WHERE n.subject = 'alg2'
            GROUP BY n.cycle ORDER BY n.cycle""")
        print("\n  Algebra II reconciliation vs core.crdc_district_panel")
        for r in cur.fetchall():
            print("   ", r)
        cur.execute("""
            SELECT cycle, subject, round(sum(enrollees)::numeric) AS total,
                   sum(n_reported) AS schools_reported,
                   sum(n_missing) AS schools_missing
            FROM core.crdc_course_district
            GROUP BY cycle, subject ORDER BY subject, cycle""")
        print("\n  national totals")
        for r in cur.fetchall():
            print("   ", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
