"""Figure export: vector PDF into report/img plus a matching TeX snippet.

Python analogue of funPrintImage.m. For each figure <name> it writes
  report/img/<name>.pdf   (vector)
  report/img/<name>.png   (raster preview, for quick inspection)
  report/img/<name>.tex   (figure environment; \\input{img/<name>.tex})
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config
from db import sanitize

plt.rcParams.update({
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "font.family": "sans-serif",
    "text.color": config.INK,
    "axes.edgecolor": config.INK_MUTED,
    "xtick.color": config.INK_MUTED,
    "ytick.color": config.INK_MUTED,
})


def save_figure(fig, name: str, caption: str, png_dpi: int = 150,
                svg: bool = False) -> str:
    """Write <name>.pdf (vector, the file the manuscript includes),
    <name>.png (raster copy at png_dpi), and <name>.tex; with svg=True
    also <name>.svg, a second vector copy that editors and browsers open
    directly."""
    config.IMG_DIR.mkdir(parents=True, exist_ok=True)
    name = sanitize(name)
    pdf = config.IMG_DIR / f"{name}.pdf"
    fig.savefig(pdf, bbox_inches="tight")
    if svg:
        fig.savefig(config.IMG_DIR / f"{name}.svg", bbox_inches="tight")
    fig.savefig(config.IMG_DIR / f"{name}.png", dpi=png_dpi,
                bbox_inches="tight")
    plt.close(fig)
    tex = (
        "\\begin{figure}[ht]\n"
        "  \\centering\n"
        f"    \\includegraphics[width=1\\textwidth]"
        f"{{{config.TEX_GRAPHICS_PREFIX}{name}.pdf}}\n"
        f"    \\caption{{{caption}}}\n"
        f"    \\label{{fig:{name}}}\n"
        "\\end{figure}\n"
    )
    (config.IMG_DIR / f"{name}.tex").write_text(tex, encoding="utf-8")
    return str(pdf)
