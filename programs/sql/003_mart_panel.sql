-- mart.alg2_panel — the five-cycle district panel, SAIPE joined through dim_year.
--
-- `is_universe` is carried through deliberately. All five cycles of the panel
-- are universe collections; the column records the frame of each cycle so
-- that a sampled cycle could not enter a level comparison unnoticed.
DROP VIEW IF EXISTS mart.alg2_panel CASCADE;
CREATE VIEW mart.alg2_panel AS
SELECT p.cycle,
       y.fall_year,
       y.saipe_vintage                                    AS vintage,
       p.is_universe,
       p.leaid,
       p.state_pc,
       s.name,
       s.pop_5_17,
       s.pov_5_17,
       CASE WHEN s.pop_5_17 > 0 THEN s.pov_5_17 / s.pop_5_17 END      AS pov_rate,
       p.alg2_enrollees,
       p.n_schools,
       p.n_alg2_reported,
       p.n_alg2_missing,
       CASE WHEN s.pop_5_17 > 0 THEN p.alg2_enrollees / s.pop_5_17 END AS alg2_per_child,
       (p.state_pc = 'TX')                                             AS is_tx
FROM core.crdc_district_panel p
JOIN core.dim_year y  ON y.school_year = p.cycle
JOIN stg.saipe_sd s   ON s.leaid = p.leaid AND s.vintage = y.saipe_vintage
WHERE s.pop_5_17 > 0 AND p.alg2_enrollees IS NOT NULL;
