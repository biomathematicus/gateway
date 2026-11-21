"""Circos/chord diagrams for donor/acceptor major flows.

Replaces the alluvial figures of aDonorAcceptor.m. Arc length of each major
is proportional to its total students (donated + received). Ribbons are
directed (donor -> acceptor) and inherit the donor's color. Sectors are
colored by college and ordered by size around the circle.

Sectors are labeled with the major's NAME. Single-word codes were used
until 2026-11-20 and were retired because some majors hold several
registrar subject codes, so no one code stands for a major.

Publication rule. A ribbon is a count of students: its width on the ring
is proportional to the students of one donor-acceptor pair, and a vector
figure lets a reader recover that count. Every chord is therefore drawn
from drawn_flows(), which keeps the flows of at least MIN_FLOW students
and sizes each sector by the flows that remain, so that no ribbon, no arc,
and no row of the index table rests on fewer students. The figure of the
manuscript is written with the flows it draws
(figChord-<subject>-majors_flows.csv), and
tools/chord_geometry_check.py recovers the counts from the PDF itself.
"""
import csv
import json

import pandas as pd
from pycirclize import Circos

import config
import data
from db import term_str
from texout import save_figure


NARROW_DEG = 4.0   # sectors narrower than this keep their name on one line
MIN_FLOW = 10      # publication rule: fewest students a drawn flow may hold


def drawn_flows(matrix: pd.DataFrame,
                min_flow: int = MIN_FLOW) -> tuple[pd.DataFrame, dict]:
    """The flows a figure may show, and what was withheld.

    A flow of fewer than `min_flow` students is set to zero, and a major
    left without any flow is dropped. Sector sizes are computed from the
    returned matrix, so a withheld flow leaves no trace in the geometry:
    the figure and its index table state the drawn flows only, and the
    withheld flows are reported as two totals.
    """
    small = (matrix > 0) & (matrix < min_flow)
    drawn = matrix.where(matrix >= min_flow, 0)
    keep = [m for m in drawn.index
            if drawn.loc[m].sum() + drawn[m].sum() > 0]
    drawn = drawn.loc[keep, keep]
    positive = drawn.values[drawn.values > 0]
    return drawn, {
        "min_flow": min_flow,
        "n_sectors": len(keep),
        "n_drawn_flows": int(positive.size),
        "n_drawn_students": int(positive.sum()),
        "min_drawn_flow": int(positive.min()) if positive.size else 0,
        "n_withheld_flows": int(small.values.sum()),
        "n_withheld_students": int(matrix.values.sum() - positive.sum()),
    }


def _clean(name: str) -> str:
    """Major name with stray double spaces of the source normalized."""
    return " ".join(name.split())


def _sector_order(matrix: pd.DataFrame, colleges: dict[str, str]) -> list[str]:
    """Size order: largest first, descending clockwise; the aggregate
    Other band always last."""
    total = matrix.sum(axis=1) + matrix.sum(axis=0)
    names = list(total.sort_values(ascending=False).index)
    if "Other" in names:
        names.remove("Other")
        names.append("Other")
    return names


def _sector_space(n: int) -> float:
    return max(0.3, 120 / n)


def sector_geometry(matrix: pd.DataFrame, order: list[str],
                    offset: float = 0.0) -> dict[str, tuple[float, float]]:
    """major -> (center angle in MATH degrees, angular width).

    Math degrees are measured counter-clockwise from the 3 o'clock
    direction, matching how the figure is read on the page. pycirclize
    lays sectors out clockwise from 12 o'clock, so the two conventions
    are related by math = (90 - pycirclize) mod 360.
    """
    total = (matrix.sum(axis=1) + matrix.sum(axis=0)).reindex(order)
    n = len(order)
    space = _sector_space(n)
    widths = (360 - n * space) * total / total.sum()
    geom, deg = {}, 0.0
    for m, w in zip(order, widths):
        geom[m] = ((90 - (offset + deg + w / 2)) % 360, float(w))
        deg += w + space
    return geom


