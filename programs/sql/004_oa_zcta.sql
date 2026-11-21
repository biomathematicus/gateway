-- context_zcta.oa_zcta -- Opportunity Atlas aggregated UP to the ZCTA.
--
-- WHY THIS EXISTS. Deterministic ZIP -> tract assignment fails for this student
-- population: student-weighted match_quality has median 0.218, and only 11.2% of
-- students exceed 0.5. UTSA students concentrate in dense San Antonio ZIPs that
-- span many tracts, so the largest tract holds about a fifth of the ZIP.
-- Picking that tract would be wrong ~78% of the time for the median student.
--
-- So do not pick. Aggregate OA to the ZCTA as a POPULATION-WEIGHTED MEAN over
-- every tract in it. This uses all the information instead of discarding it, and
-- it states its own resolution honestly: the value is a property of the ZIP,
-- which is the finest level the student's address actually supports.
--
-- Still ECOLOGICAL, and now doubly so -- an average of predicted cohort outcomes
-- over an area. It is not a measurement of any student.
CREATE SCHEMA IF NOT EXISTS context_zcta;
DROP TABLE IF EXISTS context_zcta.oa_zcta CASCADE;

CREATE TABLE context_zcta.oa_zcta AS
WITH j AS (
    SELECT x.zcta5,
           x.pop_overlap                                   AS w,
           o.kfr_pooled_pooled_p25,
           o.jail_pooled_pooled_p25,
           o.kfr_black_pooled_p25,
           o.kfr_hisp_pooled_p25,
           o.kfr_white_pooled_p25,
           o.poor_share2010,
           o.med_hhinc2016,
           o.frac_coll_plus2010,
           o.singleparent_share2010
    FROM raw_xwalk.zcta_tract_frac x
    JOIN context_tract.oa_tract   o ON o.geoid_2010 = x.geoid_2010
    WHERE x.pop_overlap > 0
)
SELECT zcta5,
       count(*)                                            AS n_tracts,
       sum(w)                                              AS pop_covered,
       sum(w * kfr_pooled_pooled_p25)  / nullif(sum(w) FILTER (WHERE kfr_pooled_pooled_p25  IS NOT NULL),0) AS kfr_p25,
       sum(w * jail_pooled_pooled_p25) / nullif(sum(w) FILTER (WHERE jail_pooled_pooled_p25 IS NOT NULL),0) AS jail_p25,
       sum(w * kfr_black_pooled_p25)   / nullif(sum(w) FILTER (WHERE kfr_black_pooled_p25   IS NOT NULL),0) AS kfr_black_p25,
       sum(w * kfr_hisp_pooled_p25)    / nullif(sum(w) FILTER (WHERE kfr_hisp_pooled_p25    IS NOT NULL),0) AS kfr_hisp_p25,
       sum(w * kfr_white_pooled_p25)   / nullif(sum(w) FILTER (WHERE kfr_white_pooled_p25   IS NOT NULL),0) AS kfr_white_p25,
       sum(w * poor_share2010)         / nullif(sum(w) FILTER (WHERE poor_share2010         IS NOT NULL),0) AS poor_share2010,
       sum(w * med_hhinc2016)          / nullif(sum(w) FILTER (WHERE med_hhinc2016          IS NOT NULL),0) AS med_hhinc2016,
       sum(w * frac_coll_plus2010)     / nullif(sum(w) FILTER (WHERE frac_coll_plus2010     IS NOT NULL),0) AS frac_coll_plus2010,
       sum(w * singleparent_share2010) / nullif(sum(w) FILTER (WHERE singleparent_share2010 IS NOT NULL),0) AS singleparent_share2010,
       true                                                AS is_ecological,
       '2010'::text                                        AS tract_vintage
FROM j GROUP BY zcta5;

ALTER TABLE context_zcta.oa_zcta ADD PRIMARY KEY (zcta5);

COMMENT ON TABLE context_zcta.oa_zcta IS
 'Opportunity Atlas aggregated to ZCTA as a POPULATION-WEIGHTED MEAN over the '
 'tracts in each ZIP. Built because deterministic ZIP->tract assignment is '
 'unusable for this student population (student-weighted match_quality median '
 '0.218). ECOLOGICAL and area-averaged: not a measurement of any individual.';
