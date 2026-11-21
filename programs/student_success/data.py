"""Data retrieval and statistics, mirroring the MATLAB pipeline.

- donor_acceptor():   exec spDonorAcceptor  (aDonorAcceptor.m)
- donor_stats():      per-donor-major Wilcoxon rank-sum + BH-FDR (tables 2.2-2.4)
- odds_ratio_all():   exec spOddsRatio per subject + Fisher exact (aOddsRatio.m)
- major_college():    DEPARTMENT -> COLLEGE via the DEPT cross-reference table
"""
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact, mannwhitneyu, ttest_ind
from statsmodels.stats.multitest import multipletests

import config
from db import cached_query


def donor_acceptor(subject: str, s_start: str = config.S_START,
                   s_end: str = config.S_END) -> pd.DataFrame:
    """One row per student who changed major and took `subject` courses."""
    name = f"aDonorAcceptor-{subject}-{s_start}-{s_end}"
    sql = f"exec spDonorAcceptor '{subject}', {s_start}, {s_end}"
    df = cached_query(name, sql,
                      ["id", "donor", "acceptor", "subj_gpa", "other_gpa"])
    df["subj_gpa"] = pd.to_numeric(df["subj_gpa"], errors="coerce")
    df["other_gpa"] = pd.to_numeric(df["other_gpa"], errors="coerce")
    return df


