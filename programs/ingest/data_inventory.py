"""Inventory of the public data held in the project database (GATEWAY).

WHAT IT COMPUTES. The data appendix of the manuscript (Appendix C) states
the size of every public source as loaded, and the quantities behind its
account of the source-data flaws. The loaders print those counts on the
console and write them to no file. This program recomputes them from the
tables and writes one statistics file, which macros/m_data.py reads:

  tables                 rows of each loaded table (SAIPE, the CRDC school
                         panel and its district aggregation, the CRDC
                         course families, EDGE geocodes, the Opportunity
                         Atlas by tract and by ZCTA, the two relationship
                         tables), with the cycles or vintages they hold
  crdc_alg2_by_cycle     the Algebra II item of the five-cycle school
                         panel: schools, districts, schools with a count,
                         schools with the skip code, enrollees, and the
                         universe flag that the loader stored
  reporting_rate         schools with an Algebra II count per district:
                         the earliest cycle against the later cycles
  alg2_skip_code         schools per cycle whose Algebra II item holds the
                         skip code, and the share of schools with a count
  universe_flag          the loader's universe flag beside the number of
                         schools of each cycle
  alg2_count_schools     schools of the primary cycle that hold an
                         Algebra II count: every school of the file, and
                         the schools with a numeric district identifier
  frame_mismatch         districts of the primary cycle with more
                         Algebra II enrollees than children aged 5 to 17,
                         and the unweighted slope with all districts,
                         without those districts, and above the floor of
                         analysis/algebra2_robust.py
  course_frames          the district frames of the course-family
                         comparison (paper0/course_gradient_figure.py) and
                         the two groups of districts outside the
                         Algebra II frame

HOW TO RUN (from programs/):

    python ingest/data_inventory.py

Output: figures/ingest/data_inventory_stats.json

The database holds public data only (CRDC, SAIPE, EDGE, Opportunity Atlas,
Census and NCES relationship files). The program reads it through
gateway/db.py in a read-only session and issues SELECT statements only.
Plain Python and SQL; no dataframes.

WHAT IT CANNOT COMPUTE. The stored school key of the 2015-16 wide file is
in no table (ingest/crdc_panel.py rebuilds the key before loading), so the
schools that share a stored key, the number of schools of that file, and
the enrollment that survives under the stored key are outside this
program. The number of Algebra II classes of a school is in no table
either, so the program counts the schools with an Algebra II enrollment
count and leaves the comparison with the class item to the loader
(ingest/crdc_courses.py).
"""
import json
import sys
from math import fsum
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gateway import db  # noqa: E402

OUT = HERE.parent / "figures" / "ingest" / "data_inventory_stats.json"

# CRDC cycles of the five-cycle school panel (ingest/crdc_panel.py, SPEC)
CYCLES = ("2011-12", "2013-14", "2015-16", "2017-18", "2021-22")
EARLIEST = "2011-12"          # the cycle that marks missing values with blanks
DAMAGED_KEY_CYCLE = "2015-16"  # the wide file with the damaged stored key
PRIMARY = "2017-18"           # the cycle of the district analyses
# cycles of the course-family table (ingest/crdc_courses.py, SUBJECTS)
COURSE_CYCLES = ("2013-14", "2015-16", "2017-18", "2021-22")
# cycles of the EDGE geocode table (ingest/edge_schools.py, CYCLES)
EDGE_CYCLES = ("2017-18", "2021-22")
# cycles of the course-family comparison (paper0/course_gradient_figure.py)
FRAME_CYCLES = ("2015-16", "2017-18", "2021-22")

SKIP_CODE = -9                # CRDC reserve code: not applicable, skipped
ROUND_SKIP_COUNT_TO = 1000    # the text gives the count to the thousand
MIN_POP = 200                 # children aged 5 to 17: the floor of
                              # analysis/algebra2_robust.py (MIN_POP)
RATIO_LIMIT = 1.0             # more Algebra II enrollees than children
# the nine core high-school courses (paper0/course_gradient_figure.py,
# HS_CORE)
HS_CORE = ("alg1_g0910", "alg1_g1112", "geometry", "alg2", "adv_math",
           "calculus", "biology", "chemistry", "physics")
