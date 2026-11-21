"""
Assemble the student-level analysis table: UTSA student -> district -> context.

This is the join everything else was built for. One row per student, carrying:

  the EXACT branch      high school -> NCES -> LEAID -> SAIPE poverty
  the ECOLOGICAL branch home ZIP -> ZCTA -> OA (aggregated to ZCTA, report 009 §7)
  the proxy gate        home-to-school distance, for the <=10 mile rule (005/008)
  the running variable  inferred high-school entry year, for the HB5 split (004)

GOVERNANCE
  IRB approval and a data-use agreement are in place (confirmed 2026-08-08).
  Even so, `IDENTIFIER` is replaced by a SALTED HASH before it crosses servers.
  `dbo.OIR` carries AGI, ZIPCODE and HIGHSCHOOLNAME together, which are
  re-identifying in combination for small high schools; the surrogate key means
  the analysis table cannot be joined back to a person without the salt, which
  never leaves `code/env/secrets.env`.
  AGI is banded, not carried as a value, for the same reason.

INFERRED HIGH-SCHOOL ENTRY YEAR -- the one derived variable here, and the one to
treat carefully. FIRSTTERMCODE gives university entry (YEAR.66 = Fall). A
standard-path student entered high school four years earlier, so
    hs_entry_year = floor(FIRSTTERMCODE) - 4
HB5's Foundation plan was the DEFAULT for students entering high school in
2014-15, so `hb5_default = hs_entry_year >= 2014`. This is an INFERENCE, not an
observed field: transfer students, delayed entrants and early graduates all
break it, and report 004 §3 says so. It is stored with a flag so an analysis can
restrict to first-time entrants where the mapping is most defensible.
"""

from __future__ import annotations

import hashlib
import io
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402
from gateway import paths  # noqa: E402

SQL = """
SELECT  IDENTIFIER,
        MIN(FIRSTTERMCODE)                                  AS first_term,
        MIN(STUDENTTYPE)                                    AS student_type,
        MIN(ETHNICITY)                                      AS ethnicity,
        MIN(GENDER)                                         AS gender,
        MIN(PELLSTATUS)                                     AS pell,
        MIN(FIRSTGENERATIONSTATUS)                          AS first_gen,
        MIN(AGI)                                            AS agi_raw,
        MIN(RIGHT('00000'+LTRIM(RTRIM(ZIPCODE)),5))         AS home_zip,
        MIN(LTRIM(RTRIM(HIGHSCHOOLNAME)))                   AS hs_name,
        MIN(LTRIM(RTRIM(HIGHSCHOOLCITY)))                   AS hs_city,
        MIN(LTRIM(RTRIM(HIGHSCHOOLSTATE)))                  AS hs_state
FROM dbo.OIR
GROUP BY IDENTIFIER
"""


def salt() -> str:
    from gateway.db import _load_secrets
    s = _load_secrets().get("PGPASSWORD", "")
    return "gateway-utsa-" + s


def band_agi(v) -> str | None:
    try:
        x = float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None
    for hi, lab in ((0, "0_or_less"), (25_000, "lt25k"), (50_000, "25k_50k"),
                    (75_000, "50k_75k"), (100_000, "75k_100k")):
        if x <= hi:
            return lab
    return "gte100k"


def haversine(lat1, lon1, lat2, lon2):
    R = 3958.7613
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin((p2 - p1) / 2) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(a))


