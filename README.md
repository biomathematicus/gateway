# Gateway

Source code of the study *A Calculus Gradient: Child Poverty, Mathematics
Preparation, and First-Year College Performance at a Hispanic-Serving
University*.

The study relates the child poverty of school districts to the courses
their high schools enroll students in, links the entrants of one public
university to their sending schools and districts, and describes first-year
outcomes at that university for students active between Fall 2014 and
Fall 2019. This repository holds every program that produced a number, a
table, or a figure of the manuscript.

## Layout

```
run_all.py            master script: every program, in dependency order
data_sources.csv      every raw public file a program reads: dataset,
                      vintage, path, SHA-256, size, source address
data_manifest.csv     acquisition records of the six archives acquired for
                      the study (license, schema, lineage)
prespecification/     analysis plan, addendum, and registration records of
                      the linked models and the section-size models
programs/
  env/                configuration of the project database
  sql/                schemas, marts, and context tables
  gateway/            access to the project database
  ingest/             loaders of the public data; data inventory
  xwalk/              high-school names to NCES school identifiers
  analysis/           district analyses of course enrollment and poverty
  paper0/             context figures (district course gradients, national
                      position, sending profiles)
  student_success/    institutional baseline and linkage profile
  module_c/           linked entrant models and section-size models
  macros/             numbers of the manuscript as TeX macros
  tools/              disclosure scan and the list of released outputs
  figures/            released outputs: figures, TeX snippets, aggregate
                      statistics (RELEASE.txt, RELEASE_MANIFEST.csv)
```

## How a number reaches the manuscript

No number that a program computes is typed in the manuscript.

1. An analysis program writes its results to `programs/figures/` as a
   statistics file (`*_stats.json`, a results CSV) beside each figure.
2. A macro module `programs/macros/m_<analysis>.py` reads those files and
   names each quantity the text prints. A parameter of an analysis (a
   threshold, the number of bootstrap draws) is read from the constant of
   the program that uses it.
3. `programs/macros/make_macros.py` writes two files per module under
   `programs/figures/macros/`. `<analysis>_newcommands.tex` declares each
   macro with `\newcommand` and gives every one the same initial value,
   `\WarningRunPipeline`: the words **[RUN THE PIPELINE]** in bold red.
   `<analysis>_renewcommands.tex` assigns each value with `\renewcommand`.
   The index file `newcommands.tex` defines the warning (the document
   loads `xcolor`), and the two index files input the files of every
   module.
4. The manuscript loads the declarations in its preamble and the values
   after `\begin{document}`, and its text says `\CalcMeanPerHundred{}`
   where a reader sees a number. A quantity that no program supplied
   prints as the red warning wherever the text uses it, so a missing run
   of the pipeline is conspicuous in the PDF.

```
python run_all.py --stage macros
```

regenerates the macro files from the outputs on disk.

## Running the programs

```
python run_all.py --list              # stages and steps
python run_all.py --stage context     # one stage
python run_all.py --from institution  # a stage and every later one
python run_all.py                     # everything
python run_all.py --dry-run           # print the commands only
python run_all.py --stage macros --manuscript <folder>
```

The last form writes the macros and then compiles the manuscript whose
`main.tex` is in the named folder. Compiling is an option of the script;
the stages are the seven of the table.

| Stage | What it does | Needs |
|---|---|---|
| `schema` | schemas of the project database | project database |
| `ingest` | loads the public data | raw public files, project database |
| `context` | district course gradients, robustness checks, national position, data inventory, inventory of the public input files | project database, raw public files |
| `crosswalk` | resolves high-school names to NCES schools; writes the internal distance file that the models read | institutional records, project database |
| `institution` | institutional baseline and linkage profile | institutional records, project database |
| `models` | linked entrant models and section-size models | institutional records, project database |
| `macros` | writes the TeX macros | the outputs under `programs/figures/` |

A reader without the restricted records can run `schema`, `ingest`,
`context`, and `macros`. The outputs of the other stages are the aggregate
files already under `programs/figures/`.

### Requirements

- Python 3.11 with numpy, scipy, matplotlib, pandas, statsmodels,
  pycirclize, and three database drivers: `psycopg2` (project database),
  `psycopg` version 3 (Scorecard tables), and `pyodbc` (institutional
  records). The check of the flow diagram reads the PDF with PyMuPDF.