def anchor_major(order: list[str]) -> str:
    """The sector placed at config.CHORD_ANCHOR_DEG: the configured major,
    or by default the major with the longest name, whose label needs the
    room of the page's diagonal (ties go to the larger sector)."""
    if config.CHORD_ANCHOR_MAJOR in order:
        return config.CHORD_ANCHOR_MAJOR
    named = [m for m in order if m != "Other"]
    return max(named, key=lambda m: len(_clean(m)))


def rotation_offset(matrix: pd.DataFrame, order: list[str],
                    target_deg: float = config.CHORD_ANCHOR_DEG) -> float:
    """Rigid rotation putting the anchor major at `target_deg` (math
    degrees). Returns the pycirclize start angle; sector order is
    untouched."""
    base = sector_geometry(matrix, order, 0.0)[anchor_major(order)][0]
    off = (base - target_deg) % 360
    # pycirclize needs -360 <= start < end <= 360, so the start angle is
    # kept in (-360, 0]; the rotation is the same
    return off - 360 if off > 0 else off


def _display_names(matrix: pd.DataFrame, order: list[str],
                   plain_q2: bool, offset: float = 0.0) -> dict[str, str]:
    """Per-sector display label: the major's name. When plain_q2 is set,
    a name stays on one line where a second line would collide or is not
    needed: in the upper-left quadrant (the page's corner gives a radial
    label room) and on narrow sectors, whose neighbors are close. All
    other names wrap at two words per line."""
    geom = sector_geometry(matrix, order, offset)
    return {m: (_clean(m) if plain_q2 and (90 < geom[m][0] <= 180
                                           or geom[m][1] < NARROW_DEG)
                else _wrap(m)) for m in order}


def _wrap(name: str, max_words: int = 2) -> str:
    """Break long major names into lines of at most max_words words."""
    words = name.split()
    return "\n".join(" ".join(words[i:i + max_words])
                     for i in range(0, len(words), max_words))


def _draw(matrix: pd.DataFrame, label_size: float, ticks_interval: int | None,
          figsize: float, plain_q2: bool = False,
          rotate: bool = False) -> "Circos":
    colleges = data.major_college()
    raw_order = _sector_order(matrix, colleges)
    offset = rotation_offset(matrix, raw_order) if rotate else 0.0
    disp = _display_names(matrix, raw_order, plain_q2, offset)
    cmap = {disp[m]: data.college_color(colleges.get(m))
            for m in matrix.index}
    order = [disp[m] for m in raw_order]
    circos = Circos.chord_diagram(
        matrix.rename(index=disp, columns=disp),
        start=offset,
        end=offset + 360,
        space=_sector_space(len(matrix)),
        r_lim=(93, 100),
        cmap=cmap,
        order=order,
        ticks_interval=ticks_interval,
        label_kws=dict(size=label_size,
                       r=105 if ticks_interval else 101.5,
                       orientation="vertical"),
        ticks_kws=dict(label_size=max(2.0, label_size * 0.35),
                       label_orientation="vertical"),
        link_kws=dict(direction=1, ec="none", alpha=0.55, lw=0),
    )
    return circos.plotfig(figsize=(figsize, figsize))


