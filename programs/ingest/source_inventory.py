"""Inventory of the public input files: data_sources.csv at the root of
the repository.

    python programs/ingest/source_inventory.py

One row per raw public file that a program of the study reads. Two kinds
of row:

  registry   the file was registered when it was loaded into the project
             database (core.source_file: dataset, vintage, path, SHA-256,
             byte count, source address, rows loaded);
  listed     the file is read by a program that does not register it (the
             Opportunity Atlas tables, the two CCD directories of the
             recovery pass, the ZCTA gazetteer of the distance diagnostic,
             the College Scorecard archive); its hash is computed here.

Every file is then looked for under the raw data folder (gateway/paths.py)
and hashed again. The column `check` says what was found:

  match      the file is in place and has the recorded hash
  match at the acquisition path
             the file has the recorded hash at the path recorded when it
             was acquired (data_manifest.csv) and has not yet been put
             under the raw data folder
  differs    the file is in place with another hash
  absent     the file was not found

data_manifest.csv, beside this file, keeps the fuller acquisition records
(license, schema, lineage) of the six archives acquired for the study; the
inventory is the complete list.

The registry stores each path as it was at loading. Two loaders recorded
paths below the CRDC folder; `file` gives every path from the raw data
folder, which is where a rebuild expects it.
"""
import csv
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db, paths  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data_sources.csv")
MANIFEST = os.path.join(ROOT, "data_manifest.csv")
TOP = ("CRDC/", "SAIPE/", "geo/", "OA/", "scorecard/")

# files that a program reads without registering them:
# dataset, vintage, path under the raw data folder, locator, program
LISTED = [
    ("opportunity_atlas", "2018 release, 2010 tract definitions",
     "OA/tract_outcomes_simple.csv", "https://opportunityinsights.org/data/",
     "ingest/oa_nmdb.py"),
    ("opportunity_atlas", "2018 release, 2010 tract definitions",
     "OA/tract_covariates.csv", "https://opportunityinsights.org/data/",
     "ingest/oa_nmdb.py"),
    ("ccd_school_universe", "2013-14",
     "geo/ccd_sc132a/sc132a.txt", "https://nces.ed.gov/ccd/pubschuniv.asp",
     "xwalk/ccd_recovery.py"),
    ("ccd_school_universe", "2010-11",
     "geo/ccd_sc102a/sc102a.txt", "https://nces.ed.gov/ccd/pubschuniv.asp",
     "xwalk/ccd_recovery.py"),
    ("census_gazetteer_zcta", "2010",
     "geo/Gaz_zcta_national.txt",
     "https://www.census.gov/geographies/reference-files/time-series/geo/"
     "gazetteer-files.html",
     "analysis/zip_hs_distance_coords.py"),
]
LOADER = {"saipe_sd": "ingest/saipe.py", "crdc": "ingest/crdc.py",
          "crdc_alg2": "ingest/crdc_panel.py",
          "crdc_courses": "ingest/crdc_courses.py",
          "edge_geocode": "ingest/edge_schools.py",
          "edge_grf_lea_tract": "ingest/tract_district_xwalk.py",
          "zcta_tract_rel": "ingest/zip_tract_xwalk.py"}


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def under_data(rel: str) -> str:
    """the registered path, from the raw data folder. Two loaders recorded
    paths below the CRDC folder, and the loader of the school locations
    left out the folder that holds each workbook."""
    rel = rel.replace("\\", "/")
    if not rel.startswith(TOP):
        rel = "CRDC/" + rel
    if not os.path.exists(paths.data_dir(*rel.split("/"))):
        folder, name = rel.rsplit("/", 1)
        inside = f"{folder}/{os.path.splitext(name)[0]}/{name}"
        if os.path.exists(paths.data_dir(*inside.split("/"))):
            rel = inside
    return rel


def registry() -> list[dict]:
    with db.connect() as c:
        cur = c.cursor()
        cur.execute("select dataset, vintage, rel_path, sha256, bytes, "
                    "source_url, n_rows from core.source_file "
                    "order by dataset, vintage, rel_path")
        rows = cur.fetchall()
    return [{"dataset": d, "vintage": v, "file": under_data(p),
             "sha256": s, "bytes": b, "rows_loaded": n if n is not None else "",
             "locator": u, "read_by": LOADER.get(d, ""), "record": "registry"}
            for d, v, p, s, b, u, n in rows]


def listed() -> list[dict]:
    out = []
    for d, v, rel, url, prog in LISTED:
        p = paths.data_dir(*rel.split("/"))
        there = os.path.exists(p)
        out.append({"dataset": d, "vintage": v, "file": rel,
                    "sha256": sha256(p) if there else "",
                    "bytes": os.path.getsize(p) if there else "",
                    "rows_loaded": "", "locator": url, "read_by": prog,
                    "record": "listed"})
    # the College Scorecard archive: its record is in data_manifest.csv
    with open(MANIFEST, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["source_id"].startswith("scorecard"):
                out.append({
                    "dataset": "college_scorecard",
                    "vintage": "June 10 2026 release",
                    "file": "scorecard/" + os.path.basename(
                        r["local_path"].replace("\\", "/")),
                    "sha256": r["sha256"], "bytes": r["byte_size"],
                    "rows_loaded": "", "locator": r["acquisition_url"],
                    "read_by": "paper0/load_scorecard.py",
                    "record": "listed"})
    return out


def acquisition_paths() -> dict:
    """basename -> path recorded at acquisition (data_manifest.csv),
    relative to the folder that holds the repository"""
    with open(MANIFEST, newline="", encoding="utf-8") as fh:
        return {os.path.basename(r["local_path"].replace("\\", "/")):
                r["local_path"] for r in csv.DictReader(fh)}


def place(rel: str, acquired: dict) -> tuple[str | None, str]:
    """where the file is now, and how it was found"""
    p = paths.data_dir(*rel.split("/"))
    if os.path.exists(p):
        return p, "match"
    old = acquired.get(os.path.basename(rel))
    if old:
        q = os.path.join(os.path.dirname(ROOT), *old.split("/"))
        if os.path.exists(q):
            return q, "match at the acquisition path"
    return None, "absent"


def main() -> int:
    rows = registry() + listed()
    acquired = acquisition_paths()
    seen, tally = {}, {}
    for r in rows:
        p, how = place(r["file"], acquired)
        if p is not None:
            if p not in seen:
                seen[p] = sha256(p)
            if seen[p] != r["sha256"]:
                how = "differs"
        r["check"] = how
        tally[how] = tally.get(how, 0) + 1
    tally.setdefault("differs", 0)
    cols = ["dataset", "vintage", "file", "sha256", "bytes", "rows_loaded",
            "locator", "read_by", "record", "check"]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    by = {}
    for r in rows:
        by[r["dataset"]] = by.get(r["dataset"], 0) + 1
    # the counts the manuscript quotes
    stats = {"files": len(rows),
             "files_with_recorded_hash_on_disk": sum(
                 v for k, v in tally.items() if k.startswith("match")),
             "files_not_under_the_raw_data_folder": sum(
                 v for k, v in tally.items() if k != "match"),
             "manifest_archives": len(acquired),
             "files_by_dataset": by}
    with open(os.path.join(ROOT, "programs", "figures",
                           "data_sources_stats.json"), "w",
              encoding="utf-8") as fh:
        json.dump(stats, fh, indent=1)
    print(f"{len(rows)} files in {OUT}")
    for d, n in sorted(by.items()):
        print(f"  {d}: {n}")
    print("check:", ", ".join(f"{k} {v}" for k, v in tally.items()))
    return 0 if not tally["differs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