def flow_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Square donor x acceptor count matrix over the union of majors."""
    m = df.groupby(["donor", "acceptor"]).size().unstack(fill_value=0)
    majors = sorted(set(m.index) | set(m.columns))
    return m.reindex(index=majors, columns=majors, fill_value=0)


def donor_stats(df: pd.DataFrame, q: float = config.Q_FDR) -> pd.DataFrame:
    """Per donor major: students who left, GPA ratio, Wilcoxon p, BH-FDR.

    Mirrors aDonorAcceptor.m: ranksum(subject GPA, non-subject GPA) among
    students who left each donor major; ratio = non-subject GPA / subject GPA
    (the 'Ratio' column of tables 2.2-2.4); p-values BH-adjusted, H0 rejected
    at adjusted p < q.
    """
    rows = []
    for major, g in df.groupby("donor"):
        gg = g.dropna(subset=["subj_gpa", "other_gpa"])
        n = len(g)
        if len(gg) >= 2 and gg["subj_gpa"].nunique() + gg["other_gpa"].nunique() > 2:
            p = mannwhitneyu(gg["subj_gpa"], gg["other_gpa"],
                             alternative="two-sided", method="asymptotic").pvalue
        else:
            p = 1.0
        subj = gg["subj_gpa"].mean()
        other = gg["other_gpa"].mean()
        rows.append((major, n, subj, other,
                     other / subj if subj and subj > 0 else np.nan, p))
    t = pd.DataFrame(rows, columns=["major", "students", "subj_gpa",
                                    "other_gpa", "ratio", "p"])
    t = t[t["students"] > 0].reset_index(drop=True)
    reject, p_adj, *_ = multipletests(t["p"].fillna(1.0), alpha=q, method="fdr_bh")
    t["p_adj"] = p_adj
    t["reject"] = reject & (t["p_adj"] < q)
    return t.sort_values("students", ascending=False).reset_index(drop=True)


def subjects() -> list[str]:
    df = cached_query(
        "subjects",
        "select distinct SHRTCKN_SUBJ_CODE from oir order by SHRTCKN_SUBJ_CODE",
        ["subject"])
    return [s for s in df["subject"].tolist() if s and s.strip()]


def odds_ratio_all(s_start: str = config.S_START, s_end: str = config.S_END,
                   q: float = config.Q_FDR, progress=None) -> pd.DataFrame:
    """Per subject: 2x2 exposure table vs 'no 4000-level course', Fisher exact.

    Mirrors aOddsRatio.m. served = a + b (students who took the subject).
    """
    rows = []
    subs = subjects()
    for i, s in enumerate(subs):
        if progress:
            progress(i, len(subs), s)
        name = f"aOddsRatio-{s}-{s_start}-{s_end}"
        sql = f"exec spOddsRatio '{s}', {s_start}, {s_end}"
        o = cached_query(name, sql, ["k", "n"]).set_index("k")["n"]
        a, b, c, d = (int(o.get(k, 0)) for k in (1, 2, 3, 4))
        if min(a + b, c + d) == 0:
            continue
        odds, p = fisher_exact([[a, b], [c, d]])
        with np.errstate(divide="ignore", invalid="ignore"):
            or_ = (a / c) / (b / d) if b * c > 0 else np.nan
        rows.append((s, a, b, c, d, a + b, or_, p))
    t = pd.DataFrame(rows, columns=["subject", "a", "b", "c", "d",
                                    "served", "odds_ratio", "p"])
    reject, p_adj, *_ = multipletests(t["p"].fillna(1.0), alpha=q, method="fdr_bh")
    t["p_adj"] = p_adj
    t["reject"] = reject & (t["p_adj"] < q)
    return t.sort_values("served", ascending=False).reset_index(drop=True)


_COHORT_CTE = """
with C as (
  select IDENTIFIER, min(try_cast(FIRSTTERMCODE as float)) as ft
  from OIR where STUDENTTYPE = 'New'
  group by IDENTIFIER
  having min(try_cast(FIRSTTERMCODE as float)) between {start} and {end}
)
"""


def odds_ratio_cohort(entry_start: str = config.COHORT_ENTRY_START,
                      entry_end: str = config.COHORT_ENTRY_END,
                      horizon: float = config.COHORT_HORIZON_YEARS,
                      q: float = config.Q_FDR,
                      level: str | None = None) -> pd.DataFrame:
    """Cohort-restricted odds ratios on a common entry cohort.

    Population: first-time freshmen (STUDENTTYPE='New') entering in
    [entry_start, entry_end]. Outcome: an enrollment record in a course
    numbered above 4000 inside the declared window (CURRENTTERM <=
    ft + horizon, inclusive; no lower bound). Exposure: took the subject
    within the same window. Unlike spOddsRatio, the unexposed group is
    the rest of the same entry cohort, which removes the entry-pathway
    artifact; exposure and outcome remain contemporaneous, and no other
    confounding is addressed (see manuscript Section 2).
    """
    tag = f"{entry_start}-{entry_end}-{horizon:g}y"
    cte = _COHORT_CTE.format(start=entry_start, end=entry_end)
    outcomes = cached_query(
        f"aCohort-outcomes-{tag}",
        cte + f"""
        select C.IDENTIFIER as id,
               max(case when try_cast(O.CT_SUBJECT as int) > 4000
                        and O.CURRENTTERM <= C.ft + {horizon} then 1
                        else 0 end) as has4k
        from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
        group by C.IDENTIFIER""",
        ["id", "has4k"])
    exp_tag = tag + (f"-{level}" if level else "")
    exposures = cached_query(
        f"aCohort-exposures-{exp_tag}",
        cte + f"""
        select distinct C.IDENTIFIER as id, O.SHRTCKN_SUBJ_CODE as subject
        from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
        where O.CURRENTTERM <= C.ft + {horizon}{_level_filter(level)}""",
        ["id", "subject"])
    has4k = outcomes.set_index("id")["has4k"].astype(int)
    n_all, n_4k = len(has4k), int(has4k.sum())
    rows = []
    for s, g in exposures.groupby("subject"):
        if not s or not s.strip():
            continue
        exp = has4k.reindex(g["id"].unique()).dropna()
        a = int((exp == 0).sum())          # exposed, no 4000-level
        b = int((exp == 1).sum())          # exposed, reached 4000-level
        c = (n_all - n_4k) - a             # unexposed, no 4000-level
        d = n_4k - b                       # unexposed, reached 4000-level
        if min(a + b, c + d) == 0:
            continue
        _, p = fisher_exact([[a, b], [c, d]])
        with np.errstate(divide="ignore", invalid="ignore"):
            or_ = (a / c) / (b / d) if b > 0 and c > 0 and d > 0 else np.nan
        rows.append((s, a, b, c, d, a + b, or_, p))
    t = pd.DataFrame(rows, columns=["subject", "a", "b", "c", "d",
                                    "served", "odds_ratio", "p"])
    reject, p_adj, *_ = multipletests(t["p"].fillna(1.0), alpha=q, method="fdr_bh")
    t["p_adj"] = p_adj
    t["reject"] = reject & (t["p_adj"] < q)
    return t.sort_values("served", ascending=False).reset_index(drop=True)


def _level_filter(level: str | None) -> str:
    """SQL predicate restricting course numbers to a level band."""
    if level is None:
        return ""
    if level == "entry":
        return (f" and try_cast(O.CT_SUBJECT as int) < "
                f"{config.ENTRY_LEVEL_MAX}")
    if level == "upper":
        return (f" and try_cast(O.CT_SUBJECT as int) >= "
                f"{config.UPPER_LEVEL_MIN}")
    raise ValueError(level)


def cohort_subject_gpa(entry_start: str = config.COHORT_ENTRY_START,
                       entry_end: str = config.COHORT_ENTRY_END,
                       horizon: float = config.COHORT_HORIZON_YEARS,
                       level: str | None = None) -> pd.DataFrame:
    """Per (student, subject): mean quality points within the horizon.

    Only rows the registrar counts in the grade average enter the mean
    (SHRGRDE_GPA_IND = 'Y'). Withdrawals and credit / no-credit rows hold
    zero quality points in the source and would otherwise be averaged in
    as failing grades. The cache key says 'graded' so that a cache built
    before this rule is never reused.

    level: None = all courses, 'entry' = 1000-level only, 'upper' = >=3000.
    """
    tag = f"{entry_start}-{entry_end}-{horizon:g}y" + \
          (f"-{level}" if level else "")
    cte = _COHORT_CTE.format(start=entry_start, end=entry_end)
    df = cached_query(
        f"aCohort-subjgpa-graded-{tag}",
        cte + f"""
        select C.IDENTIFIER as id, O.SHRTCKN_SUBJ_CODE as subject,
               avg(O.SHRGRDE_QUALITY_POINTS) as gpa
        from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
        where O.CURRENTTERM <= C.ft + {horizon}
          and O.SHRGRDE_GPA_IND = 'Y'
          and O.SHRGRDE_QUALITY_POINTS is not null{_level_filter(level)}
        group by C.IDENTIFIER, O.SHRTCKN_SUBJ_CODE""",
        ["id", "subject", "gpa"])
    df["gpa"] = pd.to_numeric(df["gpa"], errors="coerce")
    return df.dropna(subset=["gpa"])


def cohort_majors(entry_start: str = config.COHORT_ENTRY_START,
                  entry_end: str = config.COHORT_ENTRY_END,
                  horizon: float = config.COHORT_HORIZON_YEARS
                  ) -> pd.DataFrame:
    """Per student: the first and the last recorded major within the
    horizon. Every caller passes through here, so the cache is always
    read with the query that wrote it."""
    tag = f"{entry_start}-{entry_end}-{horizon:g}y"
    cte = _COHORT_CTE.format(start=entry_start, end=entry_end)
    return cached_query(
        f"aCohort-majors-{tag}",
        cte + f"""
        select C.IDENTIFIER as id,
               (select top 1 O2.DEPARTMENT from OIR O2
                where O2.IDENTIFIER = C.IDENTIFIER
                  and O2.CURRENTTERM <= C.ft + {horizon}
                order by O2.CURRENTTERM asc) as firstmajor,
               (select top 1 O3.DEPARTMENT from OIR O3
                where O3.IDENTIFIER = C.IDENTIFIER
                  and O3.CURRENTTERM <= C.ft + {horizon}
                order by O3.CURRENTTERM desc) as lastmajor
        from C""",
        ["id", "firstmajor", "lastmajor"])


def cohort_major_change(entry_start: str = config.COHORT_ENTRY_START,
                        entry_end: str = config.COHORT_ENTRY_END,
                        horizon: float = config.COHORT_HORIZON_YEARS
                        ) -> pd.Series:
    """Per student: True if first and last major within the horizon differ."""
    df = cohort_majors(entry_start, entry_end, horizon)
    return pd.Series((df["firstmajor"] != df["lastmajor"]).values,
                     index=df["id"], name="changed")


def gpa_panels(split: str = "4000", q: float = config.Q_FDR,
               level: str | None = None):
    """Per-subject GPA profile of two student panels within the clean cohort.

    split='4000':  A = did not reach 4000-level within horizon, B = reached.
    split='major': A = changed major within horizon, B = same major.
    level: None = all courses, 'entry' = 1000-level only, 'upper' = >=3000.
    Returns (table, grand_mean, (name_A, name_B)); table has per subject the
    panel sizes, panel mean GPAs, and BH-adjusted Welch p for the A-vs-B
    GPA gap.
    """
    g = cohort_subject_gpa(level=level)
    tag = (f"{config.COHORT_ENTRY_START}-{config.COHORT_ENTRY_END}-"
           f"{config.COHORT_HORIZON_YEARS:g}y")
    if split == "4000":
        cte = _COHORT_CTE.format(start=config.COHORT_ENTRY_START,
                                 end=config.COHORT_ENTRY_END)
        outcomes = cached_query(
            f"aCohort-outcomes-{tag}",
            cte + f"""
            select C.IDENTIFIER as id,
                   max(case when try_cast(O.CT_SUBJECT as int) > 4000
                            and O.CURRENTTERM <= C.ft +
                                {config.COHORT_HORIZON_YEARS} then 1
                            else 0 end) as has4k
            from C join OIR O on O.IDENTIFIER = C.IDENTIFIER
            group by C.IDENTIFIER""",
            ["id", "has4k"])
        in_a = outcomes.set_index("id")["has4k"].astype(int) == 0
        names = ("Did not reach above-4000 in window",
                 "Reached above-4000 in window")
    elif split == "major":
        in_a = cohort_major_change()
        names = ("Changed major within window", "Same major throughout")
    else:
        raise ValueError(split)
    g = g[g["id"].isin(in_a.index)]
    g["in_a"] = in_a.reindex(g["id"]).values
    rows = []
    for s, gg in g.groupby("subject"):
        if not s or not s.strip():
            continue
        a, b = gg.loc[gg["in_a"], "gpa"], gg.loc[~gg["in_a"], "gpa"]
        if len(a) < 2 or len(b) < 2:
            continue
        if a.mean() == 0 and b.mean() == 0:
            continue    # ungraded subject (all zero quality points)
        # Welch's t: the figures display MEAN GPAs, and grade distributions
        # pile up at 4.0, which blinds rank tests to real mean gaps
        p = ttest_ind(a, b, equal_var=False).pvalue
        rows.append((s, len(a), a.mean(), len(b), b.mean(), p))
    t = pd.DataFrame(rows, columns=["subject", "n_a", "gpa_a",
                                    "n_b", "gpa_b", "p"])
    reject, p_adj, *_ = multipletests(t["p"].fillna(1.0), alpha=q,
                                      method="fdr_bh")
    t["p_adj"] = p_adj
    t["reject"] = reject & (t["p_adj"] < q)
    return t, float(g["gpa"].mean()), names


def major_college() -> dict[str, str]:
    """Map each major (OIR DEPARTMENT) to its college via the DEPT table."""
    dept = cached_query("DEPT", "select SUBJECT, COLLEGE, DEPARTMENT from DEPT")
    m = dict(zip(dept["DEPARTMENT"], dept["COLLEGE"]))
    m.update(config.MAJOR_COLLEGE_FALLBACK)
    return m


def subject_college() -> dict[str, str]:
    dept = cached_query("DEPT", "select SUBJECT, COLLEGE, DEPARTMENT from DEPT")
    return dict(zip(dept["SUBJECT"], dept["COLLEGE"]))


def college_color(college: str | None) -> str:
    return config.COLLEGE_COLORS.get(college, config.COLLEGE_OTHER_COLOR)