def college_legend(fig, matrix: pd.DataFrame, n_merged: int,
                   size: float, ncol: int = 3) -> None:
    """Legend of the colleges below the ring: one swatch per college that
    has a sector in the figure, in the fixed order of
    config.COLLEGE_COLORS, and the gray of the aggregate sector last.

    The legend is anchored under everything already drawn (the sector
    names reach below the ring), centered on the drawing, and laid out in
    `ncol` columns, so it takes several lines. Swatches are opaque, which
    keeps them apart from the ribbons (alpha 0.55) for
    tools/chord_geometry_check.py."""
    from matplotlib.patches import Patch
    colleges = data.major_college()
    present = {colleges.get(m) for m in matrix.index if m != "Other"}
    entries = [(c, col) for c, col in config.COLLEGE_COLORS.items()
               if c in present]
    if "Other" in matrix.index:
        entries.append((f"Other ({n_merged} smallest majors)" if n_merged
                        else "Other", config.COLLEGE_OTHER_COLOR))
    fig.canvas.draw()
    box = fig.get_tightbbox(fig.canvas.get_renderer())      # inches
    width, height = fig.get_size_inches()
    legend = fig.legend(
        handles=[Patch(facecolor=col, edgecolor="none") for _, col in entries],
        labels=[name for name, _ in entries],
        title="College", loc="upper center",
        bbox_to_anchor=((box.x0 + box.x1) / 2 / width,
                        box.y0 / height - 0.012),
        ncol=ncol, frameon=False, fontsize=size, title_fontsize=size,
        handlelength=1.1, handleheight=1.1, handletextpad=0.5,
        columnspacing=2.2, labelspacing=0.45, borderaxespad=0.0)
    legend.get_title().set_fontweight("bold")
    for text in legend.get_texts() + [legend.get_title()]:
        text.set_color(config.INK)


def top_n(matrix: pd.DataFrame, n: int) -> pd.DataFrame:
    """Keep the n largest majors by total flow; aggregate the rest as Other."""
    total = (matrix.sum(axis=1) + matrix.sum(axis=0)).sort_values(ascending=False)
    keep = list(total.index[:n])
    rest = [m for m in matrix.index if m not in keep]
    m = matrix.copy()
    m.loc["Other"] = m.loc[rest].sum(axis=0)
    m["Other"] = m[rest].sum(axis=1)
    return m.drop(index=rest, columns=rest)


def merge_smallest(matrix: pd.DataFrame,
                   k: int = config.CHORD_OTHER_SMALLEST
                   ) -> tuple[pd.DataFrame, list[str]]:
    """Collect the k majors with the smallest total flow into Other.

    Returns the merged matrix and the merged majors, largest first. A
    flow between two merged majors becomes a flow inside Other, so the
    number of students in the matrix is unchanged.
    """
    if not k:
        return matrix, []
    total = (matrix.sum(axis=1) + matrix.sum(axis=0)).sort_values(
        kind="stable")
    rest = list(total.index[:k])
    m = matrix.copy()
    m.loc["Other"] = m.loc[rest].sum(axis=0)
    m["Other"] = m[rest].sum(axis=1)
    return m.drop(index=rest, columns=rest), rest[::-1]


def _body(df: pd.DataFrame):
    """Drawn matrix, merged majors, sector order, geometry, and the
    account of what was drawn and withheld, for the body chord; the
    figure and its index table share them.

    The smallest majors are collected in Other first, so that their flows
    with a named major add up before the minimum is applied; then every
    flow under the minimum is withheld."""
    full = data.flow_matrix(df)
    merged_matrix, merged = merge_smallest(full)
    m, account = drawn_flows(merged_matrix)
    account = {"n_students": int(full.values.sum()),
               "n_majors": int(len(full)), "n_merged": len(merged),
               **account}
    order = _sector_order(m, data.major_college())
    geom = sector_geometry(m, order, rotation_offset(m, order))
    return m, merged, order, geom, account


