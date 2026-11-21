# Module C analysis plan

## Pre-college predictors of mathematics preparation and first-year subject performance among UT San Antonio first-time entrants

Version 1.0, 2026-11-18. Registered.
Deliverable: `P0-D06` (VER9 Paper 0, §6 and §10.6).
Status: accepted by the PI and frozen before any estimation. The registration record, with the SHA-256 of this file and of the code, is `registration_event.md`.

PI decisions recorded (2026-11-18):

- all entry cohorts are modeled;
- CAP students stay in the sample with a flag;
- this plan is written and frozen before any estimation;
- the demographics block is included;
- the thresholds of Section 9 and the 1,000-student subject minimum are accepted;
- IRB coverage for this analysis is in place (PI confirmation);
- registration is by SHA-256 of this file and date, as a typed event for `VER9_Log.md`;
- the two amendments of version 0.2 (school block trimmed by stability; credit route in three levels) are accepted, and the Stage 0 maps stand as drafted.

---

## 1. Questions, claim class, hypotheses

**Q1, preparation.** Among first-time fall entrants, which pre-college characteristics predict mathematics preparation at entry, and which predict preparation in mathematics specifically, beyond general academic preparation?

**Q2, performance.** For every subject with enough first-year enrollment, which pre-college characteristics predict first-year course performance, and does mathematics preparation predict performance outside mathematics beyond verbal preparation?

**Claim class.** Predictive association, conditional on UT San Antonio entry. No causal effect is estimated. Reports use "predicts" and "is associated with"; "determines" is reserved for the PI's motivating statement.

**Hypotheses stated in advance.**

- **H1.** The sending school's advanced-mathematics enrollment (Calculus and AP mathematics per student) predicts the gap between an entrant's mathematics and verbal scores after family resources are accounted for.
- **H2.** The mathematics score predicts first-year grades in subjects outside mathematics after the verbal score is accounted for.

**Estimand without a directional hypothesis.** How much out-of-sample skill the place and school blocks add to subject-grade prediction once the preparation block is included.

---

## 2. Population and sample flow

**Target population.** First-time-in-college entrants (`STUDENTTYPE = 'New'`) whose first term is a fall term, Fall 2009 through Fall 2019: 50,469 students in 11 cohorts.

| Use | Cohorts | Students |
|---|---|---:|
| Q1 (preparation at entry) | Fall 2009 to Fall 2019 | 50,469 |
| Q2 (first-year performance) | Fall 2009 to Fall 2018 (complete first-year window) | 46,080 |

- Spring and summer first-time entrants are reported as counts and excluded from estimation.
- CAP students (13.4% of first-time entrants) are retained. The CAP flag enters every model, and primary contrasts are also reported by CAP status.
- **Linked sample:** entrants whose sending school resolves to an accepted NCES school in the frozen crosswalk (Section 5). All models that use the place or school blocks run on the linked sample.
- **All-entrant sample:** every fall entrant. Models without the place and school blocks run on it as a selection check on the linked sample.
- A sample-flow table (all first-time, fall entrants, scored, aid status known, linked, in each subject) is produced in Stage 0, before any outcome model.

The `'New'` rule is the provisional cohort rule. Reconciliation against the official institutional-research census cohort is a gate for publication (Section 11).

---

## 3. Time axis

- A term dimension maps each term code to an ordered index. Arithmetic on floating term codes is retired.
- **Baseline:** everything recorded before the first course attempt. All predictors are baseline quantities.
- **First-year window:** entry fall, following spring, following summer (term offsets 0 to 2).
- Course rows dated before the entry term are audit counts and never outcomes.
- This plan ends at the first-year landmark. Outcomes after year one belong to the sibling study (Section 14).

---

## 4. Variables

Inventory verified against `dbo.OIR` by schema and aggregate queries on 2026-11-18.

### 4.1 Predictor blocks

