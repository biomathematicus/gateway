"""Write the macro files of the manuscript.

Runs each `m_<name>.py` module of this folder and writes, under
`programs/figures/macros/`, two files per module, in the layout of the
`*_newcommands.tex` / `*_renewcommands.tex` pairs the PI uses elsewhere:

    <name>_newcommands.tex    a `\\newcommand` for every macro of the module,
                              set to `\\WarningRunPipeline`, so that a number
                              no program supplied is visible in the PDF;
    <name>_renewcommands.tex  the values, one `\\renewcommand` per line.

and two index files the manuscript inputs:

    newcommands.tex           defines `\\WarningRunPipeline`, the initial
                              value of every macro: the words RUN THE
                              PIPELINE in bold red (the document loads
                              xcolor); then inputs every
                              <name>_newcommands.tex (preamble)
    renewcommands.tex         inputs every <name>_renewcommands.tex (after
                              \\begin{document})

A macro whose value is missing therefore prints the red warning wherever
the text uses it. The index files also hold two macros about the macros
themselves: `\\MacroTotal`, the number of quantities the modules name,
and `\\MacroModulesWord`, the number of modules.

A file is rewritten only when its macros changed, so the "Generated" line
of a file is the time its values last changed.

    python make_macros.py            write everything
"""
import datetime
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import texmacros as T  # noqa: E402


#: What a quantity prints until its value is assigned. \providecommand
#: lets a document set its own warning before the index file is read.
WARNING = ("\\providecommand{\\WarningRunPipeline}"
           "{\\textcolor{red}{\\textbf{[RUN THE PIPELINE]}}}")


def modules():
    return sorted(p.stem for p in HERE.glob("m_*.py"))


def _body(text: str) -> str:
    """a macro file without its 'Generated' line"""
    return "\n".join(ln for ln in text.split("\n") if "Generated:" not in ln)


def write(path: Path, text: str) -> bool:
    """write the file unless only its 'Generated' line would change"""
    if path.exists() and _body(path.read_text(encoding="utf-8")) == _body(text):
        return False
    path.write_text(text, encoding="utf-8")
    return True


def main():
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    seen, done, changed = {}, [], 0
    T.OUT.mkdir(parents=True, exist_ok=True)
    for mod_name in modules():
        mod = importlib.import_module(mod_name)
        name = mod_name[2:]
        items = mod.build()
        for k in items:
            assert k not in seen, f"\\{k} is defined in {seen[k]} and {mod_name}"
            seen[k] = mod_name
        title = getattr(mod, "TITLE", name)
        source = getattr(mod, "SOURCE", "")
        changed += write(
            T.OUT / f"{name}_newcommands.tex",
            f"% {title}: LaTeX commands (placeholders)\n"
            f"% Generated: {stamp} by programs/macros/{mod_name}.py\n\n"
            + "".join(f"\\newcommand{{\\{k}}}{{\\WarningRunPipeline}}\n"
                      for k in items))
        changed += write(
            T.OUT / f"{name}_renewcommands.tex",
            f"% {title}: actual values\n"
            f"% Generated: {stamp} by programs/macros/{mod_name}.py\n"
            + (f"% Source: {source}\n" if source else "") + "\n"
            + "".join(f"\\renewcommand{{\\{k}}}{{{v}}}\n"
                      for k, v in items.items()))
        done.append((name, len(items)))
    # macros about the macros: how many quantities, in how many modules
    meta = {"MacroTotal": T.fmt(len(seen), "int"),
            "MacroModulesWord": T.fmt(len(done), "word")}
    head = {
        "newcommands":
            "% Initial value of every quantity: a warning in bold red. A\n"
            "% quantity keeps it until a renewcommands file assigns its\n"
            "% value, so a missing run of the pipeline shows in the PDF.\n"
            "% The document loads xcolor.\n"
            + WARNING + "\n"
            + "".join(f"\\newcommand{{\\{k}}}{{\\WarningRunPipeline}}\n"
                      for k in meta),
        "renewcommands":
            "".join(f"\\renewcommand{{\\{k}}}{{{v}}}\n"
                    for k, v in meta.items()),
    }
    for kind in ("newcommands", "renewcommands"):
        changed += write(
            T.OUT / f"{kind}.tex",
            f"% Index of the {kind} files, written by\n"
            "% programs/macros/make_macros.py. \\MacroDir is set in main.tex.\n"
            f"% Generated: {stamp}\n"
            + head[kind]
            + "".join(f"\\input{{\\MacroDir {n}_{kind}}}\n" for n, _ in done))
    for n, k in done:
        print(f"  {n:18s} {k:4d} macros")
    print(f"  {len(seen)} macros in {len(done)} modules, written to {T.OUT} "
          f"({changed} files changed)")


if __name__ == "__main__":
    main()
