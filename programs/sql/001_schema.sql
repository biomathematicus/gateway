-- GATEWAY: layered schema.
--
-- Layering is by PROVENANCE, not by topic, because the reason this database is
-- being rebuilt is that the previous one's provenance could not be reproduced.
--
--   raw_*  verbatim source text + the file and sha256 it came from. Never edited.
--   stg    typed. This is where sentinel values die (see below).
--   core   conformed dimensions and facts.
--   mart   analysis-ready views, one per report figure.
--
-- THE SENTINEL PROBLEM, stated once here because it is the single most likely
-- way to get a wrong number out of this database:
--
--   CRDC stores reserve codes IN the count columns: -3 skip logic, -4 missing
--   optional, -5 action plan, -6 force certified, -9 not applicable/skipped,
--   -11/-12 suppressed for privacy, -13 missing DIND skip logic. In the previous
--   database every CRDC column was `character varying`, so the natural
--   `col::int` then `SUM()` silently ADDS -9 sentinels into an enrollment total.
--   In `stg` a sentinel becomes NULL and its identity is preserved in a parallel
--   `*_rc smallint` column, so a suppression rate stays reportable and a total
--   can never absorb a code.
--
--   SAIPE has no sentinels but does ship values with thousands separators and
--   blank cells; those become NULL, not 0.

CREATE SCHEMA IF NOT EXISTS raw_saipe;
CREATE SCHEMA IF NOT EXISTS raw_crdc;
CREATE SCHEMA IF NOT EXISTS raw_xwalk;
CREATE SCHEMA IF NOT EXISTS raw_oa;
CREATE SCHEMA IF NOT EXISTS raw_nmdb;
CREATE SCHEMA IF NOT EXISTS raw_utsa;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

-- ---------------------------------------------------------------------------
-- provenance: every raw load registers here, so a table can always be traced
-- back to a file and a hash.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.source_file (
    source_id     bigserial PRIMARY KEY,
    dataset       text        NOT NULL,     -- 'saipe_sd', 'crdc', 'grf', ...
    vintage       text        NOT NULL,     -- '2017', '2017-18', ...
    rel_path      text        NOT NULL,     -- path under /data
    sha256        text        NOT NULL,
    bytes         bigint      NOT NULL,
    source_url    text,
    loaded_at     timestamptz NOT NULL DEFAULT now(),
    n_rows        bigint,
    UNIQUE (dataset, vintage, rel_path)
);

-- ---------------------------------------------------------------------------
-- dim_year: the ONE place the school-year / calendar-year alignment is written
-- down. Every join between a CRDC cycle and a SAIPE vintage goes through here
-- instead of being re-derived in each query.
--
-- CRDC is a school year (2017-18). SAIPE is a calendar income year. The
-- convention adopted: a CRDC cycle pairs with the SAIPE vintage of its FALL
-- calendar year, because SAIPE's "estimated population 5-17 in poverty" is an
-- estimate for that income year and the CRDC snapshot is taken during it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.dim_year (
    school_year     text PRIMARY KEY,     -- '2017-18'
    fall_year       int  NOT NULL,        -- 2017
    spring_year     int  NOT NULL,        -- 2018
    saipe_vintage   int  NOT NULL,        -- 2017
    crdc_cycle      boolean NOT NULL DEFAULT false,
    note            text
);

INSERT INTO core.dim_year (school_year, fall_year, spring_year, saipe_vintage, crdc_cycle, note) VALUES
  ('2009-10', 2009, 2010, 2009, true , 'CRDC sample, not universe'),
  ('2011-12', 2011, 2012, 2011, true , 'CRDC universe from this cycle'),
  ('2013-14', 2013, 2014, 2013, true , 'TX HB5 signed 2013; Foundation default for students ENTERING HS 2014-15'),
  ('2015-16', 2015, 2016, 2015, true , NULL),
  ('2017-18', 2017, 2018, 2017, true , 'held locally'),
  ('2020-21', 2020, 2021, 2020, false, 'CRDC skipped this cycle'),
  ('2021-22', 2021, 2022, 2021, true , 'held locally; pandemic year'),
  ('2012-13', 2012, 2013, 2012, false, NULL),
  ('2014-15', 2014, 2015, 2014, false, NULL),
  ('2016-17', 2016, 2017, 2016, false, NULL),
  ('2018-19', 2018, 2019, 2018, false, NULL),
  ('2019-20', 2019, 2020, 2019, false, NULL)
ON CONFLICT (school_year) DO NOTHING;

-- ---------------------------------------------------------------------------
-- dim_lea: districts are NOT stable across 30 years. They merge, split and
-- close, and a LEAID that disappears looks exactly like "instability" in a
-- poverty series unless it is measured separately. This table records, per
-- LEAID, the span over which SAIPE actually reports it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.dim_lea (
    leaid        text PRIMARY KEY,
    state_fips   text,
    state_pc     text,
    name_last    text,
    first_year   int,
    last_year    int,
    n_years      int
);

CREATE TABLE IF NOT EXISTS core.dim_state (
    state_fips text PRIMARY KEY,
    state_pc   text UNIQUE,
    state_name text
);
