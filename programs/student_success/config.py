"""Central configuration for the Python figure pipeline.

Mirrors the conventions of script/aaPipeline.m. All tunable parameters
(top-N, FDR level, p-value display floor, fonts) live here.
"""
import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent          # programs/student_success
# Local cache of query results. It holds student-level rows, so it lives
# outside the repository and outside any synchronized folder: the folder
# named by GATEWAY_CACHE, or a folder of the local user profile.
PKL_DIR = Path(os.environ.get("GATEWAY_CACHE") or (
    Path(os.environ.get("LOCALAPPDATA") or Path.home())
    / "gateway_cache" / "pkl"))
IMG_DIR = PKG_DIR.parent / "figures" / "student_success"
# path prefix used inside the TeX \includegraphics snippets
TEX_GRAPHICS_PREFIX = "figures/student_success/"

CONN_STRING = (
    "Driver={ODBC Driver 17 for SQL Server};"
    "Server=.;Database=UTSA;Trusted_Connection=yes;"
)

# Analysis window (matches aaPipeline.m: 2014 Fall - 2019 Fall)
S_START = "2014.66"
S_END = "2019.66"

# Subject used for the donor/acceptor chord diagrams (matches aaPipeline.m)
CHORD_SUBJECT = "MAT"

# Cohort-restricted odds-ratio analysis (removes transfer/censoring bias):
# first-time freshmen entering in this window, followed for HORIZON years
COHORT_ENTRY_START = "2014.66"
COHORT_ENTRY_END = "2015.66"
COHORT_HORIZON_YEARS = 4.0

# Course-level bands (CT_SUBJECT course numbers)
ENTRY_LEVEL_MAX = 2000    # 1000-level = entry courses (< 2000)
UPPER_LEVEL_MIN = 3000    # upper division (>= 3000)

# --- Tunable display parameters -------------------------------------------
CHORD_LABEL_SIZE = 20    # sector label font (pt) for the chord diagrams
CHORD_BODY_LABEL_SIZE = 24   # body chord: names must stay legible when
                             # the figure is set at the page's text width
CHORD_BODY_PNG_DPI = 600     # body chord: raster copy at 600 x 600 dpi so
                             # that zooming into the PNG keeps its detail
                             # (PI direction, 2026-11-20); the PDF the
                             # manuscript includes is vector
TOP_N_MAJORS = 24        # chord: majors named individually; rest -> Other

# Rotation anchor for the chords: one major is placed at CHORD_ANCHOR_DEG
# measured counter-clockwise from the 3 o'clock direction (standard
# mathematical convention). The whole ring rotates rigidly, so the size
# ordering of sectors is unchanged. With CHORD_ANCHOR_MAJOR = None the
# anchor is the major with the longest name: at 135 degrees its radial
# label points to the upper-left corner of the page, where a long label
# has the most room (PI direction, 2026-11-20).
CHORD_ANCHOR_MAJOR = None
CHORD_ANCHOR_DEG = 135.0

# Body chord and its index table: the majors with the smallest total flow
# are collected in one gray "Other" sector, because their arcs are too
# short to see on the page (PI direction, 2026-11-20). With 14, the
# sector holds every major that exchanged fewer than 225 students: Music,
# General (COA), Anthropology, Non Degree Seeking, General (COEHD),
# Geological Sciences, Public Administration, Modern Languages &
# Literatures, Race, Ethnicity, Gender and Sexuality Studies, Undeclared
# - GATES, COPP (Admin Unit), Counseling, Bicultural/Bilingual Studies,
# and Social Work (first 8, then 14 on the PI's second pass).
CHORD_OTHER_SMALLEST = 14

# Sectors are labeled with the major's name. The single-word codes used
# before 2026-11-20 (MAJOR_WORD) were retired: some majors hold several
# registrar subject codes, so no one code stands for a major.
Q_FDR = 0.001            # Benjamini-Hochberg q for the statistical helpers

# --- Color scheme (validated palette; see dataviz skill) -------------------
# Categorical slots, fixed assignment by college - never cycled.
COLLEGE_COLORS = {
    "Sciences": "#2a78d6",                                  # blue
    "Business": "#eb6834",                                  # orange
    "Engineering": "#1baf7a",                               # aqua
    "Liberal and Fine Arts": "#eda100",                     # yellow
    "Education & Human Development": "#e87ba4",             # magenta
    "University College": "#008300",                        # green
    "Architecture, Construction and Planning": "#4a3aa7",   # violet
    "Public Policy": "#e34948",                             # red
}
COLLEGE_OTHER_COLOR = "#898781"   # Honors, NA, OUS, unmapped, "Other" band

# Diverging pair (red = adverse/below norm, blue = favorable/above norm)
ROSE_HARMFUL = "#e34948"
ROSE_BENEFICIAL = "#2a78d6"

INK = "#0b0b0b"
INK_MUTED = "#898781"
GRID = "#e1e0d9"

# Fallback mapping for majors (OIR DEPARTMENT values) that are not
# departments in the DEPT cross-reference table.
MAJOR_COLLEGE_FALLBACK = {
    "University College": "University College",
    "General (COB)": "Business",
    "General (COS)": "Sciences",
    "General (COE)": "Engineering",
    "General (COEHD)": "Education & Human Development",
    "General (COLFA)": "Liberal and Fine Arts",
    "General (COA)": "Architecture, Construction and Planning",
    "General (CDA)": "Architecture, Construction and Planning",
    "COPP (Admin Unit)": "Public Policy",
    "Public Administration": "Public Policy",
}
