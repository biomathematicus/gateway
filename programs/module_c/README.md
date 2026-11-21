# Linked entrant models (Module C)

Pipeline behind Section 3.6 of the Paper 0 manuscript: what predicts
mathematics preparation at entry, and what predicts first-year performance
in each subject. The analysis plan, the Stage 0 maps, and the registration
record are in `prespecification/` at the root of the repository. The
registered programs and the registration records name the plan by its
path at registration (`Economics/Paper0/module_c/`); those files cannot
change without changing their registered hashes.

## Rules

- Student rows are read from the institutional source in place and held in
  memory only. Nothing row-level is written to disk, and no student row
  goes to GATEWAY.
- Every output is an aggregate with at least 10 students per released cell.
- The plan was frozen before estimation. `mc_data.py`, `mc_models.py`,
  `run_module_c.py`, and `../ingest/crdc_courses.py` are hashed in the
  registration record; a change to any of them after the freeze is a
  deviation to be logged in Section 17 of the plan.
- SQL for cross-referencing, arrays for computation, no dataframes.

## Modules

| File | Role |
|---|---|
| [mc_data.py](mc_data.py) | assembly: students, first attempts in the first-year window, school and district context |
| [mc_models.py](mc_models.py) | estimators: clustered least squares with absorbed fixed effects, nested random-intercept REML, fixed-effects logit, Benjamini-Hochberg, random-effects pooling |
| [run_module_c.py](run_module_c.py) | stages: sample flow, preparation models, subject models, sensitivity runs, predictive ladder |
| [mc_figures.py](mc_figures.py) | figures, captions, and the pooled table, drawn from the released tables; the table reports the registered pooling and a companion weighted by first attempts (`q2_weighted.csv`) |
| [cohort_notes.py](cohort_notes.py) | entry terms and CAP split of the reference cohort |
| [register.py](register.py) | writes the registration record (run once, at the freeze) |

### Class-size addendum

Plan: `prespecification/class_size_addendum.md` (registered
2026-11-19; record in `class_size_registration.md`). It imports the
modules above unchanged.

| File | Role |
|---|---|
| [cs_data.py](cs_data.py) | sections (size, schedule type, instructor label) and first attempts with their section; an outcome-blind mode selects no grade field |
| [run_class_size.py](run_class_size.py) | Stage 0 (flow, exposure, balance), the comparison ladder M0 to M4 by subject, student fixed effects, the next-course check, the 45-student cap scenario, sensitivity runs; wild cluster bootstrap over instructors for p-values and intervals |
| [cs_figures.py](cs_figures.py) | `figClassSizeLadder` and `tabClassSizeScenario`, with generated captions; the figure caption expands its own subject codes from `mc_figures.SUBJECT_NAME`, so the figure reads alone in the body of the manuscript |
| [register_class_size.py](register_class_size.py) | writes the addendum's registration record (run once) |

Instructor identifiers are replaced by a salted surrogate inside the
query, and no output is indexed by section or instructor.

### Corrections after review (2026-11-20)

Deviation D2 of the plan and D1 of the addendum. The registered files
above are imported unchanged and keep their hashes; frozen copies are in
`prespecification/frozen/`.

| File | Role |
|---|---|
| [rev5_module_c.py](rev5_module_c.py) | pooled intervals with the covariance between subject estimates; predictive ladder with the course-by-term baseline built from training rows only, in two stated tasks, with a bootstrap over sending schools; primary coefficients without the aid variables; provenance of the aid and score fields. Writes `../figures/module_c/rev5/` |
| [rev5_class_size.py](rev5_class_size.py) | wild cluster bootstrap for the linear contrasts of the size coefficient and the interaction (scenario by entry-score third, size slope at a given score), with test inversion and a calibration under shuffles; pooled intervals with two-way clustering; next-course check on continuers with a different instructor; support for the scenario; observed Calculus section sizes. Writes `../figures/module_c/class_size/rev5/` |

`mc_figures.py` and `cs_figures.py` take a second argument naming the
corrections folder: they read the estimates from the first folder, the
corrected intervals from the second, and write there.

### Instructor concentration (exploratory)

[instructor_concentration.py](instructor_concentration.py) asks whether a
subject's low grades sit with a few instructors, on the movers of the
reference cohort and on the first attempts of the section-size models.
Outputs go to `../figures/module_c/instructor_concentration/`; every
number is an aggregate over a subject or over at least five instructors.

## Running

```
python run_module_c.py --permute     # dry run on shuffled outcomes
python run_module_c.py               # registered estimation, about 30 minutes
python mc_figures.py registered
python cohort_notes.py

python run_class_size.py --stage0-only         # outcome-blind checks
python run_class_size.py --permute --calibrate # dry run, about 10 minutes
python run_class_size.py                       # registered, about 6 minutes
python cs_figures.py registered

python rev5_module_c.py                        # corrections, about 7 minutes
python mc_figures.py cohorts_2014_2019 rev5
python rev5_class_size.py --calibrate          # corrections, about 13 minutes
python cs_figures.py registered rev5
```

Class-size outputs go to `../figures/module_c/class_size/`.

Outputs go to `../figures/module_c/registered/` (or `dryrun/`). The
institutional SQL Server service must be running.