def chord_majors(df: pd.DataFrame, subject: str) -> str:
    """Body figure: every sector labeled with its major's name, the
    smallest majors collected in Other, the longest name on the page's
    upper-left diagonal. Flows of fewer than MIN_FLOW students are not
    drawn."""
    m, merged, order, _, stats = _body(df)
    assert stats["min_drawn_flow"] >= MIN_FLOW
    assert stats["n_drawn_students"] + stats["n_withheld_students"] == \
        stats["n_students"]
    fig = _draw(m, label_size=config.CHORD_BODY_LABEL_SIZE,
                ticks_interval=None, figsize=24, plain_q2=True, rotate=True)
    # a little larger than the sector names: the legend is read first
    college_legend(fig, m, len(merged),
                   size=1.2 * config.CHORD_BODY_LABEL_SIZE)
    # the quantities the text quotes from this figure
    (config.IMG_DIR / f"figChord-{subject}-majors_stats.json").write_text(
        json.dumps(stats, indent=1), encoding="utf-8")
    # the flows the figure draws: its backing data, every cell at or above
    # the minimum
    with open(config.IMG_DIR / f"figChord-{subject}-majors_flows.csv", "w",
              newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["donor", "acceptor", "n_students"])
        for donor in order:
            for acceptor in order:
                if m.loc[donor, acceptor] > 0:
                    w.writerow([_clean(donor), _clean(acceptor),
                                int(m.loc[donor, acceptor])])
    return save_figure(
        fig, f"figChord-{subject}-majors",
        f"Major-change flows among students who took {subject} "
        "courses and changed major "
        f"({term_str(config.S_START)}--{term_str(config.S_END)}). The "
        f"figure draws the {stats['n_drawn_flows']:,} flows of at least "
        f"{MIN_FLOW} students, which hold {stats['n_drawn_students']:,} of "
        f"the {stats['n_students']:,} students; the "
        f"{stats['n_withheld_flows']:,} smaller flows are not drawn. Each "
        "sector is one major, labeled with its name; "
        "Table~\\ref{tab:majorangles} indexes every sector by angular "
        "position. Arc length is proportional to the students of the "
        "drawn flows, donated plus received; ribbons point from donor to "
        "acceptor and inherit the "
        "donor's color; colors denote college (legend below the ring). "
        f"The {len(merged)} majors "
        "with the smallest total flow are collected in the gray sector "
        "labeled Other. Sectors run clockwise from the largest.",
        png_dpi=config.CHORD_BODY_PNG_DPI, svg=True)


def chord_full(df: pd.DataFrame, subject: str) -> str:
    """Every major that keeps a drawn flow as its own sector (not used
    in the manuscript)."""
    m, account = drawn_flows(data.flow_matrix(df))
    order = _sector_order(m, data.major_college())
    fig = _draw(m, label_size=config.CHORD_LABEL_SIZE,
                ticks_interval=None, figsize=24, plain_q2=True, rotate=True)
    return save_figure(
        fig, f"figChord-{subject}-all",
        f"Donor and acceptor majors among students who took {subject} "
        f"courses and changed major ({term_str(config.S_START)}--{term_str(config.S_END)}): "
        f"the {account['n_drawn_flows']:,} flows of at least {MIN_FLOW} "
        f"students ({account['n_drawn_students']:,} students). "
        "Arc length is proportional to the number of students donated plus "
        "received; ribbons point from donor to acceptor and inherit the donor's "
        "color. Sectors run clockwise from the largest, and the ring is "
        "rotated rigidly so that "
        f"{_clean(anchor_major(order))} sits at "
        f"{config.CHORD_ANCHOR_DEG:g}$^\\circ$. Colors denote college. "
        "Vector figure: magnify for detail.")


def chord_top_n(df: pd.DataFrame, subject: str,
                n: int = config.TOP_N_MAJORS) -> str:
    full = data.flow_matrix(df)
    m, account = drawn_flows(top_n(full, n))
    fig = _draw(m, label_size=config.CHORD_LABEL_SIZE,
                ticks_interval=1000, figsize=14)
    return save_figure(
        fig, f"figChord-{subject}-top{n}",
        f"Major-change flows among students who took {subject} courses "
        f"({term_str(config.S_START)}--{term_str(config.S_END)}), top {n} majors by total flow; "
        "remaining majors are "
        "aggregated in the gray Other band. The figure draws the "
        f"{account['n_drawn_flows']:,} flows of at least {MIN_FLOW} "
        "students. Arc length is proportional to "
        "students donated plus received; ribbons point from donor to acceptor.")


def _tex_escape(s: str) -> str:
    s = _clean(s)              # normalize stray double spaces in DB labels
    s = s.replace("&", "\\&").replace("%", "\\%").replace("_", "\\_")
    # let long slashed names (Bicultural/Bilingual) wrap inside p-columns
    return s.replace("/", "/\\allowbreak{}")


