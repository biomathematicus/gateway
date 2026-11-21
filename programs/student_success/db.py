"""Database access with local pickle caching.

Python analogue of funSaveMAT.m / funQuery2Cell.m: every query is keyed by a
sanitized name; on first execution the result is fetched from SQL Server
(trusted connection, local instance, database UTSA) and stored as a .pkl in
the cache folder (config.PKL_DIR, outside the repository); later runs load
the cache.

Provenance of a cache file. Beside each <name>.pkl the module writes
<name>.sha256 with the SHA-256 of the query text and the time of the read.
A cache is used only when that hash equals the hash of the query the
program now asks for; a cache whose query changed, or one written before
hashes were recorded, is read again from the database. The cache does not
know when the source tables change: for the run that a manuscript reports,
start from an empty cache folder or set GATEWAY_REFRESH=1, which reads
every query again.
"""
import datetime
import hashlib
import os
import re

import pandas as pd
import pyodbc

import config


def sanitize(name: str) -> str:
    """Mimic funSanitizeString: file-system safe cache/figure names."""
    name = name.replace("%", "ALL").replace("&", "and")
    name = re.sub(r"[.\\/,'\s]+", "-", name.strip())
    return re.sub(r"-+", "-", name).strip("-")


def term_str(s_term: str) -> str:
    """funDate2String: '2014.66' -> 'Fall 2014' (x.0 Spring, .33 Summer, .66 Fall)."""
    year, _, frac = s_term.partition(".")
    season = {"": "Spring", "0": "Spring", "33": "Summer", "66": "Fall"}.get(
        frac, s_term)
    return f"{season} {year}"


def query_hash(sql: str) -> str:
    """SHA-256 of the query text, whitespace normalized"""
    return hashlib.sha256(" ".join(sql.split()).encode("utf-8")).hexdigest()


def cached_query(name: str, sql: str, columns: list[str] | None = None,
                 refresh: bool = False) -> pd.DataFrame:
    config.PKL_DIR.mkdir(parents=True, exist_ok=True)
    path = config.PKL_DIR / f"{sanitize(name)}.pkl"
    record = path.with_suffix(".sha256")
    digest = query_hash(sql)
    refresh = refresh or os.environ.get("GATEWAY_REFRESH") == "1"
    if path.exists() and not refresh:
        on_record = (record.read_text(encoding="utf-8").split()[0]
                     if record.exists() else None)
        if on_record == digest:
            return pd.read_pickle(path)
        print(f"  cache {path.name}: "
              + ("its query changed" if on_record else "no query hash on record")
              + ", reading again", flush=True)
    with pyodbc.connect(config.CONN_STRING, timeout=10) as cn:
        cur = cn.cursor()
        rows = cur.execute(sql).fetchall()
        if columns is None:
            columns = [d[0] for d in cur.description]
        df = pd.DataFrame([tuple(r) for r in rows], columns=columns)
    df.to_pickle(path)
    record.write_text(
        f"{digest}  {datetime.datetime.now().isoformat(timespec='seconds')}\n",
        encoding="utf-8")
    return df
