"""Inventory of the numeric literals of the manuscript, and the tools that
replace them by macros.

    python inventory.py snapshot     copy the manuscript sources to _work/
                                     and list every numeric literal with a
                                     stable identifier (_work/inventory.tsv)
    python inventory.py check NAME   check _work/assign_NAME.json against
                                     the module m_NAME.py: every assigned
                                     macro must reproduce its literal
    python inventory.py apply        replace every checked literal in the
                                     manuscript by its macro
    python inventory.py status       what is assigned and what is left
    python inventory.py region TAG A B   the literals of lines A..B of the
                                     file whose name starts with TAG (03,
                                     A2, ...), with what was decided

A literal is a run of digits with optional grouped thousands (`9{,}790`) and
decimals, with its sign when it is in math mode. Numbers inside \\ref,
\\label, \\cite, \\input, comments, and lengths (`4pt`, `0.21\\textwidth`)
are not literals of the text. The assignment files map identifiers to macro
names; they are working files of the conversion and are not tracked.
"""
import importlib
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
MS = HERE.parents[2] / "Economics" / "Paper0" / "manuscript"
WORK = HERE / "_work"
SNAP = WORK / "snapshot"
FILES = ["main.tex"] + [f"sections/{n}" for n in (
    "01_introduction.tex", "02_data_methods.tex", "03_results.tex",
    "04_discussion.tex", "05_statements.tex", "A1_statistical_methods.tex",
    "A2_additional_results.tex", "A3_data_appendix.tex", "A4_major_codes.tex")]

NUM = re.compile(r"(?:\d{1,3}(?:\{,\}\d{3})+|\d+)(?:\.\d+)?")
ARGS = re.compile(
    r"\\(?:ref|eqref|label|cite[tp]?\*?|input|includegraphics|bibliography\w*|"
    r"usepackage|documentclass|setcounter|multicolumn|cmidrule|hypersetup|"
    r"begin|end|setlength|renewcommand|newcommand|providecommand|"
    r"counterwithin\*?|graphicspath|vspace|hspace|rule)"
    r"(?:\[[^\]]*\])*(?:\([^)]*\))?(?:\{[^{}]*\})*")
# a length is written without a space (4pt, 0.21\textwidth); "0.7 in
# Edgewood" is a number followed by a word
UNIT = re.compile(r"(?:pt|em|ex|cm|mm|bp)\b|\\textwidth|\\linewidth|"
                  r"\\tabcolsep|\\baselineskip")


def code_part(line: str) -> str:
    """the line without its comment"""
    m = re.search(r"(?<!\\)%", line)
    return line if m is None else line[:m.start()]


def literals(text: str, body_from: int = 0):
    """(line, c0, c1, literal, in_math) for every literal of a file"""
    out, math = [], False
    for ln, line in enumerate(text.split("\n")):
        code = code_part(line)
        masked = list(code)
        for m in ARGS.finditer(code):
            for i in range(m.start(), m.end()):
                masked[i] = " "
        for m in re.finditer(r"\\\\\[[^\]]*\]|p\{[^}]*\}|\[[tbph!]+\]", code):
            for i in range(m.start(), m.end()):
                masked[i] = " "
        masked = "".join(masked)
        # math state at each position of the line (single $ only)
        state, flags = math, []
        for i, ch in enumerate(code):
            if ch == "$" and (i == 0 or code[i - 1] != "\\"):
                state = not state
            flags.append(state)
        math = state
        if ln < body_from:
            continue
        for m in NUM.finditer(masked):
            a, b = m.span()
            if a and (masked[a - 1].isalpha() or masked[a - 1] in "\\#@_^"):
                continue                      # part of a name: MAT1073, H1
            if UNIT.match(masked, b):
                continue                      # a length
            in_math = flags[a] if a < len(flags) else False
            if in_math and a and code[a - 1] in "+-" and (
                    a == 1 or code[a - 2] in "$( ,{"):
                a -= 1                        # the sign belongs to the number
            out.append((ln + 1, a, b, code[a:b], in_math))
    return out


