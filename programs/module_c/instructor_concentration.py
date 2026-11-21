"""Are low grades in a subject concentrated in a few instructors?

Exploratory, run at the PI's request on 2026-11-19 after the relative
grading matrix showed political science below movers' norms. Not part
of any registered plan.

Two populations, two questions.

A. Movers of the reference cohort (the population of the relative
   grading matrix): for each subject, how the movers' deviation from
   their own norm is spread over the instructors who taught them.
B. First attempts of the Fall 2014 to Fall 2018 entrants (the
   population of the section-size models): for each subject, how much
   instructors differ within the same course and term once student
   preparation and background are held fixed.

Student and instructor identifiers are replaced inside the query by
salted surrogates. Every output is an aggregate over a subject or over
a group of at least five instructors; nothing is indexed by instructor
or by section. Arrays and plain lists; no dataframes.

    python instructor_concentration.py
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pyodbc

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mc_data as D  # noqa: E402
import mc_models as M  # noqa: E402
import run_module_c as R  # noqa: E402
import cs_data as CS  # noqa: E402
import run_class_size as RC  # noqa: E402
from student_success import config as _ss  # noqa: E402

OUT = R.OUT / "instructor_concentration"
ENTRY_START, ENTRY_END, HORIZON = 2014.66, 2015.66, 4.0   # reference cohort
MIN_MOVERS, MIN_GROUP, MIN_INSTRUCTORS = 600, 5, 10
QUARTER = 0.25
log, guard, write, f4 = R.log, R.guard, R.write, R.f4

SQL_MOVER_ROWS = f"""
with C as (
  select IDENTIFIER, min(try_cast(FIRSTTERMCODE as float)) ft
  from OIR where STUDENTTYPE = 'New' group by IDENTIFIER
  having min(try_cast(FIRSTTERMCODE as float))
         between {ENTRY_START} and {ENTRY_END}),
M as (
  select C.IDENTIFIER, C.ft,
    (select top 1 O2.DEPARTMENT from OIR O2
     where O2.IDENTIFIER = C.IDENTIFIER
       and O2.CURRENTTERM <= C.ft + {HORIZON}
     order by O2.CURRENTTERM asc) fm,
    (select top 1 O3.DEPARTMENT from OIR O3
     where O3.IDENTIFIER = C.IDENTIFIER
       and O3.CURRENTTERM <= C.ft + {HORIZON}
     order by O3.CURRENTTERM desc) lm
  from C)
select convert(varchar(64), hashbytes('SHA2_256', ? + O.IDENTIFIER), 2),
       O.SHRTCKN_SUBJ_CODE, try_cast(O.CT_SUBJECT as int),
       convert(varchar(64), hashbytes('SHA2_256',
               ? + ltrim(rtrim(O.PRIMARY_INSTRUCTOR_ID))), 2),
       O.SHRGRDE_QUALITY_POINTS
from M join OIR O on O.IDENTIFIER = M.IDENTIFIER
where M.fm is not null and (M.lm is null or M.fm <> M.lm)
  and O.CURRENTTERM <= M.ft + {HORIZON}
  and O.SHRGRDE_GPA_IND = 'Y' and O.SHRGRDE_QUALITY_POINTS is not null
