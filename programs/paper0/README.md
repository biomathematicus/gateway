# Paper 0 Exhibits

Positioning and context exhibits of the manuscript. Every module writes
four artifacts into
`../figures/paper0/`: `<name>.pdf` (vector, embedded by the manuscript),
`<name>.png` (300-DPI preview), `<name>.tex` (figure environment with the
canonical caption; the manuscript `\input`s the paper0 snippets), and
`<name>_data.csv` (backing data). Analysis uses SQL for cross-referencing
and lists / numpy arrays for computation; no dataframes.

## Modules

| Module | Figure | Source |
|---|---|---|
| [scorecard.py](scorecard.py) | `figScorecardLocator` — four-panel national position (2019-20 baseline row, 2024-25 current row) | project PostgreSQL (`paper0.scorecard.institution`, port 5434), loaded by [load_scorecard.py](load_scorecard.py) from the hashed Scorecard archive |
| [science_figure.py](science_figure.py) | `figScienceProvision` — science provision deserts at the sending schools | published aggregates of pipeline report 026 (`../figures/026_*.csv`) |
| [course_panels_figure.py](course_panels_figure.py) | `figCalculusPanels` — manuscript Figure 1: district Calculus enrollment per high-school student against (A) child poverty and (B) median household income, Bexar County highlighted (weighted slope -0.171, SE 0.020, -36.9% of the national mean per ten points; income r = 0.45). `_stats.json` holds the Texas fit, the unweighted fit, and the landmark districts | GATEWAY `mart.course_poverty` (`hs_enr_est`) plus `figAlgebraIIOA_data.csv` for district income; run `oa_figure.py` first |
| [algebra2_panels_figure.py](algebra2_panels_figure.py) | `figAlgebraIIPanels` — superseded in the manuscript by `figCalculusPanels` (Algebra II was the subject of an early hypothesis the course comparison did not bear out); kept for the record: district Algebra II enrollment per high-school student against (A) child poverty and (B) median household income, Bexar County highlighted (weighted slope -0.014, SE 0.033; income r = 0.06). `_stats.json` also holds the per-resident-child slope on the same frame, the unweighted fit, and the income correlations cited in the text | GATEWAY `mart.course_poverty` (`hs_enr_est`) plus `figAlgebraIIOA_data.csv` for district income; run `oa_figure.py` first |
| [algebra2_figure.py](algebra2_figure.py) | `figAlgebraIIPoverty` — Algebra II enrollees per resident child aged 5-17 vs child poverty. Superseded in the manuscript by `figAlgebraIIPanels`; kept for the per-child record | GATEWAY `mart.alg2_poverty` (CRDC 2017-18 × SAIPE 2017), spec of report 024 |
| [oa_figure.py](oa_figure.py) | `figAlgebraIIOA` — Algebra II enrollees per resident child on the Opportunity Atlas income surface (weighted r = 0.20). Superseded in the manuscript by panel B of `figAlgebraIIPanels`; its `_data.csv` remains the source of district income | GATEWAY `context_tract.oa_tract` × `raw_xwalk.lea_tract_frac` (GRF17, loaded by `../ingest/tract_district_xwalk.py`) × `mart.alg2_poverty` |
| [course_gradient_figure.py](course_gradient_figure.py) | `figCourseGradients` — manuscript Figure 2, two panels. (A) United States: the gradient estimator repeated for 15 CRDC course families: profile by tenths of high-school students plus relative gradients, every count divided by estimated enrollment in the grades of the course (high-school enrollment for high-school courses, grades 7-8 enrollment for early Algebra I), with each gradient also printed in seats per 100 students. (B) Bexar County, Texas: the same display for the county's 15 school districts, drawn by the same two functions (`heat`, `forest`). Districts are ordered by child poverty and merged into groups that each hold at least a tenth of the county's high-school students (`MIN_SHARE`; five groups), and the gradient is the weighted slope over the 15 districts, relative to the national mean, with percentile intervals from a bootstrap that resamples districts on its own random stream, so the national intervals do not change (`_bexar.csv` holds the district, group, and county ratios; `_bexar_slopes.csv` the county gradient with its interval beside the national one). The gradient axis `X_RANGE` is shared by the two panels; the per-resident-child variant stays in the statistics and gradient files only, on the districts with no missing-coded course item (companion `_gradients.csv`, `_bexar.csv`, `_income.csv`, `_stats.json` hold three cycles, three frames, the grade 9-12 school check, and the income correlations by course) | GATEWAY `mart.course_poverty` (CRDC 2015-16, 2017-18, 2021-22 × SAIPE, loaded by `../ingest/crdc_courses.py`, which estimates `hs_enr_est` and `ms_enr_est` by grade-span proration) |
| [provision_figure.py](provision_figure.py) | `figProvisionBands` — credit arrival by sending-school AP-math provision | published aggregates of report 021 (`../figures/021_school_ap_offer.csv`) |
| [sending_poverty.py](sending_poverty.py) | `figSendingPoverty` — child poverty of sending districts vs all Texas children | GATEWAY `core.hs_crosswalk` × `stg.saipe_sd` (aggregates only) |

## Infrastructure

- [pg.py](pg.py) — dedicated user-space PostgreSQL 16 cluster for imported
  Paper 0 data (port 5434, trust auth on localhost, data directory outside
  any synchronized folder). Its settings are the `[scorecard]` section of
  `../env/config.toml`, each with a default. `connect()` starts the server
  if needed.
- [load_scorecard.py](load_scorecard.py) — streams the curated Scorecard
  columns from the hashed zip into `scorecard.institution`; idempotent per
  data year. The archive's manifest row (sha256, lineage) lives in
  `data_manifest.csv` at the root of the repository.
- GATEWAY access goes through `../gateway/db.py`; all reads are from
  published aggregate tables/views, never student microdata.

## Running

```
python scorecard.py
python science_figure.py
python ../ingest/crdc_courses.py      # once; loads the course families
python oa_figure.py                   # writes the district income file
python course_panels_figure.py         # Figure 1
python course_gradient_figure.py
python provision_figure.py
python sending_poverty.py
```

Each module prints its headline numbers (e.g. the fitted slope, weighted
medians) so a regeneration can be checked against the pipeline reports
before the manuscript is recompiled.
