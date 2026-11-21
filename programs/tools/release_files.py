"""The released outputs: which files under programs/figures belong in the
repository, and the manifest of the exhibits.

    python programs/tools/release_files.py [manuscript folder] [--stage]
    python programs/tools/release_files.py [manuscript folder] --check

Running the programs fills programs/figures with working files. Some of
the older diagnostic programs write counts for fewer than ten students
(pairs of ZIP codes, school names, small cells of a table). Those files are
internal: nothing under programs/figures is tracked by pattern, and only
the files this program lists are released.

Two kinds of file are released:
  * the files the macro modules read (found by building every module of
    programs/macros with the readers of texmacros recording their paths),
    and the macro files themselves;
  * the files a manuscript includes (its \\input of generated TeX
    snippets and the graphics those snippets and its sections include),
    with the backing aggregate files of each included figure
    (<figure>_*.csv and <figure>_*.json), when a manuscript folder is
    given.

Before the list is accepted, every CSV and JSON file on it is scanned for
counts of students under the minimum cell (the rule and the column names
of tools/disclosure_scan.py; in JSON files, every key that names students
or entrants). A figure can also state a count through its geometry: the
ribbons of a chord diagram are counts of students, so the counts are
recovered from the released PDF and held to the same minimum
(tools/chord_geometry_check.py). A hit of either kind stops the program.

The manifest names, for each figure and table of the manuscript, its
generating program and its released inputs (INPUTS for the inputs whose
files have other names), and says whether those inputs hold the values
shown or summary statistics only.

Written to programs/figures:
    RELEASE.txt            the released files
    RELEASE_MANIFEST.csv   each figure and table of the manuscript with
                           its label, the program that generates it, and
                           its backing files

--stage adds the listed files to the git index (they are ignored by
pattern, so they are added by name). --check changes nothing: it fails
when the files git tracks under programs/figures differ from the list, or
when the scan finds a small cell. Build any package for others from the
repository with `git archive`, so that it holds the tracked files only.
"""
import csv
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROGRAMS = HERE.parent
FIG = PROGRAMS / "figures"
sys.path.insert(0, str(PROGRAMS / "macros"))
sys.path.insert(0, str(HERE))

LISTS = ("RELEASE.txt", "RELEASE_MANIFEST.csv")

#: the program that generates each exhibit, by the name of its file
GENERATORS = {
    "figCalculusPanels": "paper0/course_panels_figure.py",
    "figCourseGradients": "paper0/course_gradient_figure.py",
    "figProvisionBands": "paper0/provision_figure.py, from the aggregates "
                         "of student_success/linkage_profile.py",
    "figSendingPoverty": "paper0/sending_poverty.py, from the aggregates "
                         "of student_success/linkage_profile.py",
    "figScorecardLocator": "paper0/scorecard.py",
    "figChord-MAT-majors": "student_success/chord.py",
    "tabMajorAngles": "student_success/chord.py",
    "figHeatmapSubjectMajor-changers": "student_success/heatmap.py",
    "figClassSizeUTSA": "student_success/classsize.py",
    "figPersistenceDFW": "student_success/persistence_dfw.py",
    "tabPersistenceDFW": "student_success/persistence_dfw.py",
    "tabMajorChangeDFW": "student_success/major_change_dfw.py",
    "tabCohortBaseline": "student_success/cohort_tables.py",
    "tabOddsNaiveCohort": "student_success/cohort_tables.py",
    "figPreparationVariance": "module_c/mc_figures.py cohorts_2014_2019 rev5",
    "figSubjectPredictors": "module_c/mc_figures.py cohorts_2014_2019 rev5",
    "tabSubjectPooled": "module_c/mc_figures.py cohorts_2014_2019 rev5",
    "figClassSizeLadder": "module_c/cs_figures.py registered rev5",
    "tabClassSizeScenario": "module_c/cs_figures.py registered rev5",
}


#: Inputs of an exhibit whose files do not share its name. Every file
#: named here is released with the exhibit (and scanned like the rest).
#: Files named <exhibit>_* in the exhibit's folder are found without help.
MC, CS, SS = ("module_c/cohorts_2014_2019/", "module_c/class_size/",
              "student_success/")