ALG2 = "alg2"                 # key of Algebra II in the course tables
# a district identifier that joins SAIPE: seven digits
NUMERIC_LEAID = "^[0-9]{7}$"

# columns this program reads; checked against information_schema.columns
COLUMNS = {
    "stg.saipe_sd": ["vintage", "leaid", "pop_5_17"],
    "stg.crdc_alg2_panel": ["cycle", "leaid", "combokey", "alg2_tot",
                            "alg2_m_rc", "alg2_f_rc", "is_universe"],
    "core.crdc_district_panel": ["cycle", "leaid", "n_schools",
                                 "n_alg2_reported"],
    "stg.crdc_school": ["cycle", "leaid", "combokey", "alg2_tot"],
    "stg.crdc_course_school": ["cycle", "combokey", "subject", "enr", "rc"],
    "raw_xwalk.edge_school": ["cycle", "ncessch"],
    "context_tract.oa_tract": ["geoid_2010", "tract_vintage"],
    "context_zcta.oa_zcta": ["zcta5", "tract_vintage"],
    "raw_xwalk.zcta_tract_frac": ["zcta5", "geoid_2010", "weight"],
    "raw_xwalk.lea_tract_frac": ["leaid", "geoid_2010", "share"],
    "core.dim_year": ["school_year", "saipe_vintage", "note"],
    "mart.alg2_panel": ["cycle", "leaid", "pop_5_17", "pov_rate",
                        "alg2_per_child"],
    "mart.course_poverty": ["cycle", "leaid", "pop_5_17", "pov_rate",
                            "subject", "enrollees", "n_reported",
                            "n_missing"],
}


def num(v):
    """a database number as int when it is whole, else float"""
    v = float(v)
    return int(v) if v.is_integer() else v


def one(cur, sql, params=()):
    """the single row of a query"""
    cur.execute(sql, params)
    rows = cur.fetchall()
    assert len(rows) == 1, (sql, len(rows))
    return rows[0]


def check_columns(cur):
    """every table and column this program reads exists"""
    for name, cols in COLUMNS.items():
        schema, table = name.split(".")
        cur.execute("select column_name from information_schema.columns "
                    "where table_schema = %s and table_name = %s",
                    (schema, table))
        have = {r[0] for r in cur.fetchall()}
        assert have, f"{name} does not exist"
        missing = [c for c in cols if c not in have]
        assert not missing, f"{name} lacks {missing}"


def by_cycle(cur, table, key):
    """{cycle: (rows, distinct keys)} of a table with a cycle column"""
    cur.execute(f"select cycle, count(*), count(distinct {key}) "
                f"from {table} group by cycle order by cycle")
    return {c: (int(n), int(k)) for c, n, k in cur.fetchall()}


