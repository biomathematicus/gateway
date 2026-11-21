# Module C, Stage 0: draft maps for PI review

Date: 2026-11-18. Companion to `analysis_plan.md` (version 0.2).
Everything here comes from outcome-blind counts: no predictor was related to any outcome.
Population for the counts: first-time fall entrants, Fall 2009 to Fall 2018 (46,078 students with a first-year course row; 422,683 lower-division rows in the first-year window).

Items marked **Review** need the PI's confirmation before the freeze.

---

## 1. Grade-code map

| Code | Rows | Quality points | In grade average | Grade outcome | DFW outcome |
|---|---:|---:|---|---|---|
| A+ | 8,784 | 4.00 | yes | 4.00 | 0 |
| A | 111,208 | 4.00 | yes | 4.00 | 0 |
| A- | 10,805 | 3.67 | yes | 3.67 | 0 |
| B+ | 9,174 | 3.33 | yes | 3.33 | 0 |
| B | 103,571 | 3.00 | yes | 3.00 | 0 |
| B- | 8,248 | 2.67 | yes | 2.67 | 0 |
| C+ | 5,586 | 2.33 | yes | 2.33 | 0 |
| C | 67,930 | 2.00 | yes | 2.00 | 0 |
| C- | 4,135 | 1.67 | yes | 1.67 | 0 |
| D+ | 1,661 | 1.33 | yes | 1.33 | 1 |
| D | 25,718 | 1.00 | yes | 1.00 | 1 |
| D- | 1,322 | 0.67 | yes | 0.67 | 1 |
| F | 28,211 | 0.00 | yes | 0.00 | 1 |
| W (withdrawal) | 24,928 | 0.00 | no | excluded | 1 |
| NC (no credit) | 3,069 | 0.00 | no | excluded | 1 |
| CR (credit) | 8,261 | 0.00 | no | excluded | 0 |
| IN, NR | 72 | 0.00 | no | excluded | excluded |

- Quality points are on the 4-point scale per course; they are not multiplied by credit hours.
- **Review:** NC counted with DFW, and CR counted as success.

**Repeat indicator.** Blank on 398,080 rows, `E` on 13,991, `I` on 10,611. It marks whether a row counts in the grade average after a repeat, so the first attempt is identified by term order.

---

## 2. Entry mathematics level (ordinal, by first mathematics course in the first-year window)

| Level | Courses (students in the first-year window) |
|---|---|
| 0, developmental | 0203 Basic Mathematics (846); 0213 Intermediate Algebra (6,917) |
| 1, college algebra tier | 1023 College Algebra with Applications (7,189); 1033 Algebra with Calculus for Business (6,146); 1043 Introduction to Mathematics (2,593); 1053 Mathematics for Business (606); 1073 Algebra for Scientists and Engineers (12,808); 1153, 1163 Essential Elements in Mathematics I, II (298) |
| 2, precalculus | 1093 Precalculus (8,838) |
| 3, first calculus | 1133 Calculus for Business (468); 1193, 1194 Calculus for the Biosciences (912); 1214 Calculus I (4,777) |
| 4, beyond first calculus | 1223, 1224 Calculus II (3,141); 2213, 2214 Calculus III (451); 2233 Linear Algebra (75) |

Entrants with no mathematics course in the first-year window form a separate category.

**Review:** the placement of the business and bioscience calculus courses at level 3, and of 1033 at level 1.

---

## 3. Subjects clearing the 1,000-student minimum

Counts are for all fall entrants. The linked sample is smaller, so the four subjects nearest the line (CLA, ME, BBL, GES) may drop out when the linked counts are run.

| Class (proposed) | Subjects (students) |
|---|---|
| Quantitative | MAT 39,846; CHE 16,685; ECO 11,546; STA 4,833; PHY 3,430; CS 2,998; ACC 1,938; ME 1,261 |
| Other | WRC 31,339; POL 28,808; HIS 28,211; AIS 21,854; BIO 18,724; PSY 14,350; SOC 13,021; GEO 7,432; ANT 6,553; IS 5,371; MUS 4,748; COR 4,488; AHC 4,179; SPN 3,999; ENG 3,062; KIN 2,969; ES 2,947; GRG 2,627; ART 2,514; AST 1,953; CRJ 1,952; COM 1,927; CLA 1,358; BBL 1,079; GES 1,017 |

33 subjects clear the minimum; 23 more hold 300 to 999 students and stay out of the primary analysis.

**Review:** the quantitative class. The proposed rule is a mathematics prerequisite or corequisite for the subject's lower-division courses. BIO, GEO, AST, ES, and IS are the cases to decide.

---

## 4. Remaining Stage 0 work

- Load the CRDC 2013-14 cycle into the course tables.
- Build the term dimension.
- Run the sample flow on the linked sample, including linked subject counts.
- Reconcile the provisional cohort against the official census cohort when it is available.
- Write the pipeline and run it end to end on permuted outcomes; record the code state.
- Register the plan.