def snapshot():
    rows = []                    # files are overwritten in place
    for rel in FILES:
        dst = SNAP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MS / rel, dst)
        with open(dst, encoding="utf-8", newline="") as fh:
            text = fh.read().replace("\r\n", "\n")
        start = 0
        if rel == "main.tex":                 # the abstract only
            start = text[:text.index("\\begin{abstract}")].count("\n")
        tag = Path(rel).stem.split("_")[0]
        lines = text.split("\n")
        for k, (ln, a, b, lit, mth) in enumerate(literals(text, start)):
            if rel == "main.tex" and ln > text[:text.index(
                    "\\end{abstract}")].count("\n") + 1:
                continue
            line = lines[ln - 1]
            ctx = (line[max(0, a - 45):a] + "[[" + lit + "]]" + line[b:b + 30])
            rows.append((f"{tag}:{k:04d}", rel, ln, a, b, lit,
                         "math" if mth else "text", ctx.strip()))
    with open(WORK / "inventory.tsv", "w", encoding="utf-8", newline="") as fh:
        fh.write("id\tfile\tline\tc0\tc1\tliteral\tmode\tcontext\n")
        for r in rows:
            fh.write("\t".join(str(x) for x in r) + "\n")
    print(f"{len(rows)} literals listed in {WORK / 'inventory.tsv'}")
    by = {}
    for r in rows:
        by[r[1]] = by.get(r[1], 0) + 1
    for k, v in by.items():
        print(f"  {v:5d}  {k}")


def inventory():
    with open(WORK / "inventory.tsv", encoding="utf-8") as fh:
        head = fh.readline().rstrip("\n").split("\t")
        return {r[0]: dict(zip(head, r)) for r in
                (line.rstrip("\n").split("\t") for line in fh) if r and r[0]}


def items_of(name: str):
    """the macros of the module m_NAME.py, or {} when there is none"""
    if not (HERE / f"m_{name}.py").exists():
        return {}
    return importlib.import_module(f"m_{name}").build()


def other_items(name: str):
    """the macros of every other module; a module that does not import
    (someone is writing it) is skipped"""
    out = {}
    for p in sorted(HERE.glob("m_*.py")):
        other = p.stem[2:]
        if other == name:
            continue
        try:
            out.update(items_of(other))
        except Exception as exc:               # noqa: BLE001
            print(f"  (module m_{other} skipped: {type(exc).__name__})")
    return out


def check(name: str, quiet=False):
    """An assignment may use a macro of its own module or of any other
    module; the macro must print exactly the literal it replaces."""
    inv = inventory()
    assign = json.loads((WORK / f"assign_{name}.json").read_text(encoding="utf-8"))
    own = items_of(name)
    items = dict(own)
    if any(m not in items for m in assign.values()):
        items = {**other_items(name), **own}
    bad = []
    for lid, macro in assign.items():
        if lid not in inv:
            bad.append((lid, macro, "unknown identifier"))
        elif macro not in items:
            bad.append((lid, macro, "macro not defined by the module"))
        elif items[macro] != inv[lid]["literal"]:
            bad.append((lid, macro, f"macro gives {items[macro]!r}, the text "
                                    f"has {inv[lid]['literal']!r}"))
    unused = sorted(set(own) - set(assign.values()))
    if not quiet:
        print(f"{name}: {len(assign)} literals assigned, {len(own)} macros, "
              f"{len(bad)} mismatches, {len(unused)} macros not used")
        for b in bad[:40]:
            print("  MISMATCH", *b)
        if unused:
            print("  not used:", ", ".join(unused[:30]))
    return assign, bad


def all_assignments():
    out, clash = {}, []
    for p in sorted(WORK.glob("assign_*.json")):
        name = p.stem[len("assign_"):]
        try:
            assign, bad = check(name, quiet=True)
        except Exception as exc:               # noqa: BLE001
            # a unit that is being written does not stop the others
            print(f"  (unit {name} skipped: {type(exc).__name__}: {exc})")
            continue
        badids = {b[0] for b in bad}
        for lid, macro in assign.items():
            if lid in badids:
                continue
            if lid in out and out[lid][0] != macro:
                clash.append((lid, out[lid], (macro, name)))
            out.setdefault(lid, (macro, name))
    # Overrides: literals whose macro prints a different value on purpose
    # (the text is corrected to what the program gives). They are written
    # by the editor of the conversion after reading the discrepancy files.
    every = None
    for p in sorted(WORK.glob("override_*.json")):
        if every is None:
            every = other_items("")
        for lid, macro in json.loads(p.read_text(encoding="utf-8")).items():
            assert macro in every, (p.name, lid, macro)
            if lid in out and out[lid][0] != macro:
                clash.append((lid, out[lid], (macro, p.stem)))
            out[lid] = (macro, p.stem)
    return out, clash