| Block | Variables | Coding fixed in advance |
|---|---|---|
| **F, family resources** | aid application (`FA_APPLIED`), adjusted gross income (`AGINum`), first-generation status | AGI enters as the percentile rank within entry cohort among aid applicants, zero and negative values included. Non-applicants (18.5%, no income recorded) form their own category. An indicator marks AGI at or below zero (4.3% of applicants). First-generation keeps its "Unknown" category. |
| **D, demographics** | gender, ethnicity | Categories as recorded; any category under the minimum cell is pooled into "other". |
| **P, place** | district child poverty rate (SAIPE), district children aged 5-17 (log) | Mean of the four SAIPE vintages ending the year before entry. |
| **S, school** | Calculus, AP mathematics, AP science, and dual enrollment per student; school enrollment (log) | From the nearest eligible CRDC cycle (4.3). Rates are winsorized at the 99th percentile, with an indicator for a school reporting none. The **advanced-mathematics index** is the mean of the cycle-standardized Calculus and AP mathematics rates. Measures were admitted on stability alone (4.4). |
| **T, preparation** | mathematics and verbal scores (`HIGHEST_SATACT_MATH`, `HIGHEST_SATACT_ERW`); pre-college mathematics credit route | Scores are standardized within entry cohort, which absorbs the 2016 SAT redesign. Missing scores (1.6%) take the cohort mean with a missing indicator. Credit route has three levels: none; dual enrollment only; exam-based (AP or CLEP, with or without dual enrollment). In a subject model where a level holds fewer than 30 students, the factor reduces to any credit against none. |
| **Design** | entry cohort, CAP flag | Cohort as a factor. |

Pell status is nearly a function of AGI (98% of the lowest AGI fifth and 0.3% of the highest receive it), so it is held out of primary models and used only in a sensitivity run that replaces AGI.

The record holds no high-school grade average, class rank, or transcript. Reports state that test scores absorb part of what those measures would explain.

### 4.2 Outcomes

**Q1, preparation at entry.**

| Outcome | Definition | Role |
|---|---|---|
| Mathematics score | cohort-standardized mathematics score | primary |
| Mathematics-verbal gap | standardized mathematics score minus standardized verbal score | primary (the "mathematics specifically" outcome) |
| Entry mathematics level | ordinal level of the first mathematics course attempted in the first-year window | secondary; requires the course map of Stage 0 |
| Mathematics credit in hand | AP credit, dual-enrollment credit (two indicators) | secondary |

**Q2, first-year performance, one model per subject.**

- **Unit:** student by course, lower-division courses (numbered below 3000, developmental courses included), inside the first-year window.
- **First attempt:** the earliest term in which the student has a row for that course. The repeat indicator marks grade-average inclusion and plays no part in the selection.
- **Grade:** quality points on rows the registrar counts in the grade average (`SHRGRDE_GPA_IND = 'Y'`): letter grades A+ through F on the 4-point scale, verified in the Stage 0 inventory.
- **DFW:** 1 for any D grade, F, W (withdrawal), or NC (no credit); 0 for any other letter grade or CR (credit). Rows coded IN or NR are excluded.
- Withdrawals and credit or no-credit rows hold zero quality points in the source and never enter a grade mean.
- **Subject inclusion:** at least 1,000 linked-sample students with a qualifying first attempt across cohorts. The subject list is fixed in Stage 0 from enrollment counts alone.
- Each subject is classed as quantitative or other in Stage 0, from catalog descriptions, before estimation.

### 4.3 School-snapshot timing

Each entrant takes the CRDC universe cycle nearest the spring of the senior year, ties to the earlier cycle. Eligible cycles are 2013-14, 2015-16, and 2017-18; the 2011-12 cycle is excluded for its anomalous zeros. The lag in years is printed with every school-block result. The variable is named **senior-school context**; it is never described as exposure across the high-school years.

The 2013-14 cycle recorded dual enrollment as a yes-or-no indicator. For cohorts mapped to that cycle, the dual-enrollment rate comes from the 2015-16 cycle.

### 4.4 Usability of the AP measures (checked before the freeze, outcome-blind)

**Student credit.** Of 50,469 fall entrants, 2,193 hold AP mathematics credit (4.3%, 133 to 256 per cohort), 7,095 hold dual-enrollment mathematics credit (14.1%), and 238 hold CLEP credit (0.5%). AP credit is recorded as credit only, with no examination score, and is almost entirely Calculus I. It supports an indicator in pooled models and is too thin to stand alone in small subject models, which is why the credit route is coded in three levels with a fallback.

