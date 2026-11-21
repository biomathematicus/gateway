# Student Success Figures

Python pipeline for the UTSA student-success analysis: chord diagrams of
major changes (replacing the MATLAB alluvial figure of `aDonorAcceptor.m`),
a clustered subject × major heatmap (generalizing tables 2.2–2.4 of the
original report), and a reproduction of the class-size figure.

## Running

```
python main.py          # regenerate every figure
python chord.py         # or run any figure module on its own
python heatmap.py
python classsize.py
python cohort_tables.py # LaTeX tables of the frozen-cohort baseline
```

[major_change_dfw.py](major_change_dfw.py) emits `tabMajorChangeDFW.tex`
(manuscript Table B3, the evidence behind the bridge paragraph of the
major-change section): for each subject, the share of reference-cohort
entrants who changed major, split by whether a first-year first attempt
in an introductory course ended in a D, F, withdrawal, or no-credit
outcome. Two populations are printed side by side, because the
comparison depends on which entrants remain observable: the
entrants observed enrolled at least one year after entry (a record in a
term one year or more after the entry term; a returning stop-out
qualifies), and all entrants with such an attempt. The script also
counts the students each cohort rule touches (records before entry,
missing major endpoints, two majors in one term) and repeats the
comparison under an entry-bounded rule that keeps confirmed changes
only. The first version printed "entrants with a DFW times the rate
difference"; that scaled contrast was removed because it reads as a
count of attributable changes. It queries SQL Server live, holds
student rows in memory only, writes aggregates with at least ten
students per cell (`major_change_dfw.csv`,
`major_change_dfw_stats.json`), and uses no dataframes and no cache.
Descriptive; computed after the analysis plans were frozen.

The body chord (`figChord-MAT-majors`) and its index table collect the
`CHORD_OTHER_SMALLEST` (14) majors with the smallest total flow in one
gray `Other` sector, because their arcs are too short to see; the
caption of the index table lists them.

[cohort_tables.py](cohort_tables.py) emits `tabCohortBaseline.tex`
(headline frozen quantities of the Fall 2014–Fall 2015 entry cohort) and
`tabOddsNaiveCohort.tex` (naive vs cohort-restricted odds ratios for
MAT/WRC/AIS, the capability-confounding worked example of Paper 0
Section 2). Both are `\input` by the manuscript; no number in them is
transcribed by hand.

- **Data:** local SQL Server, database `UTSA`, Windows trusted
  authentication; stored procedures `spDonorAcceptor` and `ClassRoomSize`,
  plus direct `OIR` queries for the cohort analyses.
- **Caching:** every query is pickled under `data/pkl/` ([db.py](db.py));
  after the first run the pipeline never touches the database. Delete a
  `.pkl` (or pass `refresh=True`) to re-query.
- **Outputs:** for each figure `<name>`, three files in
  `../figures/student_success/`: `<name>.pdf` (vector), `<name>.png`
  (preview, embedded below), `<name>.tex` (figure environment; include
  with `\input{figures/student_success/<name>.tex}`).

## Key parameters ([config.py](config.py))

| Parameter | Default | Meaning |
|---|---|---|
| `S_START`, `S_END` | 2014.66, 2019.66 | analysis window (x.0 Spring, .33 Summer, .66 Fall) |
| `CHORD_SUBJECT` | MAT | subject filter for the donor/acceptor chords |
| `CHORD_LABEL_SIZE` | 20 | sector label font (pt) for the archival chords |
| `CHORD_BODY_LABEL_SIZE` | 24 | sector label font (pt) for the body chord |
| `CHORD_ANCHOR_MAJOR`, `CHORD_ANCHOR_DEG` | None, 135 | major placed at the anchor angle; None = the longest name |
| `CHORD_OTHER_SMALLEST` | 14 | smallest majors collected in Other (body chord) |
| `TOP_N_MAJORS` | 24 | majors kept in the body chord; rest → Other |
| `COHORT_ENTRY_START/END` | Fall 2014–Fall 2015 | first-time-freshman entry cohort (heatmap) |
| `COHORT_HORIZON_YEARS` | 4 | observation window after entry |
| `HP_LAMBDA` (in [classsize.py](classsize.py)) | 1e4 | Hodrick–Prescott smoothing |

---

## Chord diagrams — source: [chord.py](chord.py)

