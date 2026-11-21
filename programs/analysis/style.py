"""
Shared figure style.

Palette is the dataviz reference categorical instance, slots 1-3, validated with
`scripts/validate_palette.js --mode light`:

    Lightness band       PASS  all 3 inside L 0.43-0.77
    Chroma floor         PASS  all 3 >= 0.1
    CVD separation       PASS  worst adjacent #1baf7a-#eb6834 dE 9.2 (deutan)
    Normal-vision floor  PASS  worst adjacent dE 27.6
    Contrast vs surface  RELIEF REQUIRED  #1baf7a is 2.74:1

The contrast relief obligation is discharged by every figure shipping a CSV
table beside it and by direct labels on the marks that use slot 3 — it is not
dismissable, so no figure may rely on that hue alone to carry a value.

Marks follow the skill: 2px lines, >=8px markers, recessive grid and axes, no
number on every point, and never a second y-axis.
"""

from __future__ import annotations

import os

import matplotlib as mpl
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIGDIR = os.path.abspath(os.path.join(HERE, "..", "figures"))
os.makedirs(FIGDIR, exist_ok=True)

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#9a9a94"


def setup() -> None:
    mpl.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": MUTED,
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "grid.color": "#e6e5e0",
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "text.color": INK,
        "axes.labelcolor": INK2,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "font.size": 10,
        "axes.titlesize": 12,
        "figure.dpi": 140,
        "savefig.dpi": 140,
        "savefig.bbox": "tight",
        "legend.frameon": False,
    })


def finish(fig, ax, slug: str, title: str, caption: str = "",
           grid: bool = True) -> str:
    """Title above, caption below, save to figures/<slug>.png, return rel path."""
    if not grid:
        ax.grid(False)
    ax.set_title(title, loc="left", pad=12, color=INK, fontweight="bold")
    if caption:
        fig.text(0.005, -0.045, caption, ha="left", va="top",
                 fontsize=8.5, color=INK2, wrap=True)
    path = os.path.join(FIGDIR, f"{slug}.png")
    fig.savefig(path)
    # vector twin for manuscript inclusion (Paper0 uses PDF figures)
    fig.savefig(path[:-4] + ".pdf")
    plt.close(fig)
    return f"../figures/{slug}.png"
