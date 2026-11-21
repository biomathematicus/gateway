"""Where the raw public files are.

One rule for every loader: the folder named by the environment variable
GATEWAY_DATA when it is set; otherwise the folder `data/` beside
`programs/`; otherwise, when that folder does not exist, a folder `data/`
one level higher (the layout of the original working tree).

    from gateway import paths
    CRDC = paths.data_dir("CRDC")

`ingest/crdc_courses.py` is the one loader that does not use this module:
its hash is on record in the registration of the analysis plan, so the file
is left as it is, and it reads `data/CRDC` beside `programs/` only.
"""
import os

PROGRAMS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_root() -> str:
    env = os.environ.get("GATEWAY_DATA")
    if env:
        return os.path.abspath(env)
    beside = os.path.abspath(os.path.join(PROGRAMS, "..", "data"))
    above = os.path.abspath(os.path.join(PROGRAMS, "..", "..", "data"))
    if not os.path.isdir(beside) and os.path.isdir(above):
        return above
    return beside


def data_dir(*parts: str) -> str:
    """a folder or file under the raw data folder"""
    return os.path.join(data_root(), *parts)