**School enrollment.** AP counts are low at many schools and ample where the entrants come from. In the 2017-18 cycle, 30% of sending schools report no AP mathematics and 42% report fewer than 10 enrollees, but those schools send 4.9% and 7.1% of linked students. The median linked student's school reports 116 AP mathematics enrollees.

**Stability.** A school measure enters the S block when its per-student rate has a rank correlation of at least 0.5 between the 2015-16 and 2017-18 cycles across the 1,209 sending schools present in both.

| Measure | Rank correlation between cycles | In the S block |
|---|---:|---|
| AP, any course | 0.87 | no (overlaps the two AP measures below) |
| AP science | 0.78 | yes |
| AP mathematics | 0.76 | yes |
| Advanced-mathematics index | 0.69 | yes (H1) |
| Calculus | 0.62 | yes |
| Dual enrollment | 0.62 | yes |
| Advanced mathematics | 0.44 | no |
| Physics | 0.28 | no |
| Algebra II | 0.24 | no |

The index reliability of about 0.7 is expected to attenuate the H1 coefficient; the report states this beside the estimate.

---

## 5. Linkage (frozen specification)

- Sending school to NCES school: `core.hs_crosswalk` in GATEWAY, as of the freeze date. Accepted decision codes are `auto`, `auto_adj`, `auto_ccd`, and `auto_vint`; the codes `none`, `private`, and `rejected` are unlinked. The table's SHA-256 is recorded at registration.
- NCES school to district: the first seven digits of the school identifier.
- District to poverty: SAIPE, joined on the district identifier and vintage.
- School to course provision: the CRDC course tables loaded by `code/ingest/crdc_courses.py`, extended to the 2013-14 cycle in Stage 0.
- Students are read from the source in place. School and district context is read from GATEWAY into memory and joined there. No student row is written to GATEWAY.

---

## 6. Models

### 6.1 Q1: what predicts preparation

1. **Variance partition.** Random-intercept model (district, school within district) with cohort and CAP effects, for the mathematics score and for the mathematics-verbal gap. Output: the share of variance between districts, between schools, and within schools.
2. **Block sequence.** Add F, then D, then P, then S. Output: the share of each variance component explained at each step.
3. **Within-school and between-school income gradients.** AGI rank is split into the school mean and the student's deviation from it. The two slopes show whether income tracks preparation among classmates, across schools, or both.
4. **H1 coefficient.** The advanced-mathematics index in the full model for the gap, per standard deviation of the index, with a school-clustered 95% interval.

### 6.2 Q2: what predicts performance, subject by subject

For each included subject, the same specification:

- **Outcome:** grade (linear model) and DFW (linear probability model; a logit is run as a check).
- **Fixed effects:** course by term, so students are compared within the same course offering.
- **Steps:** (a) mathematics and verbal scores; (b) plus F, D, CAP, and credit route; (c) plus P and S.
- **Primary contrasts, from step (b):** the mathematics coefficient, the verbal coefficient, and their difference, each per standard deviation.
- **Summary across subjects:** a subject-by-predictor table of standardized coefficients, shown as a heatmap, and a random-effects pooled estimate within each subject class.

Because comparisons are within a course, Q2 measures performance given the course taken. Which course an entrant starts in is measured in Q1 (entry mathematics level).

### 6.3 Predictive ladder (adapted from the iBudget Volume I framework)

Applied to the two primary Q1 outcomes and to each Q2 subject.

| Element | Specification |
|---|---|
| Model families | linear model with the blocks; ridge regression (penalty by generalized cross-validation); random forest |
| Targets | Q1: the two primary outcomes. Q2: the relative outcome, the deviation of a grade or DFW indicator from its course-by-term mean, which is the comparison the fixed-effects models make |
| Random-forest setting | 500 trees; one third of the features per split; depth 6, 10, or unlimited; minimum leaf 20 or 50. The setting is chosen once per target, by three school-grouped folds inside the forward-check training cohorts with 200 trees, and then held fixed |
| Validation | 10 folds assigned by sending school, so every student of a school sits in one fold |
| Forward check | train on entrants through Fall 2015, test on Fall 2016 to Fall 2018 |
| Metrics | out-of-fold R² and RMSE; for DFW also AUC and Brier score, scoring each student by the classmates' DFW rate plus the predicted deviation |
| Block skill | for the linear and ridge families: added out-of-fold skill when a block enters in order (Q1: F, D, P, S; Q2: T, F, D, P, S), and lost skill when a block is dropped from the full model; both are reported |
| Subgroup error | out-of-fold error by aid group, first-generation status, CAP status, and school-size band |
| Feature set | fixed by this plan; variance inflation and mutual information are reported as descriptive tables |

