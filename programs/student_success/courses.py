"""
Canonical UTSA mathematics course names, and the gateway sequence.

WHY THIS EXISTS. `SHRTCKN_CRSE_TITLE` is a free-text field truncated to about
30 characters, and its spelling drifted across the 2012-2019 window. One course
appears under many titles:

    Algebra with Calculus for Bus / Algebra w Calculus for Bus /
    Algebra w/ Calculus for Bus   / Algebra Calculus for Bus
    Algebra-Scientists & Engineers / Algebra-ScientistsEngineers /
    Algebra-Scientist&Engineer     / Algebra-Scientists&Engineer
    College Algebra w/Applications / College Algebra w/App

Grouping on the raw title therefore splits a single course into fragments and
silently understates its enrolment. An earlier version of report 014 selected
its "top five courses by volume" on fragmented titles, which is how a 15-student
cell reached a results table.

Canonicalisation works on a punctuation-free lowercase key, so spacing and
ampersand variants collapse before any rule is applied.
"""

from __future__ import annotations

import re

# The gateway sequence, in order. Report 016 uses adjacency here to ask whether
# a student's NEXT course still shows the instrument gap.
SEQUENCE = ["Intermediate Algebra",
            "College Algebra with Applications",
            "Precalculus",
            "Calculus I",
            "Calculus II",
            "Calculus III"]

#: courses that are a terminal/parallel track rather than a rung of SEQUENCE
PARALLEL = ["Algebra with Calculus for Business",
            "Algebra for Scientists & Engineers",
            "Calculus for the Biosciences"]


def _key(title: str) -> str:
    """Punctuation-free lowercase key: `Algebra w/ Calc` -> `algebrawcalc`."""
    return re.sub(r"[^a-z0-9]", "", str(title).lower())


def canon(title: str) -> str:
    """Map a raw SHRTCKN_CRSE_TITLE onto a canonical course name.

    Titles outside the rules below are returned whitespace-normalised with a
    trailing `(Q)` marker stripped, so unrecognised courses stay distinct
    rather than being silently merged.
    """
    k = _key(title)
    k = re.sub(r"q$", "", k)                      # trailing (Q) quantitative flag

    if k.startswith("precalculus"):
        return "Precalculus"
    # exact rungs -- 'calculusi' must not swallow 'calculusii'
    if k in ("calculusi",):
        return "Calculus I"
    if k in ("calculusii",):
        return "Calculus II"
    if k in ("calculusiii",):
        return "Calculus III"
    if "biosciences" in k:
        return "Calculus for the Biosciences"
    if k.startswith("algebra") and "calculus" in k and "bus" in k:
        return "Algebra with Calculus for Business"
    if k.startswith("algebra") and "scientist" in k:
        return "Algebra for Scientists & Engineers"
    if k.startswith("collegealgebra"):
        return "College Algebra with Applications"
    if k.startswith("intermediatealgebra"):
        return "Intermediate Algebra"

    t = re.sub(r"\s*\(\s*Q\s*\)\s*$", "", str(title).strip())
    return re.sub(r"\s+", " ", t)


def next_in_sequence(course: str) -> str | None:
    """The rung after `course`, or None if it is terminal or off-ladder."""
    if course in SEQUENCE and SEQUENCE.index(course) + 1 < len(SEQUENCE):
        return SEQUENCE[SEQUENCE.index(course) + 1]
    return None