def _two_panel_table(rows: list[tuple[str, ...]], headers: tuple[str, ...],
                     colspec: str, label: str, caption: str,
                     size: str = "\\small") -> str:
    """Render rows as two side-by-side panels so a ~50-row table fits on
    one page without extra packages."""
    half = (len(rows) + 1) // 2
    left, right = rows[:half], rows[half:]
    right += [("",) * len(headers)] * (len(left) - len(right))
    head = " & ".join(f"\\textbf{{{h}}}" for h in headers)
    out = ["\\begin{table}[tbp]", "  \\centering", f"  {size}",
           "  \\setlength{\\tabcolsep}{4pt}",
           f"  \\caption{{{caption}}}", f"  \\label{{{label}}}",
           f"  \\begin{{tabular}}{{{colspec}@{{\\quad}}{colspec}}}",
           "    \\toprule",
           f"    {head} & {head} \\\\", "    \\midrule"]
    for a, b in zip(left, right):
        cells = " & ".join(_tex_escape(c) for c in a + b)
        out.append(f"    {cells} \\\\")
    out += ["    \\bottomrule", "  \\end{tabular}", "\\end{table}", ""]
    return "\n".join(out)


MIN_CELL = 10   # publication rule: no printed count may rest on fewer students


def _general_note(order: list[str]) -> str:
    """'Business (COB), Engineering (COE), ...' for the General majors on
    the ring, from the college each one maps to."""
    colleges = data.major_college()
    items = []
    for x in order:
        if x.startswith("General (") and x.endswith(")"):
            items.append(f"{_tex_escape(colleges.get(x, x))} "
                         f"({x[len('General ('):-1]})")
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def major_tables(df: pd.DataFrame) -> list[str]:
    """Angular index of the body chord: major name -> degrees and size,
    keyed to the figure's geometry."""
    m, merged, order, geom, _ = _body(df)
    total = m.sum(axis=1) + m.sum(axis=0)
    assert (total[order] >= MIN_CELL).all()

    names = [_clean(x) for x in merged]
    other_note = ""
    if merged:
        other_note = (
            f" Other collects the {len(merged)} majors with the smallest "
            "total flow, whose sectors would be too small to see: "
            + "; ".join(_tex_escape(x) for x in names[:-1])
            + "; and " + _tex_escape(names[-1]) + ".")
    # alphabetical by major, the aggregate sector last
    idx = [(_clean(x), f"{geom[x][0]:.0f}$^\\circ$",
            f"{int(total[x]):,}" if total[x] >= MIN_CELL else "$<$10")
           for x in sorted(order, key=lambda x: (x == "Other",
                                                  _clean(x).lower()))]
    p = config.IMG_DIR / "tabMajorAngles.tex"
    p.write_text(_two_panel_table(
        idx, ("Major", "Angle", "N"),
        ">{\\raggedright\\arraybackslash}p{5.0cm}rr", "tab:majorangles",
        "Angular index to the chord diagram of "
        "Figure~\\ref{figChordShort}: every major in alphabetical "
        "order, the approximate angular position of its sector center "
        "(degrees counter-clockwise from the 3 o'clock direction), and "
        "$N$, the number of students it donated plus received in the "
        f"flows the figure draws (flows of at least {MIN_FLOW} students). The "
        "majors named General are the college-wide undeclared or "
        "general-studies majors of the college in parentheses: "
        # the General majors inside Other are expanded too: the list of
        # merged majors names them
        + _general_note(order + merged) + "." + other_note,
        size="\\footnotesize"),
        encoding="utf-8")
    return [str(p)]


def generate() -> None:
    df = data.donor_acceptor(config.CHORD_SUBJECT)
    print(f"donor/acceptor {config.CHORD_SUBJECT}: {len(df):,} students")
    print(" ", chord_majors(df, config.CHORD_SUBJECT))
    print(" ", chord_full(df, config.CHORD_SUBJECT))
    print(" ", chord_top_n(df, config.CHORD_SUBJECT))
    for p in major_tables(df):
        print(" ", p)


if __name__ == "__main__":
    generate()