The linear models answer the questions. The random forest checks whether they miss interactions or curvature; a gap in out-of-fold skill above 0.02 in R² triggers a reported search for the source.

---

## 7. Inference and multiplicity

- Standard errors are clustered on sending school throughout.
- Q1 has two primary coefficients, reported with 95% intervals and no adjustment.
- Q2 controls the false-discovery rate by Benjamini-Hochberg at q = 0.05 within each of three families across subjects: mathematics coefficients, verbal coefficients, and their differences.
- Everything outside the primary contrasts is labeled exploratory in every table and caption.

---

## 8. Missing data, selection, and sensitivity runs

| Issue | Handling |
|---|---|
| No income for non-applicants | own category; never imputed |
| Missing scores | cohort mean with indicator; complete-case run as a check |
| Unlinked sending school | excluded from linked-sample models; inverse-probability-of-linkage weights as a check; common coefficients compared between the linked and all-entrant samples |
| Selection on entry | every result labeled conditional on entry; no statement about Texas high-school students |
| School mobility | the record names one sending school; a run restricted to entrants whose home ZIP lies within 10 miles of that school |
| Snapshot lag | a run restricted to cohorts with a lag of two years or less |
| Score redesign | a run splitting cohorts before and after Fall 2016 |
| CAP | all primary contrasts repeated by CAP status |
| AGI coding | runs with log AGI among positive values, and with Pell status in place of AGI |

---

## 9. Interpretive commitments

Fixed before estimation. The thresholds are open to PI adjustment until the freeze.

- **H1 is supported** when the advanced-mathematics index coefficient on the gap is positive with an interval excluding zero in the primary model and stays positive in the lag and distance runs.
- **H2 is supported** when the pooled mathematics coefficient, net of verbal, across non-quantitative subjects has an interval excluding zero and the coefficient passes false-discovery control in at least half of those subjects.
- Estimates and intervals are reported in full whether or not a hypothesis is supported.
- Effects are translated into score points and grade points alongside standardized units.
- The population-side pattern (all districts, public data) comes from the course-gradient analysis already in the manuscript. A Texas campus-level companion is outside this plan.

---

## 10. Disclosure and environment

- Estimation runs on the authorized machine against the source database in place.
- Student rows are held in memory only. This plan creates no row-level cache file and writes no student row to GATEWAY or the synced project tree.
- Identifiers are replaced by the salted surrogate before leaving the query.
- AGI values are never printed, logged, or exported.
- Released outputs are aggregates: coefficients, variance components, fold metrics, and figures. Every released cell or group holds at least 10 students. School-level random effects are not released.

---

## 11. Gates before estimation (VER9 §6.5)

| Gate | Status | Owner |
|---|---|---|
| IRB determination covering this analysis | **Closed.** Protocol FY24-25-316 provides for retrospective data analysis: non-interventional secondary analysis of existing institutional administrative records for students who first enrolled in Fall 2014 through Fall 2019, with no intervention, no contact or interaction with students, and no new data collection, every exposure and outcome window closing before the Spring 2020 instructional disruption. Data request 201908048-IN, approved 2019-08-25, authorized storage of the data for future research use. | PI |
| Data-owner approval and authorized environment | To confirm | PI, data steward |
| Variable inventory | Complete (Section 4) | analyst |
| Manifest rows | CRDC course rows exist; rows for the 2013-14 cycle and the restricted extract to add | analyst |
| Disclosure and minimum-cell rules | Section 10 | PI |
| Frozen linkage | Section 5; hash at freeze | analyst |
| Frozen outcome algorithm | Section 4.2 plus the Stage 0 maps | analyst, PI review |
| Missingness and multiplicity | Sections 7 and 8 | analyst |
| Selection and mobility sensitivities | Section 8 | analyst |
| Registration | Done 2026-11-18: `registration_event.md` holds the SHA-256 of this file, the Stage 0 maps, the code, and the crosswalk, as a typed `DECISION` event ready for entry into `VER9_Log.md` | PI |

