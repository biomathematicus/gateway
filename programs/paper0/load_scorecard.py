"""Load curated College Scorecard columns into PostgreSQL (paper0 DB).

Streams selected columns of MERGED{year}_PP.csv members straight from the
raw-data zip into scorecard.institution via COPY - csv module and lists
only, no pandas. Idempotent: reloading a data year replaces it.

Years loaded: the frozen pre-perturbation vintage (2019-20) and the most
recent data years, so the locator figure can be drawn 'as of today' with
the baseline vintage one parameter away.
"""
import csv
import io
import sys
import zipfile
from pathlib import Path

import pg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gateway import paths  # noqa: E402

ZIP_NAME = "College_Scorecard_Raw_Data_06102026.zip"


def archive() -> Path:
    """The Scorecard archive listed in data_manifest.csv: under the raw
    data folder (`scorecard/`), or in `data/` beside this program, where
    it was first kept."""
    places = (Path(paths.data_dir("scorecard")),
              Path(__file__).resolve().parent / "data")
    for d in places:
        if (d / ZIP_NAME).exists():
            return d / ZIP_NAME
    raise FileNotFoundError(
        f"{ZIP_NAME} not found in " + " or ".join(str(d) for d in places))
YEARS = ["2019_20", "2023_24", "2024_25", "2025_26"]

COLS = ["UNITID", "INSTNM", "CITY", "STABBR", "CONTROL", "PREDDEG",
        "HIGHDEG", "UGDS", "C150_4", "PCTPELL", "ADM_RATE", "RET_FT4",
        "SAT_AVG", "TUITIONFEE_IN", "HSI"]
NUMERIC = {"UNITID", "CONTROL", "PREDDEG", "HIGHDEG", "UGDS", "C150_4",
           "PCTPELL", "ADM_RATE", "RET_FT4", "SAT_AVG", "TUITIONFEE_IN",
           "HSI"}
MISSING = {"", "NULL", "PrivacySuppressed", "PS"}

DDL = """
create schema if not exists scorecard;
create table if not exists scorecard.institution (
  data_year     text not null,
  unitid        integer not null,
  instnm        text,
  city          text,
  stabbr        text,
  control       integer,
  preddeg       integer,
  highdeg       integer,
  ugds          real,
  c150_4        real,
  pctpell       real,
  adm_rate      real,
  ret_ft4       real,
  sat_avg       real,
  tuitionfee_in real,
  hsi           integer,
  primary key (data_year, unitid)
);
"""


def load_year(cn, z: zipfile.ZipFile, year: str) -> int:
    member = next(n for n in z.namelist()
                  if n.endswith(f"MERGED{year}_PP.csv"))
    cn.execute("delete from scorecard.institution where data_year = %s",
               (year,))
    n = 0
    with z.open(member) as raw:
        rdr = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig",
                                          newline=""))
        header = next(rdr)
        idx = [header.index(c) for c in COLS]
        with cn.cursor().copy(
                "copy scorecard.institution from stdin") as cp:
            for row in rdr:
                vals = [year]
                for c, i in zip(COLS, idx):
                    v = row[i].strip()
                    if v in MISSING:
                        vals.append(None)
                    elif c in NUMERIC:
                        try:
                            vals.append(float(v) if "." in v else int(v))
                        except ValueError:
                            vals.append(None)
                    else:
                        vals.append(v)
                if vals[1] is None:
                    continue
                cp.write_row(vals)
                n += 1
    return n


def main() -> None:
    with pg.connect() as cn:
        cn.execute(DDL)
        with zipfile.ZipFile(archive()) as z:
            for year in YEARS:
                n = load_year(cn, z, year)
                print(f"{year}: {n:,} institutions")
        cn.commit()
        for year, total, c150 in cn.execute(
                """select data_year, count(*),
                          count(c150_4) filter (where preddeg = 3)
                   from scorecard.institution group by 1 order by 1"""):
            print(f"  {year}: {total:,} rows; "
                  f"{c150:,} bachelor's with C150_4")


if __name__ == "__main__":
    main()
