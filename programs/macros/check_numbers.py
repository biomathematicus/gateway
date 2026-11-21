"""Check of the rule "no number that a program computes is typed in the
manuscript".

    python check_numbers.py [manuscript folder]

Lists every numeric literal that is still typed in the manuscript sources
and is not on the list of literals that stay text (kept_numbers.tsv beside
this file: file, literal, the words before it, and the reason). A literal
stays text when it is a calendar label, a name that holds digits, the unit
of a statement, a numeral of a formula, a statistic quoted from a cited
source, or a statistical convention. Exit status 1 when a literal is not
on the list.

    python check_numbers.py --accept REASON [folder]

adds every literal that is not yet listed to kept_numbers.tsv with the
given reason; use it after reading the listing.
"""
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEPT = HERE / "kept_numbers.tsv"
FILES = ["main.tex"] + [f"sections/{n}" for n in (
    "01_introduction.tex", "02_data_methods.tex", "03_results.tex",
    "04_discussion.tex", "05_statements.tex", "A1_statistical_methods.tex",
    "A2_additional_results.tex", "A3_data_appendix.tex", "A4_major_codes.tex")]

NUM = re.compile(r"(?:\d{1,3}(?:\{,\}\d{3})+|\d+)(?:\.\d+)?")
ARGS = re.compile(
    r"\\(?:ref|eqref|label|cite[tp]?\*?|input|includegraphics|bibliography\w*|"
    r"usepackage|documentclass|setcounter|multicolumn|cmidrule|hypersetup|"
    r"begin|end|setlength|renewcommand|newcommand|providecommand|"
    r"counterwithin\*?|graphicspath|vspace|hspace|rule|IfFileExists)"
    r"(?:\[[^\]]*\])*(?:\([^)]*\))?(?:\{[^{}]*\})*")
UNIT = re.compile(r"(?:pt|em|ex|cm|mm|bp)\b|\\textwidth|\\linewidth|"
                  r"\\tabcolsep|\\baselineskip")


def code_part(line):
    m = re.search(r"(?<!\\)%", line)
    return line if m is None else line[:m.start()]


def literals(text, first=0, last=10 ** 9):
    """(line number, literal, words before it) for every typed number"""
    out = []
    for ln, line in enumerate(text.split("\n"), 1):
        if not first <= ln <= last:
            continue
        code = code_part(line)
        masked = list(code)
        for m in ARGS.finditer(code):
            masked[m.start():m.end()] = " " * (m.end() - m.start())
        for m in re.finditer(r"\\\\\[[^\]]*\]|p\{[^}]*\}|\[[tbph!]+\]", code):
            masked[m.start():m.end()] = " " * (m.end() - m.start())
        masked = "".join(masked)
        for m in NUM.finditer(masked):
            a, b = m.span()
            if a and (masked[a - 1].isalpha() or masked[a - 1] in "\\#@_^"):
                continue                       # part of a name: MAT1073
            if UNIT.match(masked, b):
                continue                       # a length
            before = re.sub(r"\s+", " ", code[max(0, a - 30):a]).strip()
            out.append((ln, code[a:b], before[-24:]))
    return out


def scan(ms):
    rows = []
    for rel in FILES:
        text = (ms / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        first, last = 0, 10 ** 9
        if rel == "main.tex":                  # the abstract only
            first = text[:text.index("\\begin{abstract}")].count("\n") + 1
            last = text[:text.index("\\end{abstract}")].count("\n") + 1
        for ln, lit, before in literals(text, first, last):
            rows.append((rel, ln, lit, before))
    return rows


def kept():
    if not KEPT.exists():
        return {}
    with open(KEPT, encoding="utf-8", newline="") as fh:
        return {(r["file"], r["literal"], r["before"]): r["reason"]
                for r in csv.DictReader(fh, delimiter="\t")}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    accept = None
    if "--accept" in sys.argv:
        accept = sys.argv[sys.argv.index("--accept") + 1]
        args.remove(accept)
    ms = Path(args[0]) if args else (
        HERE.parents[2] / "Economics" / "Paper0" / "manuscript")
    known = kept()
    rows = scan(ms)
    new = [r for r in rows if (r[0], r[2], r[3]) not in known]
    print(f"{len(rows)} typed numbers in the manuscript, "
          f"{len(rows) - len(new)} on the list of literals that stay text, "
          f"{len(new)} not listed")
    for rel, ln, lit, before in new:
        print(f"  {rel}:{ln}\t{lit}\t...{before}")
    if accept and new:
        for rel, ln, lit, before in new:
            known[(rel, lit, before)] = accept
        with open(KEPT, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter="\t", lineterminator="\n")
            w.writerow(["file", "literal", "before", "reason"])
            for (rel, lit, before), why in sorted(known.items()):
                w.writerow([rel, lit, before, why])
        print(f"{len(new)} added to {KEPT.name}")
        return 0
    return 1 if new else 0


if __name__ == "__main__":
    raise SystemExit(main())