- PostgreSQL 16 with PostGIS.
- A TeX distribution with `latexmk`, to compile a manuscript.

### Two database services

The programs use two PostgreSQL services, both configured in
`programs/env/config.toml`. Copy `programs/env/config.example.toml` to
that name and set the values of your installation.

| Service | Section | Module | Holds |
|---|---|---|---|
| Project database | `[db]` | `programs/gateway/db.py` (`psycopg2`) | the public data and the aggregate context tables |
| Scorecard cluster | `[scorecard]` | `programs/paper0/pg.py` (`psycopg`) | the College Scorecard tables |

The password of the project database is read from
`programs/env/secrets.env` (a line `PGPASSWORD=...`), which is never
tracked. The Scorecard cluster is a user-space cluster with trust
authentication on localhost. Every key of `[scorecard]` has a default
(port 5434, database `paper0`, the operating-system user, the PostgreSQL
programs found on the `PATH`), and `pg.py` starts the server when it is
down.

The institutional records are read from a SQL Server instance through
`pyodbc`, by the authorized team only
(`programs/student_success/config.py`).

### Where the raw public files go

The loaders look for the raw files in the folder named by the environment
variable `GATEWAY_DATA`. Without that variable they use `data/` beside
`programs/` (`programs/gateway/paths.py`). `data_sources.csv` names each
file with its path from that folder. Three points need attention:

- The College Scorecard archive goes in `data/scorecard/`.
- The `crosswalk` stage writes `programs/figures/008_coord_distances.csv`,
  the distance from each home ZIP code to the matched school, which the
  data step of the models reads. The file lists pairs of ZIP code and
  school with their counts, so it is internal: git ignores it and it is
  never released. A rebuild of the `models` stage needs the `crosswalk`
  stage to have run on the same machine.
- `programs/ingest/crdc_courses.py` reads `data/CRDC` beside `programs/`
  and ignores `GATEWAY_DATA`. Its hash is on record in the registration of
  the analysis plan, so the file is left as it is. When the raw files live
  elsewhere, link or copy the CRDC folder to that place.

### A fresh run of the institutional programs

The older institutional programs (`student_success/main.py` and
`cohort_tables.py`, with the figure modules they call) read the records
through a local cache, in the folder
named by `GATEWAY_CACHE` (default: a folder of the local user profile,
outside the repository). Each cache file is stored with the SHA-256 of the
query that produced it, and a program reads the database again whenever
its query differs from the recorded one. The hash identifies the query;
it cannot tell that the source tables changed. For the run that a
manuscript reports, set `GATEWAY_CACHE` to an empty folder outside the
repository, or set `GATEWAY_REFRESH=1`, which reads every query again.
Then run

```
python run_all.py --from institution
```

The outputs released here were checked this way on 2026-11-20: a run from
an empty cache reproduced every table, statistics file, and backing data
file of those programs byte for byte.

Every program has been run on the machine of the analysis. The complete
sequence has not yet been run on a second machine by an authorized
analyst; that test is the remaining step before the rebuild can be called
portable.

## Data

**Public data.** `data_sources.csv` lists every raw public file that a
program reads (378 files): the Civil Rights Data Collection, the Small
Area Income and Poverty Estimates, the NCES EDGE school locations and
geographic relationship file, the CCD school directories, the Opportunity
Atlas, Census relationship and gazetteer files, and the College Scorecard.
Each row gives the dataset, the vintage, the path from the raw data
folder, the SHA-256, the size, the rows loaded, the source address, and
the program that reads the file. Most rows come from the registry that the
loaders fill in the project database (`core.source_file`); the files that
a program reads without registering them are hashed by
`programs/ingest/source_inventory.py`, which writes the inventory and
checks every hash against the file on disk (column `check`).
`data_manifest.csv` holds the fuller acquisition records (license, schema,
lineage) of the six archives acquired for the study. The files are not
redistributed here.

**Institutional records.** The student records of the university are
restricted and are not in this repository. The programs that read them
(`crosswalk`, `institution`, `models`) run only for the authorized team.
Their outputs under `programs/figures/` are aggregates.

