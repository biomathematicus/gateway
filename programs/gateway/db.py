"""
GATEWAY database access.

Connection facts this module encodes so no caller has to rediscover them:

  * The host, port, database, and user come from `programs/env/config.toml`
    (copy `config.example.toml`). The database needs PostGIS.
  * `odbc_connect()` builds an explicit connection string with the port, so
    that no system DSN with a missing port can redirect the connection.
  * Secrets are read from `programs/env/secrets.env`, which is never tracked.
    Nothing in this package embeds a password or an API key.

psycopg2 is the default driver because `COPY` is an order of magnitude faster
than parameterised inserts for the bulk loads. pyodbc is provided for tools that
want the ODBC route.
"""

from __future__ import annotations

import os
import tomllib
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
ENV = os.path.join(CODE, "env")


def _load_secrets() -> dict[str, str]:
    out: dict[str, str] = {}
    p = os.path.join(ENV, "secrets.env")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    for k in ("CENSUS_API_KEY", "PGPASSWORD"):
        if k in os.environ:
            out[k] = os.environ[k]
    return out


def config() -> dict:
    with open(os.path.join(ENV, "config.toml"), "rb") as fh:
        return tomllib.load(fh)


def census_api_key() -> str | None:
    return _load_secrets().get("CENSUS_API_KEY")


def dsn_kwargs() -> dict:
    c = config()["db"]
    return {"host": c["host"], "port": c["port"], "dbname": c["dbname"],
            "user": c["user"], "password": _load_secrets().get("PGPASSWORD", "")}


@contextmanager
def connect(autocommit: bool = False):
    """psycopg2 connection to GATEWAY."""
    import psycopg2
    conn = psycopg2.connect(**dsn_kwargs())
    conn.autocommit = autocommit
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def odbc_connect():
    """ODBC route, with an EXPLICIT port. Never relies on the broken DSN."""
    import pyodbc
    c = config()["db"]
    s = _load_secrets()
    return pyodbc.connect(
        "DRIVER={PostgreSQL ODBC Driver(UNICODE)};"
        f"SERVER={c['host']};PORT={c['port']};DATABASE={c['dbname']};"
        f"UID={c['user']};PWD={s.get('PGPASSWORD','')};")


def engine():
    """SQLAlchemy engine, for pandas.read_sql."""
    from sqlalchemy import create_engine
    from urllib.parse import quote_plus
    c = config()["db"]
    pw = quote_plus(_load_secrets().get("PGPASSWORD", ""))
    return create_engine(
        f"postgresql+psycopg2://{c['user']}:{pw}@{c['host']}:{c['port']}/{c['dbname']}")


def read_sql(sql: str, params=None):
    import pandas as pd
    return pd.read_sql(sql, engine(), params=params)


def exec_sql(sql: str) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)


def exec_file(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        exec_sql(fh.read())


def table_count(schema: str, table: str) -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f'select count(*) from "{schema}"."{table}"')
        return cur.fetchone()[0]