**Custodian questions.** Which aid year the single AGI and Pell snapshot refers to; confirmation that `CAP` marks the Coordinated Admission Program; the official census cohort for reconciliation.

---

## 12. Aggregates already seen

These were viewed before this plan was written. They are fixed background and cannot count as confirmation.

- Aid application by Pell status; AGI medians by aid group.
- Mean mathematics and verbal scores by aid group and by AGI fifth (mathematics 539 to 585, verbal 536 to 590 across fifths).
- CAP status by mathematics enrollment by senior-level progression in the Fall 2014 and 2015 window.
- Graduation counts by cohort and CAP status; first-time entrants by entry term.
- Pipeline reports 013 to 018, 021, and 025: credit route by district poverty, DFW by credit route with score adjustment, linkage selection.
- Counts of AP, dual-enrollment, and CLEP mathematics credit by cohort; AP and Calculus enrollment counts at the sending schools and their stability between cycles (Section 4.4). These describe predictors only.

The income part of Q1 is therefore descriptive. H1 (school provision and the gap) and H2 have not been examined.

---

## 13. Stages and deliverables

| Stage | Content | Output |
|---|---|---|
| 0, outcome-blind | load CRDC 2013-14; term dimension; grade-code map and course-level map from frequency tables; subject list and classes; sample flow; cohort reconciliation; full pipeline run on permuted outcomes | frozen maps, sample-flow table, code state recorded |
| 1 | Q1 models | variance-partition figure, gradient table, H1 estimate |
| 2 | Q2 models | subject-by-predictor heatmap, pooled estimates, H2 verdict |
| 3 | predictive ladder and subgroup error | skill and block tables |
| 4 | disclosure review and write-up | released aggregates, report |

Code lives in `code/module_c/`; outputs in `code/figures/module_c/`. Cross-referencing is done in SQL and computation on arrays, with no dataframes. Figures follow the project standard (vector PDF, 300-DPI PNG, TeX snippet, backing aggregate CSV).

---

## 14. Boundary with the sibling study

`rhe/ANALYSIS_CONTRACT.md` studies first-year mathematics pathways and later outcomes. This plan stops at the first-year landmark and treats pre-college characteristics as predictors of entry preparation and first-year grades. The two share the term dimension, the first-year window, the rule for pre-entry rows, and the official-cohort reconciliation gate.

---

## 15. Decisions requested before the freeze

All decisions are resolved and recorded at the top of this file. The two amendments of version 0.2, accepted by the PI on 2026-11-18, were:

1. **S block trimmed by stability.** Advanced mathematics, Physics, and Algebra II per-student rates leave the school block (rank correlations between cycles of 0.44, 0.28, and 0.24). The H1 index is unchanged.
2. **Credit route in three levels.** None; dual enrollment only; exam-based (AP or CLEP), with the fallback of Section 4.1 for small subjects.

A third item is a clarification from the Stage 0 grade-code inventory: Section 4.2 now states the first-attempt rule, the graded-row rule, and the DFW coding explicitly. The draft maps for review are in `stage0_maps.md`.

---

## 16. Implementation record at registration

Choices fixed while building the pipeline on shuffled outcomes, before the freeze. None was informed by a real outcome.