def tables(cur) -> dict:
    """rows of each loaded table, with what the rows are"""
    out = {}

    n, nv, v0, v1 = one(cur, "select count(*), count(distinct vintage), "
                             "min(vintage), max(vintage) from stg.saipe_sd")
    assert n > 0 and nv > 0
    out["saipe_district_year"] = {
        "table": "stg.saipe_sd", "unit": "district by vintage",
        "n_rows": int(n), "n_vintages": int(nv),
        "first_vintage": int(v0), "last_vintage": int(v1)}

    panel = by_cycle(cur, "stg.crdc_alg2_panel", "combokey")
    assert tuple(panel) == CYCLES, sorted(panel)
    # one row per school and cycle
    assert all(rows == schools for rows, schools in panel.values())
    out["crdc_school_cycle"] = {
        "table": "stg.crdc_alg2_panel", "unit": "school by cycle",
        "n_rows": sum(rows for rows, _ in panel.values()),
        "n_cycles": len(panel), "cycles": list(panel)}

    dist = by_cycle(cur, "core.crdc_district_panel", "leaid")
    assert tuple(dist) == CYCLES, sorted(dist)
    assert all(rows == leas for rows, leas in dist.values())
    out["crdc_district_cycle"] = {
        "table": "core.crdc_district_panel", "unit": "district by cycle",
        "n_rows": sum(rows for rows, _ in dist.values())}

    cur.execute("select cycle, count(*), count(distinct combokey), "
                "count(distinct subject) from stg.crdc_course_school "
                "group by cycle order by cycle")
    course = {c: {"n_rows": int(n), "n_schools": int(s),
                  "n_course_families": int(f)}
              for c, n, s, f in cur.fetchall()}
    assert tuple(course) == COURSE_CYCLES, sorted(course)
    # every school of a cycle holds one row per course family of the cycle
    for c, r in course.items():
        assert r["n_rows"] == r["n_schools"] * r["n_course_families"], c
    out["crdc_course_school"] = {
        "table": "stg.crdc_course_school",
        "unit": "school by cycle by course family",
        "n_rows": sum(r["n_rows"] for r in course.values()),
        "by_cycle": course}

    edge = by_cycle(cur, "raw_xwalk.edge_school", "ncessch")
    assert tuple(edge) == EDGE_CYCLES, sorted(edge)
    assert all(rows == schools for rows, schools in edge.values())
    out["edge_school_cycle"] = {
        "table": "raw_xwalk.edge_school", "unit": "school by cycle",
        "n_rows": sum(rows for rows, _ in edge.values()),
        "by_cycle": {c: rows for c, (rows, _) in edge.items()}}

    for key, table, col, unit in (
            ("opportunity_atlas_tract", "context_tract.oa_tract",
             "geoid_2010", "census tract"),
            ("opportunity_atlas_zcta", "context_zcta.oa_zcta",
             "zcta5", "ZCTA")):
        n, k = one(cur, f"select count(*), count(distinct {col}) "
                        f"from {table}")
        assert n > 0 and n == k, table
        cur.execute(f"select distinct tract_vintage from {table} "
                    "order by 1")
        out[key] = {"table": table, "unit": unit, "n_rows": int(n),
                    "tract_vintages": [r[0] for r in cur.fetchall()]}

    for key, table, col, name, unit in (
            ("zcta_tract_weights", "raw_xwalk.zcta_tract_frac",
             "zcta5", "n_zctas", "ZCTA by tract"),
            ("district_tract_shares", "raw_xwalk.lea_tract_frac",
             "leaid", "n_districts", "district by tract")):
        n, na, nb = one(cur, f"select count(*), count(distinct {col}), "
                             f"count(distinct geoid_2010) from {table}")
        assert n > 0, table
        out[key] = {"table": table, "unit": unit, "n_rows": int(n),
                    name: int(na), "n_tracts": int(nb)}
    return out


def crdc_alg2_by_cycle(cur) -> dict:
    """the Algebra II item of the five-cycle school panel, by cycle

    A school holds a count when its male or its female total is a count
    (the loader sets the sum to NULL when both are missing). A school
    holds the skip code when either column holds it; the number of cells
    counts the two columns apart.
    """
    cur.execute("""
        select cycle, count(*), count(distinct leaid), count(alg2_tot),
               count(*) filter (where alg2_tot = 0),
               sum(alg2_tot),
               count(*) filter (where alg2_m_rc = %(skip)s
                                   or alg2_f_rc = %(skip)s),
               count(*) filter (where alg2_m_rc = %(skip)s)
                 + count(*) filter (where alg2_f_rc = %(skip)s),
               count(*) filter (where alg2_m_rc <> %(skip)s
                                   or alg2_f_rc <> %(skip)s),
               count(*) filter (where alg2_tot is null
                                  and alg2_m_rc is null
                                  and alg2_f_rc is null),
               bool_and(is_universe), bool_or(is_universe)
        from stg.crdc_alg2_panel group by cycle order by cycle""",
                {"skip": SKIP_CODE})
    rows = cur.fetchall()
    cur.execute("select cycle, count(*), sum(n_schools), "
                "sum(n_alg2_reported) from core.crdc_district_panel "
                "group by cycle")
    agg = {c: (int(d), int(s), int(r)) for c, d, s, r in cur.fetchall()}
    cur.execute("select school_year, saipe_vintage, note from core.dim_year")
    year = {c: (v, note) for c, v, note in cur.fetchall()}
    out = {}
    for (cycle, n, nd, ncount, nzero, enr, nskip, ncells, nother, nblank,
         all_universe, any_universe) in rows:
        # the flag is constant within a cycle
        assert all_universe == any_universe, cycle
        # the district aggregation holds the same schools and districts
        assert agg[cycle] == (nd, n, ncount), (cycle, agg[cycle])
        assert cycle in year, f"{cycle} is not in core.dim_year"
        out[cycle] = {
            "n_schools": int(n),
            "n_districts": int(nd),
            "n_schools_alg2_count": int(ncount),
            "n_schools_alg2_zero": int(nzero),
            "alg2_enrollees": num(enr),
            "n_schools_skip_code": int(nskip),
            "n_cells_skip_code": int(ncells),
            "n_schools_other_code": int(nother),
            "n_schools_blank": int(nblank),
            "pct_schools_alg2_count": 100.0 * ncount / n,
            "alg2_count_schools_per_district": ncount / nd,
            "loader_flag_is_universe": bool(all_universe),
            "saipe_vintage": int(year[cycle][0]),
            "dim_year_note": year[cycle][1],
        }
    assert tuple(out) == CYCLES, sorted(out)
    return out