def main() -> int:
    import pyodbc
    cn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};"
                        "SERVER=localhost;DATABASE=UTSA;Trusted_Connection=yes;")
    try:
        s = pd.read_sql(SQL, cn)
    finally:
        cn.close()
    print(f"students: {len(s):,}", flush=True)

    sl = salt().encode()
    s["student_key"] = [hashlib.sha256(sl + str(i).encode()).hexdigest()[:16]
                        for i in s.IDENTIFIER]
    s = s.drop(columns=["IDENTIFIER"])
    s["agi_band"] = s.agi_raw.map(band_agi)
    s = s.drop(columns=["agi_raw"])

    ft = pd.to_numeric(s.first_term, errors="coerce")
    s["univ_entry_year"] = np.floor(ft)
    s["hs_entry_year"] = s.univ_entry_year - 4
    s["hb5_default"] = s.hs_entry_year >= 2014
    s["entry_inference_ok"] = s.student_type.astype(str).str.strip().str.lower().eq("new")

    with db.connect() as c:
        xw = pd.read_sql("SELECT hs_name, hs_city, leaid, ncessch, decision "
                         "FROM core.hs_crosswalk WHERE decision LIKE 'auto%%'", c)
        edge = pd.read_sql("SELECT ncessch, lat AS s_lat, lon AS s_lon, cnty "
                           "FROM raw_xwalk.edge_school WHERE cycle='2017-18'", c)
        zc = pd.read_sql("SELECT zcta5, geoid_2010, county_fips, match_quality "
                         "FROM raw_xwalk.zcta_tract_best", c)
        oa = pd.read_sql("SELECT zcta5, n_tracts, kfr_p25, jail_p25, "
                         "poor_share2010, med_hhinc2016, frac_coll_plus2010 "
                         "FROM context_zcta.oa_zcta", c)

    d = (s.merge(xw, on=["hs_name", "hs_city"], how="left")
           .merge(edge, on="ncessch", how="left")
           .merge(oa, left_on="home_zip", right_on="zcta5", how="left")
           .merge(zc[["zcta5", "county_fips"]], left_on="home_zip",
                  right_on="zcta5", how="left", suffixes=("", "_z")))

    # home ZIP centroid, for the distance gate
    GEO = paths.data_dir("geo")
    g = pd.read_csv(os.path.join(GEO, "Gaz_zcta_national.txt"), sep="\t",
                    dtype={"GEOID": str})
    g.columns = [c.strip() for c in g.columns]
    g["GEOID"] = g["GEOID"].str.strip().str.zfill(5)
    g["h_lat"] = pd.to_numeric(g["INTPTLAT"], errors="coerce")
    g["h_lon"] = pd.to_numeric(g["INTPTLONG"], errors="coerce")
    d = d.merge(g[["GEOID", "h_lat", "h_lon"]], left_on="home_zip",
                right_on="GEOID", how="left")
    d["miles_home_to_school"] = haversine(d.h_lat, d.h_lon, d.s_lat, d.s_lon)
    d["oa_proxy_ok"] = d.miles_home_to_school <= 10          # report 005/008 rule
    d["oa_proxy_strict"] = d.miles_home_to_school <= 5

    # district poverty at the SAIPE vintage nearest the student's HS years
    with db.connect() as c:
        # pov_rate is computed in the mart view, not stored in stg
        sa = pd.read_sql("""
            SELECT leaid, vintage, pop_5_17,
                   CASE WHEN pop_5_17 > 0 THEN pov_5_17 / pop_5_17 END AS pov_rate
            FROM stg.saipe_sd WHERE pop_5_17 > 0""", c)
    d["saipe_vintage"] = d.hs_entry_year.clip(1995, 2024)
    d = d.merge(sa, left_on=["leaid", "saipe_vintage"],
                right_on=["leaid", "vintage"], how="left")

    cols = ["student_key", "univ_entry_year", "hs_entry_year", "hb5_default",
            "entry_inference_ok", "student_type", "ethnicity", "gender", "pell",
            "first_gen", "agi_band", "home_zip", "hs_name", "hs_city", "hs_state",
            "leaid", "ncessch", "decision", "county_fips",
            "miles_home_to_school", "oa_proxy_ok", "oa_proxy_strict",
            "n_tracts", "kfr_p25", "jail_p25", "poor_share2010",
            "med_hhinc2016", "frac_coll_plus2010", "pov_rate", "pop_5_17"]
    out = d[cols].drop_duplicates(subset=["student_key"])

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS mart.utsa_student_context CASCADE")
        cur.execute("""
            CREATE TABLE mart.utsa_student_context (
                student_key text PRIMARY KEY,
                univ_entry_year double precision, hs_entry_year double precision,
                hb5_default boolean, entry_inference_ok boolean,
                student_type text, ethnicity text, gender text, pell text,
                first_gen text, agi_band text,
                home_zip text, hs_name text, hs_city text, hs_state text,
                leaid text, ncessch text, decision text, county_fips text,
                miles_home_to_school double precision,
                oa_proxy_ok boolean, oa_proxy_strict boolean,
                n_tracts double precision, kfr_p25 double precision,
                jail_p25 double precision, poor_share2010 double precision,
                med_hhinc2016 double precision, frac_coll_plus2010 double precision,
                pov_rate double precision, pop_5_17 double precision)""")
        buf = io.StringIO()
        out.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert("COPY mart.utsa_student_context FROM STDIN "
                        "WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("CREATE INDEX ON mart.utsa_student_context (leaid)")
        cur.execute("CREATE INDEX ON mart.utsa_student_context (home_zip)")
        cur.execute("""
            COMMENT ON TABLE mart.utsa_student_context IS
            'One row per UTSA student. student_key is a SALTED HASH -- it cannot
             be joined back to a person without the salt in code/env/secrets.env.
             AGI is banded, not carried. kfr_p25/jail_p25/poor_share2010 are
             ECOLOGICAL, measured at ZIP resolution (see report 009 section 7):
             they describe the neighbourhood, never the student. hs_entry_year is
             INFERRED as univ_entry_year - 4; use entry_inference_ok to restrict
             to first-time entrants.'""")

    print(f"  mart.utsa_student_context: {len(out):,} students", flush=True)
    with db.connect() as c:
        print()
        print(pd.read_sql("""
            SELECT count(*) students,
                   count(leaid) with_district,
                   count(kfr_p25) with_oa,
                   count(*) FILTER (WHERE oa_proxy_ok) proxy_ok,
                   count(*) FILTER (WHERE hb5_default) post_hb5,
                   count(*) FILTER (WHERE NOT hb5_default) pre_hb5,
                   count(*) FILTER (WHERE entry_inference_ok) new_entrants
            FROM mart.utsa_student_context""", c).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