INPUTS = {
    "figPreparationVariance": [MC + "q1_variance_partition.csv"],
    "figSubjectPredictors": [MC + "q2_primary.csv", MC + "q2_coefficients.csv",
                             MC + "results.json"],
    "tabSubjectPooled": [MC + "q2_pooled.csv", MC + "q2_primary.csv",
                         "module_c/rev5/q2_pooled_joint.csv"],
    "figClassSizeLadder": [CS + "registered/cs_primary.csv",
                           CS + "registered/cs_student_fe.csv",
                           CS + "registered/cs_pooled.csv",
                           CS + "registered/cs_projection.csv",
                           CS + "registered/results.json",
                           CS + "rev5/cs_pooled_joint.csv",
                           CS + "rev5/cs_contrasts.csv",
                           CS + "rev5/cs_section_sizes.csv"],
    "tabClassSizeScenario": [CS + "registered/cs_projection.csv",
                             CS + "registered/cs_projection_mat_thirds.csv",
                             CS + "registered/results.json",
                             CS + "rev5/cs_contrasts.csv"],
    "tabCohortBaseline": [SS + "tabOddsNaiveCohort_stats.json",
                          SS + "cohort_window_audit.json"],
    "tabMajorAngles": [SS + "figChord-MAT-majors_flows.csv",
                       SS + "figChord-MAT-majors_stats.json"],
    "tabMajorChangeDFW": [SS + "major_change_dfw.csv",
                          SS + "major_change_dfw_stats.json"],
    "tabPersistenceDFW": [SS + "persistence_dfw.csv",
                          SS + "persistence_dfw_stats.json"],
}

#: What the released inputs of an exhibit hold. "values shown": the
#: exhibit can be redrawn from them. "summary statistics": they hold the
#: quantities the text quotes, and the exhibit itself can be redrawn only
#: with authorized access to the institutional records.
SUMMARY_ONLY = {
    "figHeatmapSubjectMajor-changers":
        "summary statistics (the row summaries; the cells of the matrix "
        "need the institutional records)",
    "figClassSizeUTSA":
        "summary statistics (settings and the values quoted; the binned "
        "curves need the institutional records)",
    "tabCohortBaseline":
        "summary statistics (the odds-ratio tables and the window audit; "
        "the other rows of the table need the institutional records)",
}


def exhibit_inputs(files) -> set:
    """the files of INPUTS for the exhibits on the list"""
    stems = {Path(f).stem for f in files}
    return {f for stem, names in INPUTS.items() if stem in stems
            for f in names}


def macro_sources() -> set:
    """files read by the macro modules, relative to programs/figures"""
    import texmacros as T
    seen = set()
    j, c = T.J, T.C

    def J(rel):
        seen.add(rel)
        return j(rel)

    def C(rel):
        seen.add(rel)
        return c(rel)

    T.J, T.C = J, C
    for p in sorted((PROGRAMS / "macros").glob("m_*.py")):
        mod = importlib.import_module(p.stem)
        # the modules bound J and C at import: rebind, then build
        for name, fn in (("J", J), ("C", C)):
            if hasattr(mod, name):
                setattr(mod, name, fn)
        mod.build()
    return {s.replace("\\", "/") for s in seen}


def manuscript_files(ms: Path):
    """(released files, exhibits): generated snippets a manuscript inputs,
    the graphics it shows, and their backing files; an exhibit is
    (label, kind, file) for each figure and table found"""
    out, exhibits = set(), []
    tex = [ms / "main.tex"] + sorted((ms / "sections").glob("*.tex"))
    text = "\n".join(p.read_text(encoding="utf-8") for p in tex)
    dirs = re.search(r"\\graphicspath\{(.*)\}\s*$", text, re.M)
    paths = re.findall(r"\{([^{}]*)\}", dirs.group(1)) if dirs else []
    roots = [(ms / d).resolve() for d in paths]

    def graphic(name):
        for r in roots:
            for cand in (r / name, r / (name + ".pdf")):
                if cand.exists() and FIG in cand.parents:
                    return cand
        return None

    def label_after(src, pos):
        m = re.search(r"\\label\{([^{}]+)\}", src[pos:pos + 6000])
        return m.group(1) if m else ""

    sources = [(text, None)]
    for m in re.finditer(r"\\input\{([^{}]*programs/figures/[^{}]*)\}", text):
        p = (ms / (m.group(1) + ".tex")).resolve()
        if p.exists():
            out.add(p.relative_to(FIG).as_posix())
            src = p.read_text(encoding="utf-8")
            sources.append((src, p))
            if "\\begin{table}" in src:
                exhibits.append((label_after(src, 0), "table",
                                 p.relative_to(FIG).as_posix()))
    for src, snippet in sources:
        for m in re.finditer(
                r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]*)\}", src):
            cand = graphic(Path(m.group(1)).name)
            if cand is None:
                continue
            rel = cand.relative_to(FIG).as_posix()
            out.add(rel)
            exhibits.append((label_after(src, m.end()), "figure", rel))
            # the backing aggregate files of the figure
            for comp in sorted(cand.parent.glob(cand.stem + "_*")):
                if comp.suffix in (".csv", ".json"):
                    out.add(comp.relative_to(FIG).as_posix())
    return out, exhibits


