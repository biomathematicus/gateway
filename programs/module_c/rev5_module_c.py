"""Module C: corrections after the REV5 review
(Economics/Paper0/module_c/analysis_plan.md, Section 17, D2).

    python rev5_module_c.py            everything
    python rev5_module_c.py --no-rf    without the random forest

The registered pipeline (mc_data.py, mc_models.py, run_module_c.py) is
imported unchanged, and the outputs in cohorts_2014_2019/ and
registered/ are left as they are. Population: the cohorts of deviation
D1 (Fall 2014 onward). This script writes to code/figures/module_c/rev5/:

q2_pooled_joint.csv     pooled score coefficients with intervals that
                        include the covariance between subject estimates
                        (the same students and sending schools contribute
                        to several subjects)
ladder_skill.csv        out-of-sample skill with the course-by-term
ladder_blocks.csv       baseline built from training rows only, for two
ladder_blocks_summary.csv   stated prediction tasks, with a bootstrap
                        over sending schools for the block increments
sensitivity_no_aid.csv  the primary coefficients with the aid variables
                        (application flag and AGI) left out
provenance_fields.json  what the extract records about the timing of
                        the aid and score fields

Student rows live in memory only; every file is an aggregate.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_module_c as R  # noqa: E402  (registered, unchanged)

M, D = R.M, R.D
OUT = R.OUT / "rev5"
BASE = R.OUT / "cohorts_2014_2019"
FIRST_COHORT = 2014
ORDER = ["T", "F", "D", "P", "S_comp"]
BLOCK_NAME = {"T": "preparation (scores and credit route)",
              "F": "family resources", "D": "demographics",
              "P": "district poverty", "S_comp": "school block"}
log, guard, write, f4 = R.log, R.guard, R.write, R.f4


def read(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load():
    D.set_first_cohort(FIRST_COHORT)
    salt = D.new_salt()
    S = D.load_students(salt)
    ctx = D.load_context(set(zip(S["hs_name"], S["hs_city"])))
    A = D.assemble(S, ctx)
    C = D.load_courses(salt, S["sid"])
    A["sid"] = None
    R.prepare(A)
    log(f"students {S['n']:,}; first attempts {len(C['stu']):,}")
    return A, C


# ------------------------------------------------- covariance-aware pooling
def joint_pooling(A, C, subjects, out, res):
    """Each row's influence on a subject's coefficient is summed within
    sending schools; the cross-products of those sums across subjects
    give the school-clustered covariance between subject estimates, the
    same estimator that gives each subject its registered standard
    error."""
    prim = {(r["outcome"], r["subject"]): r for r in read(BASE / "q2_primary.csv")}
    school, nsch = M.group_index(A["school"])
    ns = len(subjects)
    keys = (("math", "math", "math_se"), ("verbal", "verbal", "verbal_se"),
            ("math_minus_verbal", "math_minus_verbal", "diff_se"))
    rows = []
    for outcome in ("grade", "dfw"):
        H = {k: np.zeros((nsch, ns)) for k, _, _ in keys}
        b = {k: np.zeros(ns) for k, _, _ in keys}
        se = {k: np.zeros(ns) for k, _, _ in keys}
        nrow, worst = np.zeros(ns), 0.0
        for si, s in enumerate(subjects):
            m = R.subject_primary(A, C, s, outcome, A["linked"], "school")
            f = m["b"]
            g, ng = M.group_index(m["cell"])
            Xd, yd = M.demean(f["raw"], g, ng), M.demean(m["y"], g, ng)
            e = yd - Xd @ f["beta"]
            Psi = (Xd * e[:, None]) @ np.linalg.pinv(Xd.T @ Xd)
            n, k = Xd.shape
            fac = (f["G"] / (f["G"] - 1)) * ((n - 1) / max(n - k - ng, 1))
            i1 = f["names"].index("math_score")
            i2 = f["names"].index("verbal_score")
            sc = school[m["idx"]]
            infl = {"math": Psi[:, i1], "verbal": Psi[:, i2],
                    "math_minus_verbal": Psi[:, i1] - Psi[:, i2]}
            reg = prim[(outcome, s)]
            for key, bk, sk in keys:
                H[key][:, si] = np.sqrt(fac) * np.bincount(sc, infl[key], nsch)
                b[key][si], se[key][si] = float(reg[bk]), float(reg[sk])
                worst = max(worst, abs(np.sqrt(H[key][:, si] @ H[key][:, si])
                                       - se[key][si]))
            nrow[si] = m["rows"]
        if worst > 2e-4:
            raise SystemExit(f"{outcome}: standard errors differ from the "
                             f"registered ones by {worst}")
        quant = np.array([s in R.QUANT for s in subjects])
        off = ~np.eye(ns, dtype=bool)
        for key, _, _ in keys:
            V = H[key].T @ H[key]
            d = np.sqrt(np.diag(V))
            Rm = V / np.outer(d, d)
            cov = np.outer(se[key], se[key]) * Rm
            res.setdefault("subject_correlation", {})[f"{outcome} {key}"] = {
                "mean_off_diagonal": float(Rm[off].mean()),
                "largest": float(Rm[off].max()),
                "smallest": float(Rm[off].min())}
            for cls, sel in (("other", ~quant), ("quantitative", quant)):
                cs = cov[np.ix_(sel, sel)]
                p = M.pool_dl(b[key][sel], se[key][sel])
                w = 1.0 / (se[key][sel] ** 2 + p["tau2"])
                w /= w.sum()
                sj = float(np.sqrt(w @ (cs + p["tau2"] * np.eye(sel.sum()))
                                   @ w))
                wn = nrow[sel] / nrow[sel].sum()
                mw = float(wn @ b[key][sel])
                wi = float(np.sqrt(((wn * se[key][sel]) ** 2).sum()))
                wj = float(np.sqrt(wn @ cs @ wn))
                rows.append((outcome, cls, key, int(sel.sum()),
                             f4(p["estimate"]), f4(p["lo"]), f4(p["hi"]),
                             f4(p["estimate"] - 1.96 * sj),
                             f4(p["estimate"] + 1.96 * sj), f4(mw),
                             f4(mw - 1.96 * wi), f4(mw + 1.96 * wi),
                             f4(mw - 1.96 * wj), f4(mw + 1.96 * wj)))
                if (outcome, cls, key) == ("grade", "other", "math"):
                    hits = sum(1 for s in np.array(subjects)[sel]
                               if prim[(outcome, s)]["bh_math"] == "1"
                               and float(prim[(outcome, s)]["math"]) > 0)
                    res["H2"] = {
                        "pooled": p["estimate"],
                        "lo_joint": p["estimate"] - 1.96 * sj,
                        "hi_joint": p["estimate"] + 1.96 * sj,
                        "lo_independent": p["lo"], "hi_independent": p["hi"],
                        "subjects": int(sel.sum()),
                        "subjects_passing_fdr_positive": hits,
                        "supported": bool(p["estimate"] - 1.96 * sj > 0
                                          and hits >= sel.sum() / 2)}
        log(f"joint pooling done: {outcome}")
    write(out / "q2_pooled_joint.csv",
          ["outcome", "class", "contrast", "subjects", "pooled",
           "lo_independent", "hi_independent", "lo_joint", "hi_joint",
           "weighted_by_first_attempts", "w_lo_independent",
           "w_hi_independent", "w_lo_joint", "w_hi_joint"], rows)


# ------------------------------------------------------------------ ladder
def centered(y, g, ng, cg, nc, tr):
    """course-by-term means of the training rows; a row whose cell holds
    no training row takes the training mean of its course, and failing
    that the training mean of the subject"""
    cnt = np.bincount(g[tr], minlength=ng)
    tot = np.bincount(g[tr], y[tr], ng)
    ccnt = np.bincount(cg[tr], minlength=nc)
    ctot = np.bincount(cg[tr], y[tr], nc)
    course = np.where(ccnt > 0, ctot / np.maximum(ccnt, 1), y[tr].mean())
    base = np.where(cnt[g] > 0, tot[g] / np.maximum(cnt[g], 1), course[cg])
    return base, cnt[g] == 0, ccnt[cg] == 0


def skill(y, p, base):
    return float(1 - ((y - p) ** 2).sum() / ((y - base) ** 2).sum())


def binary_metrics(y, p, base, outcome):
    if outcome != "dfw":
        return ["", "", ""]
    from sklearn.metrics import roc_auc_score
    return [f4(roc_auc_score(y, p)),
            f4(float(((y - np.clip(p, 0, 1)) ** 2).mean())),
            f4(roc_auc_score(y, base))]


def ladder_subject(A, C, s, outcome, cfg, school, nsch, skill_rows,
                   block_rows, store):
    r, cell = R.subject_rows(A, C, s, A["linked"], outcome)
    idx, y = C["stu"][r], C[outcome][r]
    g, ng = M.group_index(cell)
    cg, nc = M.group_index(C["num"][r])
    fold = R.folds_by_group(A["school"][idx])
    cohort = A["cohort"][idx]
    nested = [tuple(["cap"] + ORDER[:j]) for j in range(len(ORDER) + 1)]
    dropped = [tuple(["cap"] + [o for o in ORDER if o != b]) for b in ORDER]
    full = nested[-1]
    mats = {}

    def X(bl):
        if bl not in mats:
            mats[bl] = R.build(A, idx, list(bl))[0]
        return mats[bl]

    fams = ([("linear", bl) for bl in nested + dropped]
            + [("ridge", bl) for bl in nested]
            + ([("rf", full)] if cfg is not None else []))
    tag = f"Q2 {outcome} {s}"

    # task 1: within the offering, sending schools held out
    base = np.zeros(len(y))
    fresh = np.zeros(len(y), dtype=bool)
    pred = {k: np.zeros(len(y)) for k in fams}
    for k in np.unique(fold):
        te = fold == k
        tr = ~te
        bk, nocell, _ = centered(y, g, ng, cg, nc, tr)
        base[te], fresh[te] = bk[te], nocell[te]
        rel = y[tr] - bk[tr]
        for fam, bl in fams:
            pred[(fam, bl)][te] = bk[te] + R.fit_predict(
                fam, X(bl)[tr], rel, X(bl)[te], cfg if fam == "rf" else None)
    r2 = {k: skill(y, p, base) for k, p in pred.items()}
    for fam in ("linear", "ridge", "rf"):
        if (fam, full) in pred:
            p = pred[(fam, full)]
            skill_rows.append(
                [tag, "within offering, schools held out", fam, len(y),
                 f4(r2[(fam, full)]),
                 f4(float(np.sqrt(((y - p) ** 2).mean()))),
                 f4(float(np.sqrt(((y - base) ** 2).mean()))),
                 int(fresh.sum())] + binary_metrics(y, p, base, outcome))
    for fam in ("linear", "ridge"):
        for j, b in enumerate(ORDER):
            lost = (r2[(fam, full)] - r2[(fam, dropped[j])]
                    if fam == "linear" else np.nan)
            block_rows.append([tag, "within offering, schools held out", fam,
                               b, r2[(fam, nested[j + 1])]
                               - r2[(fam, nested[j])], lost])
    sc = school[idx]
    cols = [(y - base) ** 2] + [(y - pred[("linear", bl)]) ** 2
                                for bl in nested]
    store[(outcome, s)] = (np.column_stack(
        [np.bincount(sc, c, nsch) for c in cols]), len(y))

    # task 2: later cohorts from earlier ones
    tr = cohort <= 2015
    te = ~tr
    if tr.sum() > 200 and te.sum() > 200:
        bk, _, nocourse = centered(y, g, ng, cg, nc, tr)
        rel = y[tr] - bk[tr]
        fw = {}
        for fam, bl in ([("linear", bl) for bl in nested] + [("ridge", full)]
                        + ([("rf", full)] if cfg is not None else [])):
            fw[(fam, bl)] = bk[te] + R.fit_predict(
                fam, X(bl)[tr], rel, X(bl)[te], cfg if fam == "rf" else None)
        f2 = {k: skill(y[te], p, bk[te]) for k, p in fw.items()}
        for fam in ("linear", "ridge", "rf"):
            if (fam, full) in fw:
                p = fw[(fam, full)]
                skill_rows.append(
                    [tag, "later cohorts from earlier cohorts", fam,
                     int(te.sum()), f4(f2[(fam, full)]),
                     f4(float(np.sqrt(((y[te] - p) ** 2).mean()))),
                     f4(float(np.sqrt(((y[te] - bk[te]) ** 2).mean()))),
                     int(nocourse[te].sum())]
                    + binary_metrics(y[te], p, bk[te], outcome))
        for j, b in enumerate(ORDER):
            block_rows.append([tag, "later cohorts from earlier cohorts",
                               "linear", b, f2[("linear", nested[j + 1])]
                               - f2[("linear", nested[j])], np.nan])


def block_bootstrap(store, subjects, block_rows, out, res, draws=2000):
    """resample sending schools, the same draw in every subject, with the
    out-of-fold predictions held fixed: the variability of the block
    increments that the evaluation sample alone produces"""
    used = np.zeros(next(iter(store.values()))[0].shape[0], dtype=bool)
    for S_, _ in store.values():
        used |= S_[:, 0] > 0
    n = int(used.sum())
    rng = np.random.default_rng(R.SEED + 5)
    W = rng.multinomial(n, np.full(n, 1.0 / n), size=draws).astype(float)
    summary, ci = [], {}
    for outcome in ("grade", "dfw"):
        subs = [s for s in subjects if (outcome, s) in store]
        inc = np.zeros((draws, len(subs), len(ORDER)))
        tot = np.zeros((draws, len(subs)))
        point = np.zeros((len(subs), len(ORDER)))
        ptot, rows = np.zeros(len(subs)), np.zeros(len(subs))
        for si, s in enumerate(subs):
            S_, rows[si] = store[(outcome, s)]
            S_ = S_[used]
            bt = W @ S_
            r2b = 1 - bt[:, 1:] / bt[:, [0]]
            inc[:, si, :] = np.diff(r2b, axis=1)
            tot[:, si] = r2b[:, -1]
            r2p = 1 - S_.sum(0)[1:] / S_.sum(0)[0]
            point[si], ptot[si] = np.diff(r2p), r2p[-1]
            lo, hi = np.percentile(inc[:, si, :], [2.5, 97.5], axis=0)
            for j, b in enumerate(ORDER):
                ci[(f"Q2 {outcome} {s}", b)] = (lo[j], hi[j])
        wt = rows / rows.sum()
        for j, b in enumerate(ORDER):
            med = np.median(inc[:, :, j], axis=1)
            wtd = inc[:, :, j] @ wt
            summary.append((
                outcome, BLOCK_NAME[b], len(subs),
                f4(float(np.median(point[:, j]))),
                *(f4(v) for v in np.percentile(med, [2.5, 97.5])),
                f4(float(point[:, j] @ wt)),
                *(f4(v) for v in np.percentile(wtd, [2.5, 97.5])),
                f4(float(point[:, j].min())), f4(float(point[:, j].max())),
                int((point[:, j] > 0).sum()),
                sum(1 for si, s in enumerate(subs)
                    if ci[(f"Q2 {outcome} {s}", b)][0] > 0)))
        summary.append((
            outcome, "all blocks", len(subs), f4(float(np.median(ptot))),
            *(f4(v) for v in np.percentile(np.median(tot, axis=1),
                                           [2.5, 97.5])),
            f4(float(ptot @ wt)),
            *(f4(v) for v in np.percentile(tot @ wt, [2.5, 97.5])),
            f4(float(ptot.min())), f4(float(ptot.max())),
            int((ptot > 0).sum()), ""))
    write(out / "ladder_blocks_summary.csv",
          ["outcome", "block_added_in_order", "subjects", "median_added_r2",
           "median_lo", "median_hi", "added_r2_weighted_by_first_attempts",
           "weighted_lo", "weighted_hi", "smallest", "largest",
           "subjects_with_positive_increment",
           "subjects_whose_interval_excludes_zero_above"], summary)
    final = []
    for tag, task, fam, b, add, lost in block_rows:
        lo, hi = ci.get((tag, b), (np.nan, np.nan)) if (
            fam == "linear" and task.startswith("within")) else (np.nan,
                                                                  np.nan)
        final.append((tag, task, fam, b, f4(add), f4(lost), f4(lo), f4(hi)))
    write(out / "ladder_blocks.csv",
          ["target", "task", "family", "block", "added_r2_in_order",
           "lost_r2_when_dropped", "added_lo", "added_hi"], final)
    res["block_bootstrap"] = {"draws": draws, "schools": n,
                              "note": "sending schools resampled jointly "
                              "across subjects; predictions held fixed"}


def run_ladder(A, C, subjects, out, res, use_rf):
    school, nsch = M.group_index(A["school"])
    cfgs = {r["target"]: json.loads(r["rf_setting"])
            for r in read(BASE / "ladder_skill.csv")
            if r["family"] == "rf" and r["rf_setting"]}
    skill_rows, block_rows, store = [], [], {}
    for outcome in ("grade", "dfw"):
        for s in subjects:
            cfg = cfgs.get(f"Q2 {outcome} {s}") if use_rf else None
            ladder_subject(A, C, s, outcome, cfg, school, nsch, skill_rows,
                           block_rows, store)
            log(f"ladder: {outcome} {s}")
    write(out / "ladder_skill.csv",
          ["target", "task", "family", "rows", "r2_against_baseline", "rmse",
           "baseline_rmse", "rows_whose_baseline_fell_back", "auc", "brier",
           "auc_baseline_only"], skill_rows)
    block_bootstrap(store, subjects, block_rows, out, res)
    gap = {}
    for task in ("within offering, schools held out",
                 "later cohorts from earlier cohorts"):
        for outcome in ("grade", "dfw"):
            lin = {r[0]: float(r[4]) for r in skill_rows
                   if r[1] == task and r[2] == "linear"
                   and r[0].startswith(f"Q2 {outcome}")}
            rf = {r[0]: float(r[4]) for r in skill_rows
                  if r[1] == task and r[2] == "rf"
                  and r[0].startswith(f"Q2 {outcome}")}
            d = [rf[k] - lin[k] for k in rf]
            if d:
                gap[f"{task}, {outcome}"] = {
                    "largest_forest_minus_linear": max(d),
                    "median_forest_minus_linear": float(np.median(d)),
                    "subjects_above_0.02": sum(1 for v in d if v > 0.02),
                    "subjects": len(d)}
    res["forest_against_linear"] = gap


# ---------------------------------------- sensitivity without aid variables
def design(A, idx, blocks):
    """'F0' stands for the family block without the aid variables:
    first-generation status alone"""
    X, names = R.build(A, idx, [b for b in blocks if b != "F0"])
    if "F0" in blocks:
        c, nm = R.cat_cols(A, "fg", idx, "Not First Generation")
        X, names = np.column_stack([X] + c), names + nm
    return X, names


def fit_design(X, names, y, cluster, cell=None):
    absorbed = 0
    if cell is not None:
        g, ng = M.group_index(cell)
        Xd, yd, absorbed = M.demean(X, g, ng), M.demean(y, g, ng), ng
        keep = M.keep_columns(Xd)
        Xk, nm = Xd[:, keep], [names[k] for k in keep]
    else:
        keep = M.keep_columns(X)
        Xk = np.column_stack([np.ones(len(y)), X[:, keep]])
        nm, yd = ["const"] + [names[k] for k in keep], y
    f = M.ols_cluster(Xk, yd, cluster, None, absorbed)
    f["names"] = nm
    f["se"] = np.sqrt(np.clip(np.diag(f["V"]), 0, None))
    return f


def no_aid(A, C, subjects, out, res):
    rows = []
    full = {}
    ok = A["linked"] & np.isfinite(A["zm"]) & np.isfinite(A["zv"])
    idx = np.flatnonzero(ok)
    sd = float(np.nanstd(A["hm"]))
    for oname, y in (("mathematics score", A["zm"][idx]),
                     ("mathematics minus verbal", (A["zm"] - A["zv"])[idx])):
        for term in ("advmath_index", "district_poverty"):
            vals = []
            for fb in ("F", "F0"):
                X, names = design(A, idx, ["cohort", "cap", fb, "D", "P",
                                           "S_index"])
                f = fit_design(X, names, y, A["school"][idx])
                b, se = R.coef(f, term)
                vals += [f4(b), f4(b - 1.96 * se), f4(b + 1.96 * se)]
                # the same coefficients at full precision, for quantities
                # the text converts to score points
                full.setdefault(oname, {}).setdefault(term, {})[
                    "with_aid_variables" if fb == "F"
                    else "without_aid_variables"] = {
                        "coef": float(b), "se": float(se)}
            rows.append((f"preparation: {oname}", term,
                         "per SD of the predictor, in SD of the score "
                         f"(one SD is {sd:.0f} points)", *vals))
    res["no_aid"] = {"score_sd_points": sd, "preparation": full}
    for fb_i, fb in enumerate(("F", "F0")):
        est = {k: [] for k in ("math", "verbal", "diff")}
        ses = {k: [] for k in ("math", "verbal", "diff")}
        cls = []
        for s in subjects:
            r, cell = R.subject_rows(A, C, s, A["linked"], "grade")
            i2 = C["stu"][r]
            X, names = design(A, i2, ["T", fb, "D", "cap"])
            f = fit_design(X, names, C["grade"][r], A["school"][i2], cell)
            for k, (b, se) in (("math", R.coef(f, "math_score")),
                               ("verbal", R.coef(f, "verbal_score")),
                               ("diff", R.contrast(f, "math_score",
                                                   "verbal_score"))):
                est[k].append(b)
                ses[k].append(se)
            cls.append(s in R.QUANT)
        cls = np.array(cls)
        pm = [M.pvalue(b, se) for b, se in zip(est["math"], ses["math"])]
        passed = M.bh(pm) & (np.array(est["math"]) > 0)
        for cname, sel in (("non-quantitative subjects", ~cls),
                           ("quantitative subjects", cls)):
            for k, lab in (("math", "mathematics score"),
                           ("verbal", "verbal score"),
                           ("diff", "mathematics minus verbal")):
                p = M.pool_dl(np.array(est[k])[sel], np.array(ses[k])[sel])
                key = (f"first-year grades, {cname}", lab)
                cell_ = [f4(p["estimate"]), f4(p["lo"]), f4(p["hi"])]
                if fb_i == 0:
                    rows.append([key[0], key[1], "pooled grade points per "
                                 "SD (independent-subject interval)"] + cell_)
                else:
                    next(r_ for r_ in rows if r_[0] == key[0]
                         and r_[1] == key[1]).extend(cell_)
        key = ("first-year grades", "subjects where the mathematics score "
               "passes false-discovery control with a positive sign")
        if fb_i == 0:
            rows.append([key[0], key[1], f"of {len(subjects)}",
                         int(passed.sum()), "", ""])
        else:
            next(r_ for r_ in rows if r_[1] == key[1]).extend(
                [int(passed.sum()), "", ""])
    write(out / "sensitivity_no_aid.csv",
          ["model", "quantity", "unit", "with_aid_variables", "lo", "hi",
           "without_aid_variables", "lo_without", "hi_without"], rows)
    log("sensitivity without the aid variables done")


# ------------------------------------------------------------- provenance
def provenance(out):
    """what the extract itself records about when the aid and score
    fields were measured: column names and counts only"""
    import pyodbc
    from student_success import config as _ss
    fields = ("AGINum", "FA_APPLIED", "PELLSTATUS", "HIGHEST_SATACT_MATH",
              "HIGHEST_SATACT_ERW")
    with pyodbc.connect(_ss.CONN_STRING, timeout=20) as cn:
        cur = cn.cursor()
        cols = [r[0] for r in cur.execute(
            "select COLUMN_NAME from INFORMATION_SCHEMA.COLUMNS "
            "where TABLE_NAME = 'OIR' order by ORDINAL_POSITION").fetchall()]
        students = cur.execute(
            "select count(distinct IDENTIFIER) from OIR").fetchone()[0]
        vary = {}
        for fld in fields:
            v = cur.execute(
                "select count(*) from (select IDENTIFIER from OIR group by "
                f"IDENTIFIER having count(distinct {fld}) > 1) x"
            ).fetchone()[0]
            vary[fld] = int(v) if v == 0 or v >= R.MIN_CELL else "fewer than 10"
    dated = [c for c in cols if any(t in c.upper() for t in
                                    ("DATE", "YEAR", "AIDY"))]
    info = {
        "table": "dbo.OIR", "columns": len(cols),
        "columns_naming_a_date_or_year": dated,
        "score_columns": [c for c in cols if "SAT" in c.upper()
                          or "ACT_" in c.upper()],
        "aid_columns": [c for c in cols if c.upper() in
                        ("FA_APPLIED", "AGI", "AGINUM", "PELLSTATUS")],
        "students": int(students),
        "students_whose_value_differs_across_their_rows": vary,
        "reading": "The extract holds one value of each aid and score "
                   "field per student and no field that dates either: no "
                   "aid year and no test date."}
    (out / "provenance_fields.json").write_text(json.dumps(info, indent=1),
                                                encoding="utf-8")
    log("provenance of the aid and score fields recorded")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-rf", action="store_true")
    ap.add_argument("--only", default="", help="comma list of steps: "
                    "pooling, ladder, noaid, provenance")
    a = ap.parse_args()
    steps = set(a.only.split(",")) if a.only else {"pooling", "ladder",
                                                   "noaid", "provenance"}
    OUT.mkdir(parents=True, exist_ok=True)
    subjects = [r["subject"] for r in read(BASE / "stage0_subjects.csv")]
    A, C = load()
    path = OUT / "results.json"
    res = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    res.update({"mode": "post-registration corrections (plan Section 17, "
                "D2)", "first_cohort": FIRST_COHORT, "seed": R.SEED})
    if "provenance" in steps:
        provenance(OUT)
    if "pooling" in steps:
        joint_pooling(A, C, subjects, OUT, res)
    if "noaid" in steps:
        no_aid(A, C, subjects, OUT, res)
    if "ladder" in steps:
        run_ladder(A, C, subjects, OUT, res, not a.no_rf)
    res["seconds"] = round(R.time.time() - R.T0)
    path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    log(f"finished: {OUT}")


if __name__ == "__main__":
    main()
