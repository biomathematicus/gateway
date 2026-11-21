"""Second PostgreSQL service of the project: the College Scorecard tables.

The Scorecard analysis keeps its imported data in its own PostgreSQL
cluster, apart from the project database of `gateway/db.py`: a user-space
cluster with trust authentication on localhost, whose data directory lives
outside any synchronized folder. Settings come from the `[scorecard]`
section of `programs/env/config.toml` (see `config.example.toml`), each
with a default:

    host      localhost
    port      5434
    dbname    paper0
    user      the operating-system user who runs the program
    bin_dir   folder of the PostgreSQL programs (default: the folder of
              `pg_isready` on the PATH)
    data_dir  folder of the cluster (default: a folder of the local user
              profile); used only to start the server when it is down

- schema : scorecard  (loaded by load_scorecard.py)

connect() ensures the server is running, then returns a psycopg (version
3) connection. Analysis code uses SQL for cross-referencing and plain
lists / numpy arrays for computation - no pandas.
"""
import getpass
import os
import shutil
import subprocess
import time
import tomllib
from pathlib import Path

import psycopg

ENV = Path(__file__).resolve().parent.parent / "env"


def _settings() -> dict:
    cfg = {}
    path = ENV / "config.toml"
    if path.exists():
        with open(path, "rb") as fh:
            cfg = tomllib.load(fh).get("scorecard", {})
    found = shutil.which("pg_isready")
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return {
        "host": cfg.get("host", "localhost"),
        "port": int(cfg.get("port", 5434)),
        "dbname": cfg.get("dbname", "paper0"),
        "user": cfg.get("user") or getpass.getuser(),
        "bin_dir": Path(cfg.get("bin_dir") or (
            Path(found).parent if found
            else r"C:\Program Files\PostgreSQL\16\bin")),
        "data_dir": Path(cfg.get("data_dir")
                         or local / "SocialSpeciesPG" / "data"),
    }


S = _settings()
PG_BIN, PG_DATA, PORT = S["bin_dir"], S["data_dir"], S["port"]
PG_LOG = PG_DATA.parent / "pg.log"
DSN = (f"host={S['host']} port={PORT} dbname={S['dbname']} "
       f"user={S['user']}")


def _running() -> bool:
    r = subprocess.run([str(PG_BIN / "pg_isready"), "-h", S["host"],
                        "-p", str(PORT)], capture_output=True)
    return r.returncode == 0


def ensure_server() -> None:
    if _running():
        return
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen(
        [str(PG_BIN / "postgres"), "-D", str(PG_DATA)],
        stdout=subprocess.DEVNULL, stderr=open(PG_LOG, "ab"),
        creationflags=flags)
    for _ in range(30):
        time.sleep(0.5)
        if _running():
            return
    raise RuntimeError(f"postgres did not start; see {PG_LOG}")


def connect() -> psycopg.Connection:
    ensure_server()
    return psycopg.connect(DSN)


if __name__ == "__main__":
    with connect() as cn:
        print(cn.execute("select version()").fetchone()[0])
