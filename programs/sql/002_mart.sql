-- GATEWAY marts: analysis-ready views, one per report figure.
--
-- The SAIPE<->CRDC join goes through core.dim_year so the school-year /
-- calendar-year convention is stated once. CRDC 2017-18 pairs with SAIPE 2017;
-- CRDC 2021-22 with SAIPE 2021.

-- ---------------------------------------------------------------------------
-- mart.district_year — the SAIPE panel, 1995-2024, with a poverty RATE.
-- The rate denominator is population 5-17, not total population: the AISES
-- slide plots counts, but a rate is what makes districts comparable.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS mart.district_year CASCADE;
CREATE VIEW mart.district_year AS
SELECT s.vintage,
       s.leaid,
       s.state_fips,
       s.name,
       s.pop_total,
       s.pop_5_17,
       s.pov_5_17,
       CASE WHEN s.pop_5_17 > 0 THEN s.pov_5_17 / s.pop_5_17 END AS pov_rate
FROM stg.saipe_sd s;

-- ---------------------------------------------------------------------------
-- mart.alg2_poverty — the AISES figure, hardened.
--
-- Each row is a district in a CRDC cycle: children 5-17 in poverty (SAIPE) on
-- one axis, Algebra II enrollees (CRDC, summed over the district's schools with
-- sentinels removed) on the other, plus the coverage behind the sum so a
-- partially-suppressed district is visible rather than silently small.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS mart.alg2_poverty CASCADE;
CREATE VIEW mart.alg2_poverty AS
SELECT c.cycle,
       y.saipe_vintage                       AS vintage,
       c.leaid,
       c.state_pc,
       s.name,
       s.pop_5_17,
       s.pov_5_17,
       CASE WHEN s.pop_5_17 > 0 THEN s.pov_5_17 / s.pop_5_17 END AS pov_rate,
       c.alg2_enrollees,
       c.enr_total,
       c.n_schools,
       c.n_alg2_reported,
       c.n_alg2_missing,
       -- the AISES reference line: districts BELOW y=x have more children in
       -- poverty than children taking Algebra II
       CASE WHEN c.alg2_enrollees IS NOT NULL AND s.pov_5_17 IS NOT NULL
            THEN (c.alg2_enrollees < s.pov_5_17) END           AS below_parity,
       CASE WHEN s.pov_5_17 > 0 THEN c.alg2_enrollees / s.pov_5_17 END
                                                               AS alg2_per_poor_child,
       CASE WHEN s.pop_5_17 > 0 THEN c.alg2_enrollees / s.pop_5_17 END
                                                               AS alg2_per_child
FROM core.crdc_district c
JOIN core.dim_year y   ON y.school_year = c.cycle
JOIN stg.saipe_sd s    ON s.leaid = c.leaid AND s.vintage = y.saipe_vintage;

-- ---------------------------------------------------------------------------
-- mart.lea_panel_balanced — districts present in EVERY SAIPE vintage.
-- Rank-persistence and ICC must be computed on a balanced panel, otherwise
-- district entry/exit is read as instability. dim_lea records the churn
-- separately so it can be reported rather than absorbed.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS mart.lea_panel_balanced CASCADE;
CREATE VIEW mart.lea_panel_balanced AS
WITH n AS (SELECT count(DISTINCT vintage) AS n_vintages FROM stg.saipe_sd)
SELECT d.*
FROM mart.district_year d
JOIN core.dim_lea l ON l.leaid = d.leaid
CROSS JOIN n
WHERE l.n_years = n.n_vintages;