"""


# --------------------------------------------------------------- statistics
def one_way(e, g):
    """one-way random effects by method of moments: (tau2, sigma2, icc)"""
    codes, J = M.group_index(g)
    n = np.bincount(codes, minlength=J).astype(float)
    N = n.sum()
    if J < 2 or N <= J:
        return np.nan, np.nan, np.nan
    mean = np.bincount(codes, e, J) / n
    sw = float(((e - mean[codes]) ** 2).sum() / (N - J))
    msb = float((n * (mean - e.mean()) ** 2).sum() / (J - 1))
    n0 = (N - (n ** 2).sum() / N) / (J - 1)
    tau2 = max(0.0, (msb - sw) / n0)
    return tau2, sw, tau2 / (tau2 + sw) if tau2 + sw > 0 else np.nan


def wquantile(v, w, qs):
    o = np.argsort(v)
    c = (np.cumsum(w[o]) - w[o] / 2) / w.sum()
    return [float(np.interp(q, c, v[o])) for q in qs]


def groups(mean, n):
    """lowest- and highest-grading instructor groups: each holds at
    least a quarter of the rows and at least MIN_GROUP instructors"""
    order = np.argsort(mean)
    total = n.sum()

    def take(idx):
        acc, k = 0.0, 0
        for k, j in enumerate(idx, 1):
            acc += n[j]
            if acc >= QUARTER * total and k >= MIN_GROUP:
                break
        return idx[:k]

    return take(order), take(order[::-1])


def profile(dev, inst, course, label):
    """how a subject's deviation is spread over its instructors"""
    codes, J = M.group_index(inst)
    n = np.bincount(codes, minlength=J).astype(float)
    mean = np.bincount(codes, dev, J) / n
    share = n / n.sum()
    out = {"subject": label, "rows": int(n.sum()), "instructors": J,
           "effective_instructors": float(1.0 / (share ** 2).sum()),
           "share_rows_top5_by_volume":
               float(np.sort(share)[::-1][:MIN_GROUP].sum())
               if J >= MIN_GROUP else np.nan,
           "mean": float(dev.mean())}
    _, _, out["icc_instructor"] = one_way(dev, inst)
    cc, K = M.group_index(course)
    within = dev - (np.bincount(cc, dev, K) / np.bincount(cc, minlength=K))[cc]
    t2, _, out["icc_instructor_within_course"] = one_way(within, inst)
    out["sd_instructor_within_course"] = float(np.sqrt(t2)) \
        if np.isfinite(t2) else np.nan
    for k in ("q10", "q25", "q50", "q75", "q90", "low_group_instructors",
              "low_group_row_share", "low_group_mean", "high_group_instructors",
              "high_group_row_share", "high_group_mean",
              "mean_without_low_group", "mean_without_high_group",
              "low_group_share_of_total_deviation"):
        out[k] = np.nan
    if J >= MIN_INSTRUCTORS:
        (out["q10"], out["q25"], out["q50"], out["q75"],
         out["q90"]) = wquantile(mean, n, [0.10, 0.25, 0.50, 0.75, 0.90])
        lo, hi = groups(mean, n)
        tot = float((n * mean).sum())
        for tag, idx in (("low", lo), ("high", hi)):
            m = np.zeros(J, dtype=bool)
            m[idx] = True
            out[f"{tag}_group_instructors"] = int(m.sum())
            out[f"{tag}_group_row_share"] = float(n[m].sum() / n.sum())
            out[f"{tag}_group_mean"] = float((n[m] * mean[m]).sum()
                                             / n[m].sum())
            out[f"mean_without_{tag}_group"] = float(
                (n[~m] * mean[~m]).sum() / n[~m].sum())
            if tag == "low" and tot != 0:
                out["low_group_share_of_total_deviation"] = float(
                    (n[m] * mean[m]).sum() / tot)
    return out


COLS = ["subject", "students", "rows", "instructors", "effective_instructors",
        "share_rows_top5_by_volume", "mean", "icc_instructor",
        "icc_instructor_within_course", "sd_instructor_within_course", "q10",
        "q25", "q50", "q75", "q90", "low_group_instructors",
        "low_group_row_share", "low_group_mean", "high_group_instructors",
        "high_group_row_share", "high_group_mean", "mean_without_low_group",
        "mean_without_high_group", "low_group_share_of_total_deviation"]


def dump(path, rows):
    write(path, COLS, [[f4(r[k]) if isinstance(r[k], float) else r[k]
                        for k in COLS] for r in rows])