def notes(kind: str):
    """_work/<kind>_*.json merged: 'nosource' (no machine-readable output
    holds the number) or 'discrepancy' (the program gives another value)"""
    out = {}
    for p in sorted(WORK.glob(f"{kind}_*.json")):
        out.update(json.loads(p.read_text(encoding="utf-8")))
    return out


def region(tag: str, a: int, b: int):
    """the literals of lines a..b of a file, with what was decided"""
    inv = inventory()
    out, _ = all_assignments()
    keep, nos, dis = kept(), notes("nosource"), notes("discrepancy")
    for lid, r in inv.items():
        if lid.split(":")[0] != tag or not a <= int(r["line"]) <= b:
            continue
        state = ("\\" + out[lid][0] if lid in out else
                 "KEEP " + str(keep[lid]) if lid in keep else
                 "NOSOURCE" if lid in nos else
                 "DISCREPANCY" if lid in dis else "-")
        print(f"{lid}\t{r['line']}\t{r['literal']}\t{r['mode']}\t{state}\t"
              f"{r['context']}")


def kept():
    """literals that stay words of the text, with the reason: calendar
    labels of sources, grade spans, units such as 'per 100', and the like
    (_work/keep_*.json, each {identifier: reason})"""
    out = {}
    for p in sorted(WORK.glob("keep_*.json")):
        out.update(json.loads(p.read_text(encoding="utf-8")))
    return out


def status():
    inv = inventory()
    out, clash = all_assignments()
    keep = kept()
    both = sorted(set(out) & set(keep))
    left = [i for i in inv if i not in out and i not in keep]
    nos = [i for i in notes("nosource") if i in left]
    dis = [i for i in notes("discrepancy") if i in left]
    print(f"{len(inv)} literals: {len(out)} macros, {len(keep)} kept as "
          f"text, {len(left)} left ({len(nos)} without a source file, "
          f"{len(dis)} where the program gives another value), "
          f"{len(clash)} claimed twice, {len(both)} both assigned and kept")
    for c in clash[:20]:
        print("  CLASH", *c)
    by = {}
    for i in left:
        by[inv[i]["file"]] = by.get(inv[i]["file"], 0) + 1
    for k, v in by.items():
        print(f"  {v:5d} left in {k}")
    return left


def render(rel, inv, out):
    """the snapshot of one file with every assigned literal replaced"""
    with open(SNAP / rel, encoding="utf-8", newline="") as fh:
        lines = fh.read().replace("\r\n", "\n").split("\n")
    ids = [i for i in out if inv[i]["file"] == rel]
    for i in sorted(ids, key=lambda i: (-int(inv[i]["line"]), -int(inv[i]["c0"]))):
        r = inv[i]
        ln, a, b = int(r["line"]) - 1, int(r["c0"]), int(r["c1"])
        assert lines[ln][a:b] == r["literal"], (i, lines[ln][a:b])
        nxt = lines[ln][b:b + 1]
        macro = "\\" + out[i][0]
        if r["mode"] == "text" or nxt.isalpha():
            macro += "{}"       # a control word swallows the space after it
        lines[ln] = lines[ln][:a] + macro + lines[ln][b:]
    return "\n".join(lines), len(ids)


def apply():
    """Write the manuscript files as snapshot + assignments. Idempotent: it
    always starts from the snapshot, so it can be rerun as assignments
    arrive. A file that someone edited since the last rendering (or since
    the snapshot) is left alone and reported."""
    inv = inventory()
    out, clash = all_assignments()
    assert not clash, clash[:5]
    last = WORK / "rendered"
    n = 0
    for rel in FILES:
        with open(MS / rel, encoding="utf-8", newline="") as fh:
            raw = fh.read()
        crlf = "\r\n" in raw
        live = raw.replace("\r\n", "\n")
        ref = last / rel if (last / rel).exists() else SNAP / rel
        with open(ref, encoding="utf-8", newline="") as fh:
            expected = fh.read().replace("\r\n", "\n")
        if live != expected:
            print(f"  {rel} was edited outside this tool: skipped")
            continue
        text, k = render(rel, inv, out)
        with open(MS / rel, "w", encoding="utf-8", newline="") as fh:
            fh.write(text.replace("\n", "\r\n") if crlf else text)
        (last / rel).parent.mkdir(parents=True, exist_ok=True)
        with open(last / rel, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        n += k
    print(f"{n} literals are macros in the manuscript")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "snapshot":
        snapshot()
    elif cmd == "check":
        check(sys.argv[2])
    elif cmd == "apply":
        apply()
    elif cmd == "region":
        region(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    else:
        status()
