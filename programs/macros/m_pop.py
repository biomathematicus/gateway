"""Macros of the study population: the extract and the students active
between Fall 2014 and Fall 2019.

Source: figures/student_success/linkage_profile_stats.json, written by
programs/student_success/linkage_profile.py.
"""
from texmacros import J, Macros

TITLE = "Study population (extract and activity window)"
SOURCE = "figures/student_success/linkage_profile_stats.json"


def build():
    s = J("student_success/linkage_profile_stats.json")
    M = Macros("Pop")
    ex, ac = s["extract_totals"], s["active"]
    rec = s["course_records"]

    # the extract: every student and course record received
    M("ExtractStudents", ex["n_students"], "int")
    M("ExtractRecords", rec["n_extract"], "int")
    M("ExtractTableStudents", ex["n_students_of_credit_table"], "int")

    # students with at least one course record in the window
    c = ac["coverage"]
    M("ActiveStudents", c["n_students"], "int")
    M("ActiveRecords", rec["n_in_window"], "int")
    M("ActiveWithNamePct", c["pct_with_name"], ".1f")
    M("ActiveWithZipPct",
      100 * ac["neighborhood"]["n_with_home_zip"] / c["n_students"], ".2f")
    M("ActiveTexasName", c["n_texas_name"], "int")
    M("ActiveTexasNamePct", 100 * c["n_texas_name"] / c["n_students"], ".1f")

    # the per-student table of pre-college credit
    M("ActiveTableStudents", ac["disposition"]["n_students"], "int")
    # students of the course records whom the per-student table lacks; all
    # of them are active in the window, so the count is the same for both
    assert (c["n_absent_from_student_table"]
            == ex["n_absent_from_student_table"])
    M("TableShortfall", c["n_absent_from_student_table"], "int")
    return M.items