1. **Samples.** 50,469 fall entrants; 42,016 in the linked sample; 41,963 linked with both scores (Q1); 38,401 linked in the Q2 cohorts. 31 subjects clear the 1,000-student minimum in the linked sample (`stage0_subjects.csv`).
2. **Subject classes.** Quantitative: MAT, CHE, ECO, STA, PHY, CS, ACC, ME. All others: other. Every Q2 summary is repeated with BIO, GEO, AST, ES, and IS moved to the quantitative class.
3. **H2 outcome.** The verdict uses the grade outcome. DFW results are reported beside it.
4. **Index in linear models.** The advanced-mathematics index stands in for its two components in every linear model. The component form (Calculus rate, AP mathematics rate, and their none-indicators) is used in the predictive ladder.
5. **Scaling.** Scores are standardized within entry cohort over all fall entrants. Every other continuous predictor is standardized once, over the linked sample, so a coefficient has the same unit in every model.
6. **Income gradient.** Estimated from the model with cohort, CAP, the split AGI terms, and demographics. Both slopes are per standard deviation of the AGI rank.
7. **Cells.** A course-by-term cell with one row is dropped. When a first-attempt term holds several rows for a course, the grade is their mean over graded rows and DFW is 1 if any is a D, F, W, or NC.
8. **Small categories.** Within each model, a demographic category with fewer than 10 students is pooled into "other".
9. **Linkage weights.** Logistic regression of linkage on cohort, CAP, and the F, D, and T blocks over all fall entrants; weights are the inverse probability, capped at 20.
10. **Secondary Q1 outcomes.** Entry mathematics level by a linear model on the level; credit in hand by linear probability models.
11. **Surrogate.** The identifier surrogate uses a random salt drawn for each run.
12. **Dry run.** The pipeline ran end to end on shuffled outcomes (scores shuffled within cohort, grades within course-by-term cell): the H1 coefficient was -0.003 (SE 0.006), the pooled H2 estimate 0.001 (interval -0.005 to 0.007), no subject passed false-discovery control, and 6.8% of the Q2 coefficients fell under p = 0.05. With the random forest included, out-of-fold R² stayed at or below 0.002 in every model family. The DFW ranking score includes the classmates' DFW rate, so the ladder reports the AUC of that rate alone as the baseline.

---

## 17. Deviations

Append-only after the freeze: date, section, change, reason. Results from a deviating analysis are labeled exploratory.

### D1. Population restricted to Fall 2014 through Fall 2019 (2026-11-19)

- **Section changed:** 2 (population). Preparation models use entrants of Fall 2014 through Fall 2019 (28,209 fall entrants; 23,489 in the linked sample). Performance models use Fall 2014 through Fall 2018 (19,874 linked entrants; 25 subjects clear the 1,000-student minimum).
- **Unchanged:** every other section, including variables, outcome rules, models, hypotheses, and the support thresholds of Section 9.
- **Reason:** PI directive given after the registered run. Institutional conditions in the cohorts before 2014 differ from the later ones, which makes the eleven-cohort pool hard to compare. The decision was made with the registered results known.
- **Status of results:** the registered eleven-cohort results stay in `code/figures/module_c/registered/`. The restricted results are in `code/figures/module_c/cohorts_2014_2019/`, are labeled a post-registration deviation wherever reported, and are shown beside the registered results.
- **Side effect:** every school snapshot now sits within one year of the senior year (the registered run reached five years).
- **Code:** `mc_data.py` and `run_module_c.py` gained a cohort option (`python run_module_c.py --first-cohort 2014 --tag cohorts_2014_2019`); the default reproduces the registered run. `mc_models.py` is unchanged. SHA-256 after the change: `mc_data.py` `6ed4fa72be70c41fc59276167f982641be0ea4a75abcc391a0eea7b151269ea5`; `run_module_c.py` `dde5a0bfd5e327e3d82578b4814a06ce366b7efde9d021bd99da524a11275136`.

### A1. Administrative update to Section 11 (2026-11-19)

The IRB row of Section 11 was replaced with the coverage statement supplied by the PI. The analysis content of the plan is unchanged.

### D2. Corrections after the REV5 review (2026-11-20)

Made with the results of D1 known, in response to `Economics/Paper0/REV5.md`. The registered code files are unchanged (their SHA-256 values still match `class_size_registration.md`); the corrections live in a new script, `code/module_c/rev5_module_c.py` (SHA-256 `542a88511f48eeb120d48430cdb9c67faacb63e6644e2cfcf425e8ad8885dd2f`), which imports them. Outputs are in `code/figures/module_c/rev5/`; the outputs of D1 in `cohorts_2014_2019/` and the registered outputs in `registered/` are untouched. Population: the cohorts of D1.