def json_small_cells(path: Path, min_cell: int) -> list:
    """key paths of a JSON file that name students or entrants and hold a
    count from 1 to min_cell - 1"""
    skip = re.compile(r"min_cell|minimum|threshold|min_takers")
    # keys that count students in the outputs of this project; counts of
    # public units (districts, schools, course families, name rows) are
    # not counts of students
    exact = {"n", "count", "with_dfw", "not_observed_later"}
    hits = []

    def is_count(key):
        k = key.lower()
        return (not skip.search(k)) and (
            "student" in k or "entrant" in k or k in exact)

    def walk(o, path, key):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}/{k}", str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]", key)
        elif (isinstance(o, (int, float)) and not isinstance(o, bool)
              and o == o and is_count(key)
              and float(o) == int(o) and 0 < o < min_cell):
            hits.append((path, o))

    walk(json.loads(path.read_text(encoding="utf-8")), "", "")
    return hits


def scan(files) -> list:
    import disclosure_scan as D
    hits = []
    for f in sorted(files):
        if f.endswith(".csv"):
            r = D.scan_file(FIG / f)
            if r:
                hits.append((f, r["columns"]))
        elif f.endswith(".json"):
            r = json_small_cells(FIG / f, D.MIN_CELL)
            if r:
                hits.append((f, r[:5]))
    return hits


def manifest(files, exhibits) -> list:
    rows, seen = [], set()
    for label, kind, rel in exhibits:
        if rel in seen:
            continue
        seen.add(rel)
        stem = Path(rel).stem
        assert stem in GENERATORS, f"no generating program on record: {rel}"
        folder = Path(rel).parent.as_posix()
        backing = sorted({f for f in files if f != rel and (
            Path(f).parent.as_posix() == folder
            and Path(f).name.startswith(stem + "_"))}
            | set(INPUTS.get(stem, [])))
        assert backing, f"no released input on record: {rel}"
        rows.append([label, kind, rel, GENERATORS[stem], "; ".join(backing),
                     SUMMARY_ONLY.get(stem, "values shown")])
    return sorted(rows, key=lambda r: (r[1], r[2]))


def graphics(files) -> list:
    """Checks of what a figure states through its geometry. A chord
    diagram states one count of students per ribbon; the counts are
    recovered from the PDF and held to the minimum cell
    (chord_geometry_check.py)."""
    import chord_geometry_check as G
    problems = []
    for f in sorted(files):
        if Path(f).name.startswith("figChord-") and f.endswith(".pdf"):
            problems += [(f, p) for p in G.check(FIG / f)]
    return problems


def tracked() -> set:
    r = subprocess.run(["git", "ls-files", "programs/figures"],
                       cwd=PROGRAMS.parent, capture_output=True, text=True)
    return {ln[len("programs/figures/"):] for ln in r.stdout.split("\n")
            if ln.startswith("programs/figures/")}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = macro_sources()
    files |= {p.relative_to(FIG).as_posix()
              for p in (FIG / "macros").glob("*.tex")}
    exhibits = []
    if args:
        more, exhibits = manuscript_files(Path(args[0]).resolve())
        files |= more
        files |= exhibit_inputs(files)
    missing = sorted(f for f in files if not (FIG / f).exists())
    assert not missing, missing

    hits = scan(files)
    for f, r in hits:
        print("SMALL CELLS:", f, r)
    drawn = graphics(files)
    for f, problem in drawn:
        print("FIGURE:", f, problem)
    if hits or drawn:
        print("release stopped: counts of students under the minimum")
        return 1
    rows = manifest(files, exhibits)

    if "--check" in sys.argv:
        have = tracked() - set(LISTS)
        extra, absent = sorted(have - files), sorted(files - have)
        for f in extra:
            print("tracked but not on the list:", f)
        for f in absent:
            print("on the list but not tracked:", f)
        print(f"{len(files)} released outputs, scan clean, "
              f"{len(extra) + len(absent)} differences from the files "
              "git tracks")
        return 1 if extra or absent else 0

    (FIG / "RELEASE.txt").write_text(
        "\n".join(sorted(files)) + "\n", encoding="utf-8")
    with open(FIG / "RELEASE_MANIFEST.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["label", "kind", "file", "generated_by", "backing_files",
                    "backing_holds"])
        w.writerows(rows)
    print(f"{len(files)} released outputs listed in {FIG / 'RELEASE.txt'}; "
          f"{len(rows)} exhibits in RELEASE_MANIFEST.csv")
    if "--stage" in sys.argv:
        paths = [str((FIG / f).relative_to(PROGRAMS.parent)).replace("\\", "/")
                 for f in sorted(files)]
        paths += [f"programs/figures/{n}" for n in LISTS]
        for i in range(0, len(paths), 100):
            subprocess.run(["git", "add", "-f", "--", *paths[i:i + 100]],
                           cwd=PROGRAMS.parent, check=True)
        print("staged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