One row of data = one student who took `CHORD_SUBJECT` courses and whose
first major differs from their last (donor → acceptor). **Arc length ∝
students exchanged (donated + received). Ribbons start wide at the donor,
narrow to an arrowhead at the acceptor, and carry the donor's color.**
Sectors are **ordered by size, descending clockwise**, and the ring is
rotated rigidly so that `CHORD_ANCHOR_MAJOR` sits at `CHORD_ANCHOR_DEG`
(measured counter-clockwise from 3 o'clock); ordering is unaffected.
Sectors are colored by college (Sciences blue, Business orange, Engineering aqua,
Liberal & Fine Arts yellow, Education magenta, University College green,
Architecture violet, Public Policy red; gray = admin units and the Other
band). Multi-word names wrap two words per line.

### `figChord-MAT-majors` — body figure (manuscript Figure 3)

![body chord](../figures/student_success/figChord-MAT-majors.png)

Every sector is labeled with the **name** of its major. The single-word
codes used before 2026-11-20 (`config.MAJOR_WORD`, `figChord-MAT-short`,
`tabMajorGlossary.tex`) were retired because some majors hold several
registrar subject codes; the last outputs of that version are kept in
`../figures/student_success/_superseded_major_codes/`. The ring is
rotated so that the major with the longest name sits at
`CHORD_ANCHOR_DEG` (135°, the page's upper-left diagonal, where a radial
label has the most room); set `CHORD_ANCHOR_MAJOR` to pin another major.
Names stay on one line in the upper-left quadrant and on sectors narrower
than `NARROW_DEG`; elsewhere they wrap two words per line.
`chord.major_tables()` emits the companion index `tabMajorAngles.tex`
(major name → angular position and size) from the same geometry, so the
figure and its index cannot drift apart.

Formats: `figChord-MAT-majors.pdf` is vector and is the file the
manuscript includes; `figChord-MAT-majors.svg` is a second vector copy
that editors and browsers open directly; `figChord-MAT-majors.png` is a
raster copy at `CHORD_BODY_PNG_DPI` (600 dpi, about 14,500 pixels on a
side and 50 MB). To inspect detail, open the PDF or the SVG.

### `figChord-MAT-top24` — appendix figure, aggregated

![top-25 chord](../figures/student_success/figChord-MAT-top24.png)

Top `TOP_N_MAJORS` majors by total flow, ordered by size from north clockwise with the aggregate Other band last; the tail is
aggregated into the gray **Other** band. Ticks count students (1 tick =
1,000).

### `figChord-MAT-all` — appendix figure, every major

![full chord](../figures/student_success/figChord-MAT-all.png)

All ~70 majors, no aggregation. Vector PDF — read by zooming.

---

## Heatmap: subject × major GPA deviation — source: [heatmap.py](heatmap.py)

### `figHeatmapSubjectMajor-changers`

![heatmap](../figures/student_success/figHeatmapSubjectMajor-changers.png)

Generalizes report tables 2.2–2.4 from three subjects to the whole
matrix. Population: first-time freshmen entering Fall 2014–Fall 2015
(N = 10,027) who **changed major** within the declared observation
window (entry through the fall term four years after entry,
inclusive). Cell = mean of (GPA in
the row subject − the student's leave-one-out mean GPA in other subjects)
over changers whose first major is the column; red = the subject grades
below the student's own norm (a barrier for that major's leavers), blue =
above; cells with < 15 students are blank.

- **Σrow** (left column) sums each row across majors — a one-number
  barrier score per subject: **MAT −14.2** and **POL −11.8** at one
  extreme, **AIS +13.4** and **IS +12.7** at the other.
- Ward clustering (dendrograms at the margins) exposes the block
  structure: a red **barrier block** (MAT red across essentially every
  donor major; the science core red mainly for STEM/business-major
  leavers; deepest single cells CS×Mathematics and CS×Computer Science),
  a blue **refuge block** (AIS, IS, SOC, ART, GBA, MUS, COM, ENG, HIS),
  and a column split — leavers of arts/humanities majors show flat
  profiles, so the barrier phenomenon is concentrated among
  STEM/business/health leavers.

---

## Class size — source: [classsize.py](classsize.py)

### `figClassSizeUTSA` — reproduction of report Figure 2.3-15

![class size](../figures/student_success/figClassSizeUTSA.png)

Port of `aClassSize.m` ('%' branch): mean section GPA vs. class size
(sections > 10 students), binned in 5-student increments, interpolated,
and smoothed with the Hodrick–Prescott filter (the same pentadiagonal
solve as MATLAB). Line width = 10 × enrollment share; every curve labeled
at its end; **MAT in red**, running far below every other subject across
the entire class-size range.

**Choosing λ (`HP_LAMBDA`):** as λ → ∞ the Hodrick–Prescott filter
converges to a straight line — equivalent to fitting a linear regression
through the binned means. The default **λ = 10⁴** is deliberately lower:
it suppresses bin-to-bin noise while retaining the curvature of the
trend (e.g. MAT's dip around 150–250-student sections), which a straight
line would erase.

Provenance note: verified against a fresh MATLAB run on the same
database — curve endpoints agree. The *published* 2020 figure differs
because the database has been re-imported since (its MAT curve ended at
~155 students; today's `OIR` has MAT sections up to 240) and the code
used a different λ.

---

## Statistical notes

| Step | MATLAB | Python |
|---|---|---|
| Rank-sum test | `ranksum` | `scipy.stats.mannwhitneyu(method="asymptotic")` |
| Welch's *t* (panel gaps) | — | `scipy.stats.ttest_ind(equal_var=False)` |
| Fisher exact | `fishertest` | `scipy.stats.fisher_exact` |
| FDR | `funFDRBH` (BH) | `statsmodels multipletests(method="fdr_bh")` |
| Hodrick–Prescott | `funHodrickPrescott` | same pentadiagonal solve, ported |
| Term codes | `funDate2String` | `db.term_str` |

[data.py](data.py) retains the full statistical toolkit built during the
analysis (donor/acceptor stats, cohort-restricted odds ratios, per-subject
GPA panels by course level) — usable for tables or future figures even
though the polar plots that displayed them were retired.

Module map: [config.py](config.py) parameters · [db.py](db.py) pyodbc +
pkl cache · [data.py](data.py) queries + statistics ·
[chord.py](chord.py) / [heatmap.py](heatmap.py) /
[classsize.py](classsize.py) figures · [texout.py](texout.py) PDF/PNG/TeX
export · [main.py](main.py) driver.