**Disclosure rules.** Student rows are read into memory, reduced to
aggregates, and discarded. Income is banded or ranked before any use and
is never tabulated. Instructor identifiers are replaced by surrogates
inside the query, and no output is indexed by section or by instructor.
The local cache of the older figure programs holds student-level rows; it
lives outside the repository (the folder named by `GATEWAY_CACHE`).

**Released outputs and internal outputs.** Running the programs fills
`programs/figures/` with working files. Some of the older diagnostic
programs write counts for fewer than ten students (pairs of ZIP codes,
school names, small cells of a table). Those files are internal to the
authorized team, and git ignores everything under `programs/figures/` by
pattern. The repository tracks only the released outputs:

- the files the macro modules read, and the macro files;
- the figures and TeX snippets the manuscript includes, with the backing
  aggregate file of each figure.

`programs/figures/RELEASE.txt` lists them, and
`programs/figures/RELEASE_MANIFEST.csv` names, for each figure and table
of the manuscript, its label, the program that generates it, its released
inputs, and what those inputs hold. For most exhibits they hold the values
shown. For three (the heatmap, the class-size curves, and the cohort
table) they hold summary statistics, and redrawing the exhibit needs the
institutional records. Every released count of students rests on at least
ten students; smaller cells are pooled or withheld.

A figure can state a count through its geometry. The ribbons of the flow
diagram are counts of students, so `student_success/chord.py` draws only
the flows of at least ten students and sizes each sector by the drawn
flows, and `programs/tools/chord_geometry_check.py` recovers the count of
every ribbon from the PDF and compares it with the released flows file.

```
python programs/tools/release_files.py <manuscript folder> --stage
python programs/tools/release_files.py <manuscript folder> --check
```

The first command rebuilds the list, scans every CSV and JSON file on it
for student counts below ten (`programs/tools/disclosure_scan.py`), runs
the check of the flow diagram, stops at a hit, and adds the listed files
to the git index. The second changes
nothing and fails when the tracked files differ from the list or when the
scan finds a small cell. Build any package for others from the repository
with `git archive`, so that it holds the tracked files only.

## Prespecified analyses

The linked entrant models and the section-size models were specified
before estimation. `prespecification/` holds the analysis plan, the
section-size addendum, the two registration records with the SHA-256 of
each registered file, and the dated list of deviations (Section 17 of the
plan).

What is preserved in its frozen state, and what is identified by hash:

- **Record of the addendum** (`class_size_registration.md`). Every file it
  names is in `prespecification/frozen/` in the registered state, and the
  five programs under `programs/module_c/` (`mc_data.py`, `mc_models.py`,
  `run_module_c.py`, `cs_data.py`, `run_class_size.py`) still match its
  hashes.
- **Record of the original plan** (`registration_event.md`).
  `stage0_maps.md` and `mc_models.py` are preserved in the registered
  state. The plan, `mc_data.py`, and `run_module_c.py` were amended by
  deviation D1, and `ingest/crdc_courses.py` was extended afterward
  (record A2 of Section 17). The repository holds their current versions.
  Their states at the first registration are identified by the recorded
  hashes and are not included; `prespecification/frozen/README.md` lists
  them. Until those versions are restored, a reader can verify the
  registered state of the models through the record of the addendum and
  cannot recompute the first three hashes.

Corrections made after review are in separate programs
(`rev5_module_c.py`, `rev5_class_size.py`) and are recorded as deviations
in the plan. The registered programs and the registration records name
the plan by its path at registration (`Economics/Paper0/module_c/`); the
same documents are the ones under `prespecification/`.

## Checking the rule on numbers

```
python programs/macros/check_numbers.py <manuscript folder>
```

lists every number still typed in the manuscript sources that is not on
the list of literals that stay text (`programs/macros/kept_numbers.tsv`:
calendar labels, names that hold digits, units, numerals of formulas,
statistics quoted from cited sources, statistical conventions).

## Adapting the pipeline to another institution

The public-data stages run as they are. The institutional stages need that
institution's field definitions (terms, grades, entry scores, credit
fields), its course maps, and a validation of the school-name linkage on
its own records; `programs/student_success/linkage_profile.py` is the
program to start from.

## License

GNU General Public License, version 3 (see `LICENSE`).