# ------------------------------------------------------------- population A
def movers(salt, out):
    with pyodbc.connect(_ss.CONN_STRING, timeout=20) as cn:
        rows = cn.cursor().execute(SQL_MOVER_ROWS, salt, salt).fetchall()
    sid, iid = {}, {}
    stu = np.array([sid.setdefault(r[0], len(sid)) for r in rows])
    subj = np.array([(r[1] or "").strip() for r in rows], dtype=object)
    num = np.array([r[2] if r[2] is not None else -1 for r in rows])
    inst = np.array([iid.setdefault(r[3], len(iid)) if r[3] else -1
                     for r in rows])
    qp = np.array([float(r[4]) for r in rows])
    del rows
    log(f"movers: {len(sid):,} students, {len(qp):,} graded rows")
    # student-by-subject grade average, then the leave-one-out norm
    sc, _ = M.group_index(subj)
    key = stu.astype(np.int64) * 10000 + sc
    kc, K = M.group_index(key)
    gpa = np.bincount(kc, qp, K) / np.bincount(kc, minlength=K)
    first = np.zeros(K, dtype=int)
    first[kc] = stu
    tot = np.bincount(first, gpa, len(sid))
    cnt = np.bincount(first, minlength=len(sid))
    ok = cnt[stu] > 1
    other = (tot[stu] - gpa[kc]) / np.maximum(cnt[stu] - 1, 1)
    dev = qp - other                      # row deviation from own norm
    res = []
    for s in sorted(set(subj[ok])):
        m = ok & (subj == s) & (inst >= 0)
        n_stu = len(np.unique(stu[m]))
        if n_stu < MIN_MOVERS:
            continue
        guard(n_stu, f"movers {s}")
        p = profile(dev[m], inst[m], num[m], s)
        p["students"] = n_stu
        res.append(p)
    res.sort(key=lambda r: -r["students"])
    dump(out / "ic_movers.csv", res)
    log(f"movers: {len(res)} subjects profiled")
    return res


# ------------------------------------------------------------- population B
def first_attempts(salt, out):
    D.set_first_cohort(RC.FIRST_COHORT)
    S = D.load_students(salt)
    ctx = D.load_context(set(zip(S["hs_name"], S["hs_city"])))
    A = D.assemble(S, ctx)
    sec = CS.load_sections(salt)
    C = CS.load_rows(salt, S["sid"], sec, with_outcomes=True)
    A["sid"] = None
    R.prepare(A)
    base = RC.exposure_mask(C, {CS.LECTURE})
    with open(RC.SUBJECTS_FILE, encoding="utf-8") as fh:
        subjects = [r["subject"] for r in csv.DictReader(fh)]
    res = {"grade": [], "dfw": []}
    for outcome in res:
        for s in subjects:
            r, cell = RC.rows_of(C, s, base, outcome)
            n_stu = len(np.unique(C["stu"][r]))
            if n_stu < RC.MIN_STUDENTS:
                continue
            guard(n_stu, f"first attempts {s}")
            X, _ = R.build(A, C["stu"][r], RC.BLOCKS)
            ls = np.log2(C["size"][r])
            Z, _ = RC.absorb(np.column_stack([X, ls, C[outcome][r]]), [cell])
            Xd, yd = Z[:, :-1], Z[:, -1]
            Xk = Xd[:, M.keep_columns(Xd)]
            e = yd - Xk @ np.linalg.lstsq(Xk, yd, rcond=None)[0]
            p = profile(e, C["inst"][r], C["num"][r], s)
            p["students"] = n_stu
            res[outcome].append(p)
        dump(out / f"ic_first_attempts_{outcome}.csv", res[outcome])
        log(f"first attempts: {outcome} done")
    return res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    salt = D.new_salt()
    a = movers(salt, OUT)
    b = first_attempts(salt, OUT)

    def pick(rows, s):
        return next((r for r in rows if r["subject"] == s), None)

    summary = {"status": "exploratory, not registered",
               "movers": {s: pick(a, s) for s in ("POL", "MAT", "CHE", "HIS",
                                                  "AIS", "BIO", "ECO")},
               "first_attempts_grade": {
                   s: pick(b["grade"], s)
                   for s in ("POL", "MAT", "CHE", "HIS", "AIS", "BIO", "ECO")}}
    (OUT / "ic_summary.json").write_text(json.dumps(summary, indent=1),
                                         encoding="utf-8")
    log(f"finished: {OUT}")


if __name__ == "__main__":
    main()