def reporting_rate(cyc: dict) -> dict:
    """schools with an Algebra II count per district: the earliest cycle
    against the later cycles"""
    rate = {c: r["alg2_count_schools_per_district"] for c, r in cyc.items()}
    later = [c for c in CYCLES if c != EARLIEST]
    mean = fsum(rate[c] for c in later) / len(later)
    lo, hi = min(rate[c] for c in later), max(rate[c] for c in later)
    return {
        "definition": "schools with an Algebra II count divided by the "
                      "districts of the cycle",
        "earliest_cycle": EARLIEST, "later_cycles": later,
        "rate_earliest": rate[EARLIEST],
        "rate_later_mean": mean, "rate_later_min": lo, "rate_later_max": hi,
        # excess of the earliest cycle over the mean of the later cycles
        "pct_excess_over_later_mean": 100.0 * (rate[EARLIEST] / mean - 1),
        # and over the single later cycle with the highest and lowest rate
        "pct_excess_smallest": 100.0 * (rate[EARLIEST] / hi - 1),
        "pct_excess_largest": 100.0 * (rate[EARLIEST] / lo - 1),
    }


def alg2_skip_code(cyc: dict) -> dict:
    """schools per cycle with the skip code in the Algebra II item, over
    the cycles that use reserve codes"""
    coded = [c for c in CYCLES if cyc[c]["n_schools_skip_code"] > 0]
    # the earliest cycle marks missing values with blanks
    assert cyc[EARLIEST]["n_schools_skip_code"] == 0
    assert cyc[EARLIEST]["n_schools_other_code"] == 0
    assert coded == [c for c in CYCLES if c != EARLIEST], coded
    # in the cycles with codes no missing value is a blank
    assert all(cyc[c]["n_schools_blank"] == 0 for c in coded)
    mean = fsum(cyc[c]["n_schools_skip_code"] for c in coded) / len(coded)
    cells = fsum(cyc[c]["n_cells_skip_code"] for c in coded) / len(coded)
    share = [cyc[c]["pct_schools_alg2_count"] for c in coded]
    return {
        "code": SKIP_CODE, "cycles_with_reserve_codes": coded,
        "n_schools_mean": mean,
        "rounding_unit": ROUND_SKIP_COUNT_TO,
        "n_schools_mean_rounded":
            ROUND_SKIP_COUNT_TO * round(mean / ROUND_SKIP_COUNT_TO),
        "n_schools_min": min(cyc[c]["n_schools_skip_code"] for c in coded),
        "n_schools_max": max(cyc[c]["n_schools_skip_code"] for c in coded),
        # the male and the female column each hold the code
        "n_cells_mean": cells,
        "pct_schools_alg2_count_mean": fsum(share) / len(share),
        "pct_schools_alg2_count_min": min(share),
        "pct_schools_alg2_count_max": max(share),
    }


