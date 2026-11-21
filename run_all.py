"""Master script: every program of the study, in dependency order.

    python run_all.py --list                 the stages and their steps
    python run_all.py --stage macros         one stage
    python run_all.py --stage context macros several stages, in pipeline order
    python run_all.py --from institution     that stage and every later one
    python run_all.py                        everything
    python run_all.py --dry-run ...          print the commands only

Each step is one program under programs/, run with the Python that runs
this script, from the programs folder. A stage stops at its first failing
step. What a stage needs is stated in its `needs` line:

    raw          the raw public files under data/ (see data_manifest.csv;
                 set GATEWAY_DATA when they live elsewhere)
    database     the project PostgreSQL database (programs/env/config.toml)
    institution  the institutional student records (restricted; available
                 only to the authorized team)
    scorecard    the College Scorecard archive listed in data_manifest.csv

A reader without the restricted records can run `schema`, `ingest`,
`context`, and `macros`; the outputs of the other stages are the aggregate
files already under programs/figures/. Compiling a manuscript is an
option, with the folder that holds its main.tex:

    python run_all.py --stage macros --manuscript <folder>

`scorecard` also names a service: the Scorecard tables live in a second
PostgreSQL cluster (programs/paper0/pg.py, section [scorecard] of
programs/env/config.toml).
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROGRAMS = ROOT / "programs"


def sql(path):
    """a step that runs one SQL file against the project database"""
    return [sys.executable, "-c",
            "from gateway import db; db.exec_file(r'%s')" % path]


def py(script, *args):
    return [sys.executable, script, *args]


# (name, what it does, what it needs, steps)
STAGES = [
    ("schema", "Schemas and dimension tables of the project database",
     "database", [
         sql("sql/001_schema.sql"),
     ]),
    ("ingest", "Public data into the project database",
     "raw, database", [
         py("ingest/saipe.py"),              # child poverty by district
         py("ingest/crdc.py"),               # CRDC school counts
         sql("sql/002_mart.sql"),
         py("ingest/crdc_panel.py"),         # Algebra II, five cycles
         sql("sql/003_mart_panel.sql"),
         py("ingest/crdc_courses.py"),       # every course family
         py("ingest/edge_schools.py"),       # school directory and points
         py("ingest/oa_nmdb.py"),            # Opportunity Atlas, tract level
         py("ingest/zip_tract_xwalk.py"),    # ZCTA to tract weights
         sql("sql/004_oa_zcta.sql"),         # Atlas aggregated to ZCTA
         py("ingest/tract_district_xwalk.py"),
         py("paper0/load_scorecard.py"),     # needs: scorecard
     ]),
    ("context", "District and national context: Figures 1 and 2, "
                "robustness, national position, data inventory",
     "database, raw (the CRDC 2015-16 school file)", [
         py("paper0/oa_figure.py"),              # district income file
         py("paper0/course_panels_figure.py"),   # Figure 1
         py("paper0/course_gradient_figure.py"),  # Figure 2 and gradients
         py("analysis/stability.py"),
         py("analysis/algebra2_robust.py"),
         py("paper0/scorecard.py"),
         py("ingest/data_inventory.py"),
         py("ingest/source_inventory.py"),       # data_sources.csv
     ]),
    ("crosswalk", "High-school names to NCES schools",
     "institution, database", [
         py("xwalk/hs_crosswalk.py"),
         py("xwalk/adjudicate_006.py"),
         py("xwalk/fallback_vintages.py"),
         py("xwalk/ccd_recovery.py"),
         # stability of school provision across CRDC cycles; it reads the
         # matched schools of the crosswalk
         py("student_success/provision_stability.py"),
         # distance from the home ZIP to the matched school. It writes
         # figures/008_coord_distances.csv, which the data step of the
         # models reads (module_c/mc_data.py). The file is internal: it
         # lists pairs of ZIP code and school with their counts, it is
         # ignored by git, and it is never released.
         py("analysis/zip_hs_distance_coords.py"),
     ]),
    ("institution", "Institutional baseline and linkage profile "
                    "(students active Fall 2014 to Fall 2019)",
     "institution, database", [
         py("student_success/main.py"),          # Figures 3, 4, 5 inputs
         py("student_success/cohort_tables.py"),
         py("student_success/cohort_window_audit.py"),
         py("student_success/major_change_dfw.py"),
         py("student_success/persistence_dfw.py"),
         py("student_success/linkage_profile.py"),
         py("paper0/provision_figure.py"),       # Figure B1
         py("paper0/sending_poverty.py"),        # Figure B2
         py("module_c/cohort_notes.py"),
     ]),
    ("models", "Linked entrant models and section-size models "
               "(prespecified; about one hour)",
     "institution, database", [
         py("module_c/run_module_c.py", "--first-cohort", "2014",
            "--tag", "cohorts_2014_2019"),
         py("module_c/rev5_module_c.py"),
         py("module_c/mc_figures.py", "cohorts_2014_2019", "rev5"),
         py("module_c/run_class_size.py"),
         py("module_c/rev5_class_size.py", "--calibrate"),
         py("module_c/cs_figures.py", "registered", "rev5"),
     ]),
    ("macros", "Numbers of the manuscript as TeX macros "
               "(programs/figures/macros)",
     "the outputs under programs/figures", [
         py("macros/make_macros.py"),
     ]),
]
NAMES = [s[0] for s in STAGES]


def show():
    for name, what, needs, steps in STAGES:
        print(f"{name}: {what}\n    needs: {needs}")
        for s in steps:
            print("    ", " ".join(s[1:]) if s[1] != "-c" else
                  "sql " + s[2].split("'")[1])


def run(names, dry):
    for name, what, needs, steps in STAGES:
        if name not in names:
            continue
        print(f"\n=== {name}: {what}", flush=True)
        for s in steps:
            label = " ".join(s[1:]) if s[1] != "-c" else (
                "sql " + s[2].split("'")[1])
            print(f"--- {label}", flush=True)
            if dry:
                continue
            t0 = time.time()
            r = subprocess.run(s, cwd=PROGRAMS)
            if r.returncode:
                print(f"FAILED ({r.returncode}): {label}")
                return r.returncode
            print(f"    done in {time.time() - t0:.0f} s", flush=True)
    return 0


def manuscript(path, dry):
    """compile a manuscript that reads programs/figures (optional)"""
    cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
           "main.tex"]
    print("\n=== manuscript:", path, flush=True)
    if dry:
        return 0
    return subprocess.run(cmd, cwd=path).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--stage", nargs="+", choices=NAMES, metavar="STAGE")
    ap.add_argument("--from", dest="start", choices=NAMES, metavar="STAGE")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--manuscript", metavar="FOLDER",
                    help="also compile main.tex in this folder")
    a = ap.parse_args()
    if a.list:
        show()
        return 0
    names = (a.stage if a.stage else
             NAMES[NAMES.index(a.start):] if a.start else NAMES)
    rc = run(names, a.dry_run)
    if rc == 0 and a.manuscript:
        rc = manuscript(a.manuscript, a.dry_run)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
