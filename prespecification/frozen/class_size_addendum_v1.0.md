# Module C addendum: section size and first-year performance

## A within-course model of section size, with a cap scenario, for UT San Antonio first-time entrants

Version 1.0, 2026-11-19. Registered.
Parent plan: `analysis_plan.md` (Module C, version 1.0). This addendum adds one question to that plan and changes nothing in it.
Status: frozen before any within-course model was fitted to unshuffled grades. Before the freeze, grades were read only inside the dry runs, which shuffle them within course-by-term cells before any model; the two real quantities that survive the shuffle and were therefore seen are listed in Section 12, item 7. The registration record, with the SHA-256 of this file and of the code, is `class_size_registration.md`.

PI decisions recorded (2026-11-19):

- the class-size curves of the manuscript are to be examined as evidence for an intervention, with a model of what smaller sections would predict;
- scope is all 25 subjects of the performance models, with mathematics reported first;
- the grade in the next mathematics course is the check on grading leniency;
- this addendum is written and frozen before estimation on real grades;
- section size within a course varies for logistical reasons, mostly classroom availability, and courses that run larger do so for historical reasons. Section size is therefore treated as the exposure, with no separate instructional format behind it.

---

## 1. Question, claim class, hypotheses

**Question.** Among first-time entrants taking the same course in the same term, do students in larger sections earn lower grades and more D, F, and withdrawal outcomes, and by how much would those outcomes be predicted to change if large sections were capped?

**Claim class.** Predictive association conditional on entry, as in the parent plan. The estimates compare students within the same course offering, with student preparation and instructor held fixed by adjustment. Section assignment is an administrative process without randomization, so the scenario of Section 7 is a projection under stated assumptions.

**Hypotheses, fixed before estimation.**

- **H3.** In mathematics, larger sections go with lower first-attempt grades within course, term, and instructor, net of preparation.
- **H4.** In mathematics, the section-size association is stronger for students with lower entry mathematics scores.

The other 24 subjects are reported with the same models and with false-discovery control. No hypothesis is attached to them.

---

## 2. Population and unit

- **Students.** First-time fall entrants of Fall 2014 through Fall 2018, the performance cohorts of the parent plan as restricted by its deviation D1. All such entrants are modeled; the linked sample is a sensitivity run, because no school or district variable enters these models.
- **Rows.** First attempts in lower-division courses during the entry fall and the following spring and summer, under the first-attempt rule of the parent plan (Section 16, item 7).
- **Subjects.** The 25 subjects of the performance models (`code/figures/module_c/cohorts_2014_2019/stage0_subjects.csv`). A subject enters the models when at least 200 students hold eligible rows and the standard deviation of log2 section size within course-by-term cells and instructors is at least 0.20. Both conditions are read from the outcome-blind exposure table. The second keeps out subjects whose sections are held to one size, where no comparison of sizes exists (Section 12, item 5).
- **Sections.** A section is a course reference number within a term. A row is eligible when the student holds the course in one section in the first-attempt term, the section holds more than 10 students, and its schedule type is "Lecture face-to-face" (the primary set).

---

## 3. Exposure

Section size is the number of distinct students holding a row in the section, whatever their entry cohort or outcome, so withdrawals count. The exposure is the base-2 logarithm of section size: a coefficient is the change in the outcome per doubling of section size. A banded form (11 to 30, 31 to 45, 46 to 75, 76 to 120, more than 120 students; reference 31 to 45) checks the logarithmic shape in mathematics.

---

## 4. Outcomes

- **Grade:** quality points on rows that count in the grade average (parent plan).
- **DFW:** indicator of a D, F, withdrawal, or no-credit outcome (parent plan).
- **Next mathematics course** (Section 6): the grade in the first attempt at a different mathematics course in the earliest later term among the spring, summer, and fall after the entry fall; ties go to the course with the highest entry-mathematics level of the parent plan's map.

The verdicts of Section 9 use the grade outcome. DFW results are reported beside it.

---

## 5. Models

Each subject is fitted separately, by least squares, with standard errors clustered on instructor. Student covariates are the T, F, D, and CAP blocks of the parent plan (entry scores and credit route; family resources; demographics; the CAP flag).

| Model | Comparison | Terms |
|---|---|---|
| M0 | all sections of the subject | log2 size |
| M1 | same course, same term | M0 + course-by-term fixed effects |
| M2 | and comparable students | M1 + student covariates |
| M3 (primary) | and the same instructor | M2 + instructor fixed effects |
| M4 | by preparation | M3 + log2 size × mathematics score |

M0 reproduces at the student level the comparison drawn by the class-size curves of the manuscript. M1 through M3 remove, in order, differences between courses, between students, and between instructors.

**Student fixed effects.** One model pools the eligible rows of all subjects with student fixed effects and course-by-term fixed effects, so each student is compared with the same student in other courses. It is fitted with one size slope and again with separate slopes for mathematics and for all other subjects.

Fixed effects in two or more dimensions are removed by alternating demeaning to convergence.

---

## 6. Leniency check on the mathematics sequence

