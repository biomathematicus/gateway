"""
Ingest SAIPE school-district and county estimates into GATEWAY.

TWO file generations, which is why a single reader kept dropping years:

  1995-2002   per-STATE fixed-width `.dat`  (sd{yy}-{st}.dat)
              `48 07380 ABBOTT INDEPENDENT SCHOOL DISTRICT   973  201  17 sd97_TX.dat 05JAN2001`
              parsed by regex rather than column offsets, because the name field
              width is not constant across years.

  2003-2024   national `.xls` (ussd{yy}.xls), 6 columns, but the header row is
              at index 1 in 2003 and index 2 from 2017 — so the header row is
              LOCATED by searching for 'State Postal Code' instead of assumed.

KEY CONSTRUCTION
  LEAID = State FIPS (2) || District ID (5) = the 7-digit NCES LEAID that CRDC
  uses. This is the join that makes the whole triangulation possible, so it is
  built once, here, and asserted non-null.

VALUES
  SAIPE ships blanks and, in some vintages, thousands separators. Both become
  NULL rather than 0 — a district with an unknown poverty count is not a
  district with no poor children.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import db  # noqa: E402
from gateway import paths  # noqa: E402

DATA = paths.data_dir("SAIPE")

# 2-digit fips, 5-digit district id, name, then three integers, then the
# provenance stamp the Census appended to each row.
DAT_RE = re.compile(
    r"^\s*(\d{2})\s+(\d{5})\s+(.+?)\s{2,}"
    r"(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+\S+\.dat", re.I)

COLS = ["vintage", "state_fips", "district_id", "leaid", "name",
        "pop_total", "pop_5_17", "pov_5_17", "src_file"]


def _num(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("$", "")
    if s in ("", ".", "N", "NA", "nan", "None", "(X)", "(NA)"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def read_dat(path: str) -> pd.DataFrame:
    rows = []
    vintage = int(re.search(r"sd(\d{2})-", os.path.basename(path)).group(1))
    vintage += 1900 if vintage >= 90 else 2000
    with open(path, encoding="latin-1") as fh:
        for line in fh:
            m = DAT_RE.match(line)
            if not m:
                continue
            st, did, name, tot, p517, pov = m.groups()
            rows.append([vintage, st, did, st + did, name.strip(),
                         _num(tot), _num(p517), _num(pov),
                         os.path.basename(path)])
    return pd.DataFrame(rows, columns=COLS)


def read_xls(path: str) -> pd.DataFrame:
    """Handles BOTH header conventions.

    2003-2023 use human labels ('State FIPS Code', 'Estimated Population 5-17')
    on a header row that sits at index 1 or 2. 2024 switched to machine names
    ('state', 'distid', 'rpopall_24', 'rpop5_17v_24', 'saepov5_17rv_24') on row
    0 AND reordered the columns, so a positional reader silently returns
    population where poverty was expected. Columns are therefore resolved BY
    NAME under both conventions.
    """
    raw = pd.read_excel(path, header=None, dtype=str)
    hdr = None
    for i in range(min(8, len(raw))):
        row = raw.iloc[i].astype(str).str.lower()
        if row.str.contains("state postal code", na=False).any():
            hdr = i
            break
        if row.str.fullmatch(r"distid", na=False).any():   # 2024 machine names
            hdr = i
            break
    if hdr is None:
        raise ValueError(f"{path}: no recognisable header row")
    body = raw.iloc[hdr + 1:].copy()
    body.columns = [str(c).strip() for c in raw.iloc[hdr]]

    def col(*names):
        for n in names:
            for c in body.columns:
                cl = c.lower()
                nl = n.lower()
                if cl == nl or cl.startswith(nl):
                    return body[c]
        return pd.Series([None] * len(body), index=body.index)

    st = col("State FIPS", "state").astype(str).str.strip().str.zfill(2)
    did = col("District ID", "distid").astype(str).str.strip().str.zfill(5)
    vintage = int(re.search(r"ussd(\d{2})", os.path.basename(path)).group(1))
    vintage += 1900 if vintage >= 90 else 2000

    out = pd.DataFrame({
        "vintage": vintage,
        "state_fips": st,
        "district_id": did,
        "leaid": st + did,
        "name": col("Name", "name").astype(str).str.strip(),
        "pop_total": col("Estimated Total Population", "rpopall").map(_num),
        "pop_5_17": col("Estimated Population 5-17", "rpop5_17").map(_num),
        # 'saepov5_17rv' is the poverty COUNT in the 2024 machine schema; note it
        # sits BEFORE the 5-17 population column there, so name-resolution is
        # what keeps poverty from being read as population.
        "pov_5_17": col("Estimated number of rele", "Estimated Number of Rele",
                        "saepov5_17rv", "saepov5_17v").map(_num),
        "src_file": os.path.basename(path),
    })
    out = out[out["state_fips"].str.fullmatch(r"\d{2}", na=False)]
    out = out[out["district_id"].str.fullmatch(r"\d{5}", na=False)]
    return out[COLS]


def load_school_districts() -> pd.DataFrame:
    d = os.path.join(DATA, "school_districts")
    frames = []
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        try:
            if name.lower().endswith(".dat") and name.lower().startswith("sd"):
                frames.append(read_dat(p))
            elif name.lower().endswith((".xls", ".xlsx")) and name.lower().startswith("ussd"):
                frames.append(read_xls(p))
        except Exception as exc:
            print(f"  ! {name}: {exc}", flush=True)
    if not frames:
        raise SystemExit("no SAIPE school-district files parsed")
    df = pd.concat(frames, ignore_index=True)
    df = df[df["leaid"].str.fullmatch(r"\d{7}", na=False)]
    return df


def register_sources(df: pd.DataFrame) -> None:
    man = os.path.join(DATA, "MANIFEST.csv")
    hashes = {}
    if os.path.isfile(man):
        m = pd.read_csv(man)
        col = "file" if "file" in m.columns else m.columns[1]
        for _, r in m.iterrows():
            hashes[os.path.basename(str(r[col]))] = (r.get("sha256"), r.get("bytes"))
    with db.connect() as conn, conn.cursor() as cur:
        for f, grp in df.groupby("src_file"):
            sha, nbytes = hashes.get(f, (None, None))
            if sha is None:
                p = os.path.join(DATA, "school_districts", f)
                if os.path.isfile(p):
                    blob = open(p, "rb").read()
                    sha, nbytes = hashlib.sha256(blob).hexdigest(), len(blob)
            cur.execute("""
                INSERT INTO core.source_file
                    (dataset, vintage, rel_path, sha256, bytes, source_url, n_rows)
                VALUES ('saipe_sd', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dataset, vintage, rel_path) DO UPDATE
                   SET sha256=EXCLUDED.sha256, bytes=EXCLUDED.bytes,
                       n_rows=EXCLUDED.n_rows, loaded_at=now()
            """, (str(int(grp["vintage"].iloc[0])), f"SAIPE/school_districts/{f}",
                  sha or "", int(nbytes or 0),
                  "https://www2.census.gov/programs-surveys/saipe/datasets", len(grp)))


def write(df: pd.DataFrame) -> None:
    import io
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS stg.saipe_sd")
        cur.execute("""
            CREATE TABLE stg.saipe_sd (
                vintage     int  NOT NULL,
                state_fips  text NOT NULL,
                district_id text NOT NULL,
                leaid       text NOT NULL,
                name        text,
                pop_total   double precision,
                pop_5_17    double precision,
                pov_5_17    double precision,
                src_file    text NOT NULL,
                PRIMARY KEY (vintage, leaid)
            )""")
        # a district can appear twice in a vintage only if the source repeats it
        d = df.drop_duplicates(subset=["vintage", "leaid"], keep="first")
        buf = io.StringIO()
        d[COLS].to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            "COPY stg.saipe_sd (vintage,state_fips,district_id,leaid,name,"
            "pop_total,pop_5_17,pov_5_17,src_file) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
            buf)
        cur.execute("CREATE INDEX ON stg.saipe_sd (leaid)")
        cur.execute("CREATE INDEX ON stg.saipe_sd (vintage)")
        print(f"  stg.saipe_sd loaded: {len(d):,} rows "
              f"({len(df) - len(d)} duplicate (vintage,leaid) dropped)", flush=True)


def build_dim_lea() -> None:
    db.exec_sql("""
        TRUNCATE core.dim_lea;
        INSERT INTO core.dim_lea (leaid, state_fips, name_last, first_year, last_year, n_years)
        SELECT leaid,
               min(state_fips),
               (array_agg(name ORDER BY vintage DESC))[1],
               min(vintage), max(vintage), count(*)
        FROM stg.saipe_sd
        GROUP BY leaid;
    """)


def main() -> int:
    print("reading SAIPE school-district files ...", flush=True)
    df = load_school_districts()
    print(f"  parsed {len(df):,} district-year rows, "
          f"vintages {int(df.vintage.min())}-{int(df.vintage.max())}", flush=True)
    write(df)
    register_sources(df)
    build_dim_lea()
    q = db.read_sql("""
        SELECT vintage, count(*) AS districts,
               count(pov_5_17) AS with_pov,
               round(sum(pov_5_17)::numeric) AS total_pov_5_17
        FROM stg.saipe_sd GROUP BY vintage ORDER BY vintage
    """)
    print(q.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
