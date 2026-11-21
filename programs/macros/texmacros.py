"""Numbers of the manuscript as TeX macros.

Every number in the manuscript is a macro whose value a program writes. A
module of this package (`m_<analysis>.py`) reads the outputs of one analysis
under `programs/figures/` and returns its macros from `build()`;
`make_macros.py` writes them as `\\renewcommand` lines, one file per module,
under `programs/figures/macros/`.

Conventions
  * A macro name holds letters only (TeX allows no digits): `\\CalcSlope`.
    Each module uses one prefix, so names never collide between modules.
  * The value is the number exactly as the text prints it, without the
    surrounding `$` or `\\%`: `9{,}790`, `-0.171`, `36.9`. Thousands are
    grouped with `{,}`. A sign is part of the value when the text prints
    it. The same quantity printed two ways (signed and unsigned, one and
    two decimals) is two macros.
  * No number is typed in a module. A value comes from a file an analysis
    wrote (JSON, CSV) or from a constant of a program, read with `const()`.
"""
import ast
import csv
import json
import re
from pathlib import Path

PROGRAMS = Path(__file__).resolve().parents[1]
FIG = PROGRAMS / "figures"
OUT = FIG / "macros"


def J(rel):
    """a JSON output, by its path under programs/figures"""
    return json.loads((FIG / rel).read_text(encoding="utf-8"))


def C(rel):
    """a CSV output as a list of dict rows"""
    with open(FIG / rel, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def row(rows, **where):
    """the single CSV row matching every key=value given"""
    hit = [r for r in rows if all(str(r[k]) == str(v) for k, v in where.items())]
    assert len(hit) == 1, (where, len(hit))
    return hit[0]


def const(rel, name):
    """a module-level constant of a program, read from its source without
    importing it: const('paper0/course_gradient_figure.py', 'N_BOOT')"""
    tree = ast.parse((PROGRAMS / rel).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                names = [t.id] if isinstance(t, ast.Name) else (
                    [e.id for e in t.elts] if isinstance(t, ast.Tuple) else [])
                if name in names:
                    val = ast.literal_eval(node.value)
                    return val[names.index(name)] if len(names) > 1 else val
    raise KeyError((rel, name))


def group(digits: str) -> str:
    """1984991 -> 1{,}984{,}991"""
    out = ""
    while len(digits) > 3:
        out = "{,}" + digits[-3:] + out
        digits = digits[:-3]
    return digits + out


_ONES = ("zero one two three four five six seven eight nine ten eleven "
         "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
         "nineteen").split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()


def words(n, capital=False) -> str:
    """a count below one hundred written as a word: 15 -> fifteen"""
    assert float(n) == int(n) and 0 <= int(n) < 100, n
    n = int(n)
    w = _ONES[n] if n < 20 else (
        _TENS[n // 10 - 2] + ("-" + _ONES[n % 10] if n % 10 else ""))
    return w.capitalize() if capital else w


def fmt(x, spec="int"):
    """Format a value for the text.

    'int'      integer with grouped thousands          9{,}790
    'int0'     integer without grouping                2014
    '.1f'      fixed decimals                          36.9
    '+.3f'     fixed decimals with an explicit sign    +0.031 / -0.171
    's.3f'     sign only when negative                 -0.171 / 0.031
    'word'     a count written as a word               fifteen
    'Word'     the same at the start of a sentence     Fifteen
    A leading 'a' takes the absolute value first ('a.1f'); a trailing
    'g' groups thousands in the integer part ('.0fg').
    """
    if spec in ("word", "Word"):
        return words(x, capital=spec == "Word")
    x = float(x)
    if spec.startswith("a"):
        x, spec = abs(x), spec[1:]
    if spec == "int":
        return ("-" if round(x) < 0 else "") + group(str(abs(int(round(x)))))
    if spec == "int0":
        return str(int(round(x)))
    grp = spec.endswith("g")
    if grp:
        spec = spec[:-1]
    m = re.fullmatch(r"([+s]?)\.(\d)f", spec)
    assert m, spec
    sign, nd = m.group(1), int(m.group(2))
    body = f"{abs(x):.{nd}f}"
    neg = x < 0 and float(body) != 0.0
    if grp:
        ip, _, fp = body.partition(".")
        body = group(ip) + ("." + fp if fp else "")
    if sign == "+":
        return ("-" if neg else "+") + body
    return ("-" if neg else "") + body


class Macros:
    """the macros of one module: M = Macros('Calc'); M('Slope', value)"""

    def __init__(self, prefix: str):
        assert re.fullmatch(r"[A-Z][A-Za-z]+", prefix), prefix
        self.prefix, self.items = prefix, {}

    def __call__(self, name: str, value, spec: str | None = None):
        full = self.prefix + name
        assert re.fullmatch(r"[A-Za-z]+", full), f"letters only: {full}"
        assert full not in self.items, f"defined twice: {full}"
        self.items[full] = fmt(value, spec) if spec else str(value)
        return self.items[full]