A higher grade in a smaller section can reflect more learning or easier grading. The next course is graded by a different instructor, so it separates the two. For mathematics first attempts in the entry fall:

- **Given the origin grade (the check).** The next-course grade is regressed on log2 size of the origin section, the origin grade, and the student covariates, with fixed effects for the origin course-by-term and the next course-by-term. If smaller sections grade more leniently, students from smaller sections do worse than their origin grade predicts, and the coefficient on log2 size is positive.
- **Total.** The same model without the origin grade.
- **Continuation (descriptive, outside the registered set).** Whether the student takes a later mathematics course in the window, on log2 size and the covariates, with origin course-by-term fixed effects. Its value was seen before the freeze (Section 12, item 7).

The check is repeated with origin-instructor fixed effects.

---

## 7. Scenario

**Cap at 45.** Every primary section above 45 students is split into the smallest number of equal sections of 45 or fewer. For a first attempt in a section of size n, the change in exposure is log2(n / ceil(n / 45)) − log2(n). The predicted change in each outcome is the M3 coefficient of the subject times that change, summed over the affected first attempts. The value 45 is the size at which the Calculus I and II sections of the record are capped.

Reported for mathematics and for each other modeled subject: affected first attempts, the predicted change in mean grade and in the DFW rate among them, the predicted number of DFW outcomes per entry cohort, and the number of sections the split adds per academic year. Intervals scale the bootstrap interval of the M3 coefficient. For mathematics the scenario is also reported by third of the entry mathematics score, from M4.

**Assumptions stated with every scenario number.** The within-course association is taken as the effect of size; it is linear in log2 size over the range of the split; added sections are taught as the existing ones are; and the count covers the modeled first attempts only, so other students in the same sections are outside it. The total across subjects assumes independent subject estimates.

---

## 8. Inference and multiplicity