def universe_flag(cyc: dict) -> dict:
    """the universe flag of ingest/crdc_panel.py beside the size of each
    cycle. A sampled cycle would hold far fewer schools and districts
    than a universe cycle."""
    sample = [c for c in CYCLES if not cyc[c]["loader_flag_is_universe"]]
    univ = [c for c in CYCLES if cyc[c]["loader_flag_is_universe"]]
    assert univ, "no cycle is flagged as a universe"
    ref = univ[0]
    return {
        "cycles_flagged_sample_by_loader": sample,
        "cycles_flagged_universe_by_loader": univ,
        "reference_cycle": ref,
        "n_schools": {c: cyc[c]["n_schools"] for c in CYCLES},
        "n_districts": {c: cyc[c]["n_districts"] for c in CYCLES},
        "pct_of_reference_schools": {
            c: 100.0 * cyc[c]["n_schools"] / cyc[ref]["n_schools"]
            for c in sample},
        "pct_of_reference_districts": {
            c: 100.0 * cyc[c]["n_districts"] / cyc[ref]["n_districts"]
            for c in sample},
        "dim_year_note": {c: cyc[c]["dim_year_note"] for c in CYCLES},
    }


def alg2_count_schools(cur, cyc: dict) -> dict:
    """schools of the primary cycle that hold an Algebra II count

    stg.crdc_school (ingest/crdc.py) holds every school of the public-use
    file. The five-cycle panel and the course-family table keep the
    schools whose district identifier is seven digits, the form that
    joins SAIPE. The two counts of the text are this one quantity on the
    two populations.
    """
    cur.execute("""
        select (leaid ~ %s) as numeric_id, count(*), count(alg2_tot),
               count(*) filter (where alg2_tot >= 0),
               count(distinct leaid)
        from stg.crdc_school where cycle = %s group by 1""",
                (NUMERIC_LEAID, PRIMARY))
    got = {bool(k): (int(n), int(c), int(nn), int(d))
           for k, n, c, nn, d in cur.fetchall()}
    assert True in got, f"stg.crdc_school holds no school of {PRIMARY}"
    other = got.get(False, (0, 0, 0, 0))
    numeric = got[True]
    # a count is never negative (reserve codes are stored apart)
    assert numeric[1] == numeric[2] and other[1] == other[2]

    # the schools with a numeric identifier are the schools of the panel,
    # with the same Algebra II value
    only_school, only_panel, differ = one(cur, """
        select count(*) filter (where p.combokey is null),
               count(*) filter (where s.combokey is null),
               count(*) filter (where p.combokey is not null
                                  and s.combokey is not null
                                  and p.alg2_tot is distinct from s.alg2_tot)
        from (select combokey, alg2_tot from stg.crdc_school
              where cycle = %s and leaid ~ %s) s
        full join (select combokey, alg2_tot from stg.crdc_alg2_panel
                   where cycle = %s) p on p.combokey = s.combokey""",
                                          (PRIMARY, NUMERIC_LEAID, PRIMARY))
    assert (only_school, only_panel, differ) == (0, 0, 0), (
        only_school, only_panel, differ)
    assert numeric[:2] == (cyc[PRIMARY]["n_schools"],
                           cyc[PRIMARY]["n_schools_alg2_count"])

    # the course-family table: a count, or the skip code without a count
    n, ncount, nskip = one(cur, """
        select count(*), count(*) filter (where enr >= 0),
               count(*) filter (where enr is null and rc = %s)
        from stg.crdc_course_school where cycle = %s and subject = %s""",
                           (SKIP_CODE, PRIMARY, ALG2))
    assert (n, ncount) == numeric[:2], (n, ncount, numeric)
    return {
        "cycle": PRIMARY,
        "definition": "schools whose Algebra II enrollment is a count "
                      "(non-negative)",
        "all_schools": {
            "table": "stg.crdc_school",
            "n_schools": numeric[0] + other[0],
            "n_schools_alg2_count": numeric[1] + other[1]},
        "numeric_district_id": {
            "table": "stg.crdc_alg2_panel, stg.crdc_course_school",
            "n_schools": numeric[0], "n_districts": numeric[3],
            "n_schools_alg2_count": numeric[1],
            "n_schools_alg2_skip_code": int(nskip)},
        "other_district_id": {
            "n_schools": other[0], "n_districts": other[3],
            "n_schools_alg2_count": other[1]},
    }