- **Section 6.2, pooled estimates.** The pooled point estimates are unchanged. Their intervals now include the covariance between subject estimates: each row's influence on a subject's coefficient is summed within sending schools, and the cross-products of those sums across subjects give the school-clustered covariance between subjects. The registered DerSimonian-Laird heterogeneity variance is kept. Reason: the same students and schools contribute to several subject models, and the registered pooling treated subjects as independent. Result: H2 stays supported under the Section 9 rule (pooled 0.140, interval 0.109 to 0.171, against 0.112 to 0.169 under independence; 17 of 18 subjects pass). The interval of the first-attempt-weighted mathematics-minus-verbal difference outside the quantitative subjects now includes zero (-0.008 to +0.043; it was 0.001 to 0.035).
- **Section 6.3, predictive ladder for the Q2 targets.** The registered code computed each course-by-term mean from all rows before the folds were formed, so held-out outcomes entered the targets. The correction computes the mean from training rows only and defines two tasks: (1) sending schools held out, baseline the training mean of the same course and term, with the training mean of the course as fallback; (2) cohorts of Fall 2014 and 2015 predicting Fall 2016 to 2018, baseline the earlier mean of the same course. Skill is the proportional reduction in squared error against the baseline. Block increments gain a bootstrap over sending schools (2,000 draws, one draw applied to all subjects, predictions held fixed). The random-forest settings are the registered ones. Result: values change little (median skill for relative grade 0.086 against 0.085; district poverty +0.0004, interval -0.0008 to +0.0016; school block -0.0015, interval -0.0033 to 0.0000).
- **Not rerun.** The Q1 ladder targets are scores standardized within entry cohort over all fall entrants. The cohort mean and standard deviation use held-out students, a rescaling over about 4,700 students per cohort that the correction leaves as registered.
- **Added sensitivity run (exploratory).** The primary coefficients without the aid variables (application flag and AGI), because the extract records no aid year (`sensitivity_no_aid.csv`). Results are stable: H1 +0.027 (0.008 to 0.046); index and district poverty on the mathematics score +9.8 and -11.4 points; pooled H2 0.145; 24 of 25 subjects pass.
- **Provenance check.** `provenance_fields.json` records that `dbo.OIR` holds one value of each aid and score field per student and no field dating either.
- **Status of results:** every quantity produced under D2 is labeled a post-registration correction where the manuscript reports it. The registered verdicts on H1 and H2 are unchanged.

### A2. Record after the REV7 review (2026-11-20)

Three statements of this section are completed or corrected, and the state of the frozen files is recorded. No analysis was rerun for this record, and no registered file changed. Status: entered on 2026-11-20 for the PI's confirmation.

- **Loader of the course tables (Section 5).** `code/ingest/crdc_courses.py` differs from its registered state (registered SHA-256 `f330c81df01c3f62d83eedf52fe7c4058c0948ef44c79dfd251972fd352562e5`; current `6c0a49e1bd438e18aba4a680e1ff3efaa837bf73fcda52809bdf6aa20a3a3b3f`). The loader was extended on 2026-11-19, after the registration, with the estimate of enrollment in grades 7 and 8 that the district course gradients use. The extension had no entry here until this record. Check: the subject coefficients and standard errors of the performance models reproduce to four decimals on the current tables (`rev5_module_c.py`, 2026-11-20), so the school measures the models read are unchanged in effect.
- **Side effect stated in D1.** The sentence "every school snapshot now sits within one year of the senior year" describes the selected CRDC cycle. Dual enrollment is an exception that follows from Section 4.3: the 2013-14 collection records it as an indicator, so entrants assigned that cycle (Fall 2014 and Fall 2015; 8,180 linked entrants) take the dual-enrollment rate from the 2015-16 cycle. For Fall 2014 entrants that rate is measured two school years after the senior year. The rule is the registered one; D1 described its timing incompletely.
- **Two values printed in D2.** The manuscript now prints every number from the program outputs at full precision. Two values differ in the last digit from those typed in D2: the lower end of the pooled H2 interval under independence is 0.111 (D2 printed 0.112), and the district-poverty coefficient of the run without the aid variables is -11.5 points (D2 printed -11.4, from a rounded coefficient). The estimates are unchanged.
- **Frozen states.** `frozen/README.md` lists the registered files preserved in their frozen state. Version 1.0 of this plan, `mc_data.py`, and `run_module_c.py` as first registered are identified by the hashes of `registration_event.md` and are absent from the working tree; they can be verified once restored from the version history. The files named in `class_size_registration.md` are all preserved, and the five registered programs still match its hashes.