- **Wild cluster bootstrap.** For the size terms of M3 and M4 in every subject, for M0 through M2 and the banded form in mathematics, and for the next-course models with two sets of fixed effects, inference comes from a wild cluster bootstrap of the t statistic with the null imposed: 999 draws, instructors as clusters, Rademacher weights (Webb's six-point weights when a subject has fewer than 12 instructors). The p-value is the share of bootstrap t statistics at least as large in absolute value as the observed one. The 95% interval is the estimate plus or minus the 95th percentile of the absolute bootstrap t statistic times the instructor-clustered standard error, so an interval excludes zero exactly when the p-value is below 0.05. This is the standard remedy when clusters are few or unequal. It was adopted after the dry runs, which showed that the ordinary clustered test rejects too often here (Section 13).
- **Clustered t intervals** (instructor-clustered standard errors, t distribution on the number of instructors minus one) are used where the bootstrap is not implemented: the student fixed-effects model, the next-course model with three sets of fixed effects, and the scenario by entry-score third. Each such interval is labeled.
- Across subjects, Benjamini-Hochberg control at q = 0.05 is applied to the bootstrap p-values of the M3 size coefficient and, separately, of the M4 interaction, within each outcome.
- Subject coefficients are pooled by random effects (DerSimonian-Laird), with the bootstrap half-width divided by 1.96 as the standard error, over all modeled subjects, within the quantitative and other classes of the parent plan, and over the subjects with at least 20 instructors.
- Instructor counts are reported beside every subject estimate.

---

## 9. Interpretive commitments

Fixed before estimation.

- **H3 is supported** when the mathematics M3 coefficient on log2 size for the grade outcome is negative, its interval excludes zero, its bootstrap p-value is below 0.05, and the student fixed-effects slope for mathematics is also negative.
- **H4 is supported** when the mathematics M4 interaction for the grade outcome is positive, its interval excludes zero, and its bootstrap p-value is below 0.05 (the size penalty shrinks as the entry score rises).
- **Leniency is indicated** when the next-course coefficient on log2 size, given the origin grade, is positive with an interval excluding zero. In that case every scenario number for mathematics is reported with that finding beside it.
- Estimates, intervals, and the scenario are reported in full whether or not a hypothesis is supported. A null or small estimate is reported as evidence about the intervention.
- The change from M0 to M3 is reported for mathematics as the share of the raw association that the tighter comparisons remove.

---

## 10. Sensitivity runs

The primary model M3, for mathematics and pooled across subjects, on: the linked sample; all lecture formats (internet, hybrid, and interactive-television lectures added); CAP entrants excluded; entry-fall rows only; sections of 20 or more students.

---

## 11. Disclosure

The rules of the parent plan (Section 10) apply. In addition:

- the instructor identifier is replaced inside the query by a salted surrogate, exactly as the student identifier is, and instructor names are never read;
- no output is indexed by section or by instructor, and no instructor effect is released;
- every released cell holds at least 10 students.

---

## 12. Aggregates seen before the freeze

All outcome-blind. The Stage 0 query selects no grade field (`run_class_size.py --stage0-only`; outputs in `code/figures/module_c/class_size/stage0/`).

1. **Record.** The source holds a course reference number, a primary-instructor identifier, and a schedule type for every row. It holds no enrollment cap, room, or meeting time. Reference numbers identify sections one to one with course and section number, apart from a single key.
2. **Flow.** 196,134 first attempts in the first-year window across the 25 subjects (23,787 students); 196,125 held in one section; 194,996 in sections of more than 10 students; 177,289 in the primary set (23,766 students); 172,123 in course-by-term cells with two or more sections.
3. **Exposure in mathematics.** 27,580 eligible rows, 20,579 students, 1,143 sections, 74 instructors, 167 course-by-term cells of which 145 hold two or more sections. Section size at the 10th, 50th, and 90th percentile of rows: 30, 77, and 159. The standard deviation of log2 size is 0.90 overall, 0.55 within course-by-term cells, and 0.49 within cells and instructors. 67% of rows sit in sections above 45 students.
4. **Balance.** Within course-by-term cells in mathematics, a doubling of section size goes with +0.007 standard deviations of the entry mathematics score (standard error 0.013) and +0.010 of the verbal score (0.019): sections of different size hold students of the same preparation. First-generation status (−0.022 per doubling) and the CAP flag (+0.028) differ slightly. Pooled over the 25 subjects the mathematics score is lower in larger sections (−0.048, standard error 0.013), and in chemistry the difference reaches −0.109, so M2 and beyond are needed outside mathematics.
5. **Subjects outside the entry rule.** IS holds 113 students in the primary set. WRC, SPN, COM, and CS hold their sections to one size: the standard deviation of log2 size within cells and instructors is 0.10, 0.15, 0.15, and 0.16, against 0.49 in mathematics. These five stay out of the models, which leaves 20 subjects.
6. **From the manuscript.** The class-size curves by subject (mean section grade against section size, all enrolled students) were seen before this addendum; they motivate it. They compare sections across courses within a subject and involve no student-level model.
7. **Two real quantities seen in the first dry run.** The dry run shuffles grades within course-by-term cells, which leaves two quantities at their real values. (a) M0 compares courses with one another, so the shuffle does not change it: in mathematics it is −0.217 grade points per doubling of section size (standard error 0.022), the student-level form of the manuscript's curve. (b) The continuation outcome of Section 6 is built from enrollment, which the shuffle does not touch: students in larger origin sections are less likely to take a later mathematics course in the window (−0.030 per doubling, standard error 0.009). Both were seen after hypotheses H3 and H4 and the models were written and before the freeze. Continuation is therefore reported as a descriptive quantity outside the registered set, and it enters no verdict.

---

## 13. Dry runs on permuted outcomes

Recorded before the freeze. Every choice below was fixed while the pipeline ran on grades shuffled within course-by-term cells. None was informed by a within-course estimate on real grades.

1. **Final dry run.** With shuffled grades the mathematics M3 coefficient was −0.029 grade points per doubling (bootstrap interval −0.073 to +0.015; p = 0.21), the M4 interaction −0.003 (p = 0.69), and the pooled M3 coefficient over the 20 subjects −0.008 (−0.019 to +0.004). One of 40 M3 tests and no M4 interaction had a bootstrap p-value below 0.05, and no subject passed false-discovery control on either term. Neither hypothesis was supported and leniency was not indicated, as a shuffle requires.
2. **Why the bootstrap.** The first two dry runs showed the instructor-clustered t test rejecting too often. A calibration then drew 200 fresh shuffles in each of five subjects and was run twice. At the nominal 5% level the clustered t test rejected 7.5% and 8.0% of the time in mathematics (73 instructors), 8.5% and 5.5% in POL (24), 16.5% and 12.5% in CHE (19), 13.0% and 11.5% in ECO (17), and 17.0% and 19.0% in GRG (10). The wild cluster bootstrap rejected 6.5% and 2.5%, 6.5% and 2.0%, 6.0% and 5.0%, 7.5% and 6.5%, and 1.5% and 2.0% (`cs_calibration.csv`). The bootstrap therefore supplies every p-value and interval where it is implemented (Section 8).
3. **A test tried and dropped.** After the first dry run a randomization test permuted section sizes among the sections of each cell. It was dropped after the second: the size of a section is tied to the number of its own students in the data, so sizes cannot be reassigned across sections with the students held in place.
4. **Entry rule.** In the first dry run a subject whose sections are held to one size returned an extreme coefficient on shuffled grades (COM, −0.55). The exposure-variation condition of Section 2 was added in response, with its threshold read from the outcome-blind exposure table.
5. **Solvers agree.** The exact two-way solver behind the bootstrap reproduces the alternating-demeaning estimates to within 2 × 10⁻¹⁴.
6. **Resolution to expect.** Under the shuffle the mathematics M3 interval had a half-width of 0.044 grade points and 1.4 percentage points of DFW per doubling, and the scenario total over the 20 subjects had a half-width of about 270 DFW outcomes per entry cohort.
7. **Reproducibility.** A dry-run shuffle depends on the order in which the database returns rows, so two dry runs differ. Registered estimates do not depend on that order, and bootstrap draws are indexed by an instructor label built from section keys, so they reproduce across runs.
8. **Run time.** About 10 minutes.

---

## 14. Deviations

Append-only after the freeze: date, section, change, reason. Results from a deviating analysis are labeled exploratory.