def slope(rows, weighted: bool) -> float:
    """least-squares slope of y on x over rows (x, y, weight)"""
    w = [r[2] if weighted else 1.0 for r in rows]
    sw = fsum(w)
    mx = fsum(wi * r[0] for wi, r in zip(w, rows)) / sw
    my = fsum(wi * r[1] for wi, r in zip(w, rows)) / sw
    sxy = fsum(wi * (r[0] - mx) * (r[1] - my) for wi, r in zip(w, rows))
    sxx = fsum(wi * (r[0] - mx) ** 2 for wi, r in zip(w, rows))
    return sxy / sxx


def median(values) -> float:
    v = sorted(values)
    assert v, "median of nothing"
    h = len(v) // 2
    return v[h] if len(v) % 2 else (v[h - 1] + v[h]) / 2


def frame_mismatch(cur) -> dict:
    """districts with more Algebra II enrollees than children aged 5 to 17

    The districts are those of analysis/algebra2_robust.py (load): the
    rows of mart.alg2_panel with a poverty rate, a positive number of
    children and an Algebra II total. The slope is the least-squares
    slope of Algebra II enrollees per child on the child poverty rate,
    unweighted and weighted by children, on three sets of districts: all;
    all but the districts whose ratio exceeds one; and the districts with
    at least MIN_POP children.
    """
    cur.execute("""
        select pov_rate, alg2_per_child, pop_5_17
        from mart.alg2_panel
        where cycle = %s and alg2_per_child is not null
          and pov_rate is not null and pop_5_17 > 0""", (PRIMARY,))
    rows = [(float(x), float(y), float(w)) for x, y, w in cur.fetchall()]
    assert rows, f"mart.alg2_panel holds no district of {PRIMARY}"
    above = [r for r in rows if r[1] > RATIO_LIMIT]
    assert above, "no district with more enrollees than children"
    sets = {
        "all_districts": rows,
        "without_ratio_above_one": [r for r in rows if r[1] <= RATIO_LIMIT],
        "at_least_min_children": [r for r in rows if r[2] >= MIN_POP],
    }
    out = {
        "cycle": PRIMARY, "min_children": MIN_POP,
        "n_districts": len(rows),
        "ratio_above_one": {
            "n_districts": len(above),
            "children": sorted(num(r[2]) for r in above),
            "median_children": num(median(r[2] for r in above)),
            "max_children": num(max(r[2] for r in above)),
            "max_ratio": max(r[1] for r in above),
            # how many of them the floor on children removes
            "n_below_min_children": sum(r[2] < MIN_POP for r in above),
        },
        "n_districts_below_min_children": sum(r[2] < MIN_POP for r in rows),
        "fits": {},
    }
    for name, sel in sets.items():
        out["fits"][name] = {
            "n_districts": len(sel),
            "max_ratio": max(r[1] for r in sel),
            "slope_unweighted": slope(sel, False),
            "slope_weighted": slope(sel, True),
        }
    return out


def course_frames(cur) -> dict:
    """district frames of the course-family comparison, by cycle

    The districts and the three states of a district follow
    paper0/course_gradient_figure.py (load, figure): districts of
    mart.course_poverty (SAIPE-matched, at least one school serving
    high-school grades) with at least MIN_POP children and a poverty
    rate. A district reports Algebra II when a school holds an Algebra II
    count; its totals are complete when no school holds a missing code
    in any course family; its core enrollment is the sum of enrollees
    over the nine core courses.
    """
    out = {}
    for cycle in FRAME_CYCLES:
        cur.execute("""
            select leaid, pop_5_17, subject, enrollees, n_reported,
                   n_missing
            from mart.course_poverty
            where cycle = %s and pop_5_17 >= %s and pov_rate is not null""",
                    (cycle, MIN_POP))
        d, subjects = {}, set()
        for leaid, pop, subj, enr, nrep, nmiss in cur.fetchall():
            r = d.setdefault(leaid, {"pop": float(pop), "core": 0.0,
                                     "alg2": False, "complete": True,
                                     "n_subjects": 0})
            subjects.add(subj)
            r["n_subjects"] += 1
            if subj in HS_CORE:
                r["core"] += float(enr)
            if subj == ALG2 and nrep and nrep > 0:
                r["alg2"] = True
            if nmiss and nmiss > 0:
                r["complete"] = False
        assert d, f"mart.course_poverty holds no district of {cycle}"
        assert set(HS_CORE) <= subjects, sorted(subjects)
        # every district holds one row per course family
        assert {r["n_subjects"] for r in d.values()} == {len(subjects)}

        def group(test):
            sel = [r for r in d.values() if test(r)]
            return {"n_districts": len(sel),
                    "children": num(fsum(r["pop"] for r in sel))}

        no_core = group(lambda r: r["core"] == 0)
        no_core["n_with_incomplete_total"] = sum(
            r["core"] == 0 and not r["complete"] for r in d.values())
        # no district of the Algebra II frame is without core enrollment
        assert not any(r["alg2"] and r["core"] == 0
                       for r in d.values()), cycle
        no_alg2 = group(lambda r: not r["alg2"] and r["core"] > 0)
        no_alg2["complete_totals"] = group(
            lambda r: not r["alg2"] and r["core"] > 0 and r["complete"])
        out[cycle] = {
            "n_course_families": len(subjects),
            "districts_serving_high_school_grades": group(lambda r: True),
            "alg2_frame": group(lambda r: r["alg2"]),
            "alg2_frame_incomplete_total": group(
                lambda r: r["alg2"] and not r["complete"]),
            "common_frame": group(lambda r: r["alg2"] and r["complete"]),
            "neutral_frame": group(
                lambda r: r["core"] > 0 and r["complete"]),
            # no enrollment in any of the nine core courses
            "no_core_enrollment": no_core,
            # no Algebra II reported, enrollment in other core courses
            "no_alg2_other_core": no_alg2,
        }
    return out


RAW_2015_16 = ("CRDC", "2015-16-crdc-data", "Data Files and Layouts",
               "CRDC 2015-16 School Data.csv")
ALG2_COLUMNS = ("TOT_MATHENR_ALG2_M", "TOT_MATHENR_ALG2_F")


def data_root() -> Path:
    """folder of the raw public files (GATEWAY_DATA, or data/ beside or
    above the programs folder)"""
    import os
    for c in (os.environ.get("GATEWAY_DATA"), HERE.parent.parent / "data",
              HERE.parent.parent.parent / "data"):
        if c and Path(c).exists():
            return Path(c)
    raise FileNotFoundError("raw data folder not found; set GATEWAY_DATA")


def stored_key() -> dict:
    """What the school key does as the 2015-16 wide file stores it (the
    loaders rebuild the key, so no table holds the stored one). Read from
    the raw public file: schools of the file, distinct stored keys, the
    schools lost when one row per stored key is kept, and the Algebra II
    enrollment that survives, among schools with a seven-digit district
    identifier (the population of the loaded panel)."""
    import csv
    import re
    path = data_root().joinpath(*RAW_2015_16)

    def count(s):
        try:
            v = float(s)
        except ValueError:
            return None
        return None if v < 0 else v        # negative values are reserve codes

    n = n7 = 0
    seen, seen7 = set(), set()
    total7 = kept7 = 0.0
    with open(path, encoding="latin-1", newline="") as fh:
        rd = csv.reader(fh)
        head = next(rd)
        ik, il = head.index("COMBOKEY"), head.index("LEAID")
        im, jf = (head.index(c) for c in ALG2_COLUMNS)
        for r in rd:
            n += 1
            key = r[ik].strip()
            seen.add(key)
            if not re.fullmatch(NUMERIC_LEAID.strip("^$"),
                                r[il].strip().zfill(7)):
                continue
            n7 += 1
            m, f = count(r[im]), count(r[jf])
            enr = (m or 0.0) + (f or 0.0)
            total7 += enr
            if key not in seen7:           # the first row of a stored key
                seen7.add(key)
                kept7 += enr
    return {
        "file": "/".join(RAW_2015_16),
        "n_schools": n, "n_distinct_stored_keys": len(seen),
        "n_schools_lost_under_stored_key": n - len(seen),
        "n_schools_numeric_district": n7,
        "alg2_enrollees_rebuilt_key": total7,
        "alg2_enrollees_stored_key": kept7,
        "pct_enrollment_lost": 100.0 * (1.0 - kept7 / total7),
    }


def main() -> int:
    raw_key = stored_key()
    with db.connect() as cn:
        cn.set_session(readonly=True)
        with cn.cursor() as cur:
            check_columns(cur)
            cyc = crdc_alg2_by_cycle(cur)
            out = {
                "program": "ingest/data_inventory.py",
                "parameters": {
                    "cycles": list(CYCLES), "earliest_cycle": EARLIEST,
                    "damaged_key_cycle": DAMAGED_KEY_CYCLE,
                    "primary_cycle": PRIMARY, "skip_code": SKIP_CODE,
                    "min_children": MIN_POP, "ratio_limit": RATIO_LIMIT,
                    "core_courses": list(HS_CORE)},
                "tables": tables(cur),
                "crdc_alg2_by_cycle": cyc,
                "reporting_rate": reporting_rate(cyc),
                "alg2_skip_code": alg2_skip_code(cyc),
                "universe_flag": universe_flag(cyc),
                "alg2_count_schools": alg2_count_schools(cur, cyc),
                "frame_mismatch": frame_mismatch(cur),
                "course_frames": course_frames(cur),
                "stored_key_2015_16": raw_key,
            }
    # the raw file and the loaded panel agree on the schools of the cycle
    assert (raw_key["n_schools_numeric_district"]
            == cyc[DAMAGED_KEY_CYCLE]["n_schools"])
    # the school panel and its district aggregation agree on the cycles
    assert (out["tables"]["crdc_school_cycle"]["n_rows"]
            == sum(r["n_schools"] for r in cyc.values()))
    assert (out["tables"]["crdc_district_cycle"]["n_rows"]
            == sum(r["n_districts"] for r in cyc.values()))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")

    print(f"wrote {OUT}")
    for r in out["tables"].values():
        print(f"  {r['table']:28s} {r['n_rows']:>10,} rows  ({r['unit']})")
    rr, sk = out["reporting_rate"], out["alg2_skip_code"]
    print(f"  Algebra II count schools per district: {EARLIEST} "
          f"{rr['rate_earliest']:.3f}, later cycles "
          f"{rr['rate_later_min']:.3f} to {rr['rate_later_max']:.3f} "
          f"({rr['pct_excess_over_later_mean']:+.1f}% over their mean)")
    print(f"  schools with code {SKIP_CODE}, mean of "
          f"{len(sk['cycles_with_reserve_codes'])} cycles: "
          f"{sk['n_schools_mean']:,.0f}; schools with a count: "
          f"{sk['pct_schools_alg2_count_mean']:.1f}%")
    a = out["alg2_count_schools"]
    print(f"  {PRIMARY} schools with an Algebra II count: "
          f"{a['all_schools']['n_schools_alg2_count']:,} of "
          f"{a['all_schools']['n_schools']:,} in the file, "
          f"{a['numeric_district_id']['n_schools_alg2_count']:,} of "
          f"{a['numeric_district_id']['n_schools']:,} with a numeric "
          f"district identifier")
    m = out["frame_mismatch"]
    print(f"  {PRIMARY} districts with ratio above one: "
          f"{m['ratio_above_one']['n_districts']} of {m['n_districts']:,}, "
          f"median {m['ratio_above_one']['median_children']} children")
    for name, f in m["fits"].items():
        print(f"    {name:26s} n={f['n_districts']:>6,}  unweighted "
              f"{f['slope_unweighted']:+.4f}  weighted "
              f"{f['slope_weighted']:+.4f}")
    c = out["course_frames"][PRIMARY]
    print(f"  {PRIMARY} no core enrollment: "
          f"{c['no_core_enrollment']['n_districts']} districts, "
          f"{c['no_core_enrollment']['children']:,} children; no Algebra II "
          f"with other core courses: "
          f"{c['no_alg2_other_core']['n_districts']} districts, "
          f"{c['no_alg2_other_core']['children']:,} children")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
