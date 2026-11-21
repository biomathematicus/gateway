"""Module C runner (Economics/Paper0/module_c/analysis_plan.md).

    python run_module_c.py --permute     dry run on shuffled outcomes
    python run_module_c.py               registered estimation

Student rows live in memory only. Every file written here is an
aggregate: counts, coefficients, variance components, fold metrics.
Released counts below the minimum cell stop the run.
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mc_data as D  # noqa: E402
import mc_models as M  # noqa: E402

OUT = HERE.parent / "figures" / "module_c"
MIN_CELL, MIN_SUBJECT, MIN_ROUTE, SEED = 10, 1000, 30, 20261118
QUANT = {"MAT", "CHE", "ECO", "STA", "PHY", "CS", "ACC", "ME"}
QUANT_BROAD = QUANT | {"BIO", "GEO", "AST", "ES", "IS"}
SCALED = ("agi_rank", "logagi", "pov", "ldpop", "index", "calc", "apm",
          "aps", "dualr", "lsch")
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:7.0f}s] {msg}", flush=True)


def guard(n, what):
    if 0 < n < MIN_CELL:
        raise SystemExit(f"disclosure guard: {what} holds {n} students")
    return n


# --------------------------------------------------------------------- design
def prepare(A):
    A["ldpop"], A["lsch"] = np.log(A["dpop"]), np.log(A["sch_enr"])
    A["logagi"] = np.where(A["agi"] > 0, np.log(np.maximum(A["agi"], 1.0)),
                           np.nan)
    A["scale"] = {}
    for k in SCALED:
        v = A[k][A["linked"] & np.isfinite(A[k])]
        A["scale"][k] = (float(v.mean()), float(v.std()))
    for key in ("fg", "gender", "eth"):
        levels = sorted(set(A[key]))
        pos = {v: i for i, v in enumerate(levels)}
        A[key + "_c"] = np.array([pos[v] for v in A[key]])
        A[key + "_levels"] = levels
    A["cohort_levels"] = sorted(set(A["cohort"].tolist()))
    pos = {v: i for i, v in enumerate(A["cohort_levels"])}
    A["cohort_c"] = np.array([pos[v] for v in A["cohort"]])
    A["hs_key"] = np.array([f"{a}|{b}" for a, b in
                            zip(A["hs_name"], A["hs_city"])], dtype=object)


def z(A, k, idx):
    mu, sd = A["scale"][k]
    v = (A[k][idx] - mu) / sd
    v[~np.isfinite(v)] = 0.0
    return v


def cat_cols(A, key, idx, ref=None):
    codes, levels = A[key + "_c"][idx], A[key + "_levels"]
    cnt = np.bincount(A[key + "_c"][np.unique(idx)], minlength=len(levels))
    r = levels.index(ref) if ref in levels else int(cnt.argmax())
    cols, names = [], []
    small, small_n = np.zeros(len(idx), dtype=bool), 0
    for L in range(len(levels)):
        if L == r or cnt[L] == 0:
            continue
        if cnt[L] < MIN_CELL:
            small |= codes == L
            small_n += cnt[L]
            continue
        cols.append((codes == L).astype(float))
        names.append(f"{key}:{levels[L]}")
    if small_n >= MIN_CELL:
        cols.append(small.astype(float))
        names.append(f"{key}:other")
    return cols, names


def build(A, idx, blocks):
    cols, names = [], []

    def add(name, v):
        cols.append(np.asarray(v, dtype=float))
        names.append(name)

    def cats(key, ref=None):
        c, nm = cat_cols(A, key, idx, ref)
        cols.extend(c)
        names.extend(nm)

    for b in blocks:
        if b == "cohort":
            cats("cohort")
        elif b == "cap":
            add("cap", A["cap"][idx])
        elif b in ("F", "F_logagi", "F_pell", "F_split"):
            if b == "F_split":
                # school mean and within-school deviation, in units of
                # one standard deviation of the AGI rank
                sc, J = M.group_index(A["hs_key"][idx])
                sd = A["scale"]["agi_rank"][1]
                for name, v in (("agi", A["agi_rank"][idx]),
                                ("nofafsa", A["no_fafsa"][idx])):
                    ok = np.isfinite(v)
                    mean = (np.bincount(sc[ok], v[ok], J)
                            / np.maximum(np.bincount(sc[ok], minlength=J), 1))
                    dev = np.where(ok, v - mean[sc], 0.0)
                    scale = sd if name == "agi" else 1.0
                    add(name + "_within", dev / scale)
                    add(name + "_between",
                        (mean[sc] - np.nanmean(v[ok])) / scale)
            else:
                add("no_fafsa", A["no_fafsa"][idx])
                if b == "F":
                    add("agi_rank", z(A, "agi_rank", idx))
                elif b == "F_logagi":
                    add("log_agi", z(A, "logagi", idx))
                else:
                    add("pell", A["pell"][idx])
            if b != "F_pell":
                add("agi_nonpositive", A["agi_nonpos"][idx])
            cats("fg", "Not First Generation")
        elif b == "D":
            cats("gender")
            cats("eth")
        elif b == "P":
            add("district_poverty", z(A, "pov", idx))
            add("district_children_log", z(A, "ldpop", idx))
        elif b == "S_index":
            add("advmath_index", z(A, "index", idx))
            add("ap_science_rate", z(A, "aps", idx))
            add("dual_rate", z(A, "dualr", idx))
            add("school_enrollment_log", z(A, "lsch", idx))
        elif b == "S_comp":
            for k, nm in (("calc", "calculus_rate"), ("apm", "ap_math_rate"),
                          ("aps", "ap_science_rate"), ("dualr", "dual_rate"),
                          ("lsch", "school_enrollment_log")):
                add(nm, z(A, k, idx))
            add("no_calculus", np.nan_to_num(A["none_calc"][idx]))
            add("no_ap_math", np.nan_to_num(A["none_apm"][idx]))
        elif b in ("T", "T_scores"):
            add("math_score", np.nan_to_num(A["zm"][idx]))
            add("verbal_score", np.nan_to_num(A["zv"][idx]))
            add("score_missing", A["score_missing"][idx])
            if b == "T":
                route = A["route"][idx]
                cnt = np.bincount(A["route"][np.unique(idx)], minlength=3)
                if min(cnt[1], cnt[2]) >= MIN_ROUTE:
                    add("credit_dual_only", route == 1)
                    add("credit_exam", route == 2)
                elif cnt[1] + cnt[2] >= MIN_ROUTE:
                    add("credit_any", route > 0)
        else:
            raise ValueError(b)
    return np.column_stack(cols), names


def fit(A, idx, y, blocks, cluster, cell=None, w=None, want_raw=False):
    X, names = build(A, idx, blocks)
    absorbed, raw = 0, X
    if cell is not None:
        g, ng = M.group_index(cell)
        Xd, yd, absorbed = M.demean(X, g, ng), M.demean(y, g, ng), ng
        keep = M.keep_columns(Xd)
        Xk, names = Xd[:, keep], [names[k] for k in keep]
    else:
        keep = M.keep_columns(X)
        Xk = np.column_stack([np.ones(len(y)), X[:, keep]])
        names, yd = ["const"] + [names[k] for k in keep], y
    res = M.ols_cluster(Xk, yd, cluster, w, absorbed)
    res["names"] = names
    res["se"] = np.sqrt(np.clip(np.diag(res["V"]), 0, None))
    if want_raw:
        res["raw"] = raw[:, keep]
    return res


def coef(res, name):
    if name not in res["names"]:
        return np.nan, np.nan
    k = res["names"].index(name)
    return float(res["beta"][k]), float(res["se"][k])


def contrast(res, a, b):
    if a not in res["names"] or b not in res["names"]:
        return np.nan, np.nan
    i, j = res["names"].index(a), res["names"].index(b)
    V = res["V"]
    return (float(res["beta"][i] - res["beta"][j]),
            float(np.sqrt(max(V[i, i] + V[j, j] - 2 * V[i, j], 0.0))))


def write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def f4(v):
    return "" if v is None or not np.isfinite(v) else f"{v:.4f}"


# ----------------------------------------------------------------- stage 0
def sample_flow(A, C, out):
    q2 = A["cohort"] <= D.LAST_Q2_COHORT
    has_row = np.zeros(A["n"], dtype=bool)
    has_row[C["stu"]] = True
    scored = np.isfinite(A["zm"]) & np.isfinite(A["zv"])
    steps = [
        (f"first-time fall entrants, Fall {D.FIRST_COHORT} to Fall "
         f"{D.LAST_COHORT}", np.ones(A["n"], bool)),
        ("with mathematics and verbal scores", scored),
        ("aid applicants (AGI recorded)", A["applied"]),
        ("sending school resolved in the crosswalk", A["has_key"]),
        ("linked sample (school and district context complete)", A["linked"]),
        ("linked sample with both scores (Q1)", A["linked"] & scored),
        (f"Fall {D.FIRST_COHORT} to Fall {D.LAST_Q2_COHORT} (Q2 cohorts)",
         q2),
        ("Q2 cohorts, linked", q2 & A["linked"]),
        ("Q2 cohorts, linked, with a first-year course row",
         q2 & A["linked"] & has_row),
        ("CAP flag set", A["cap"] > 0),
        ("CAP flag set, linked", (A["cap"] > 0) & A["linked"]),
    ]
    rows = [(s, guard(int(m.sum()), s)) for s, m in steps]
    write(out / "stage0_sample_flow.csv", ["step", "students"], rows)
    by = []
    for co in A["cohort_levels"]:
        c = A["cohort"] == co
        by.append((co, int(c.sum()), int((c & A["linked"]).sum()),
                   D.cycle_of(co)[0], D.cycle_of(co)[1]))
    write(out / "stage0_cohort_flow.csv",
          ["cohort", "fall_entrants", "linked", "crdc_cycle", "lag_years"], by)
    # subjects by linked students with a qualifying first attempt
    ok = A["linked"][C["stu"]] & np.isfinite(C["dfw"])
    subj = {}
    for s in np.unique(C["subj"][ok]):
        m = ok & (C["subj"] == s)
        subj[s] = len(np.unique(C["stu"][m]))
    keep = sorted((s for s, n in subj.items() if n >= MIN_SUBJECT),
                  key=lambda s: -subj[s])
    write(out / "stage0_subjects.csv", ["subject", "linked_students", "class"],
          [(s, subj[s], "quantitative" if s in QUANT else "other")
           for s in keep])
    log(f"sample flow: {rows[0][1]:,} entrants, {rows[4][1]:,} linked; "
        f"{len(keep)} subjects clear {MIN_SUBJECT:,}")
    return keep


# --------------------------------------------------------------------- Q1
Q1_STEPS = [("design", ["cohort", "cap"]),
            ("+F", ["cohort", "cap", "F"]),
            ("+D", ["cohort", "cap", "F", "D"]),
            ("+P", ["cohort", "cap", "F", "D", "P"]),
            ("+S", ["cohort", "cap", "F", "D", "P", "S_index"])]
FULL_Q1 = Q1_STEPS[-1][1]


def run_q1(A, C, out, res):
    ok = A["linked"] & np.isfinite(A["zm"]) & np.isfinite(A["zv"])
    idx = np.flatnonzero(ok)
    school = A["school"][idx]
    district = np.array([s[:7] for s in school], dtype=object)
    sd_m = float(np.nanstd(A["hm"]))
    outcomes = {"math": A["zm"][idx], "gap": (A["zm"] - A["zv"])[idx]}
    vp = []
    for name, y in outcomes.items():
        base = None
        for label, blocks in Q1_STEPS:
            X, _ = build(A, idx, blocks)
            Xk = np.column_stack([np.ones(len(y)), X[:, M.keep_columns(X)]])
            v = M.nested_reml(Xk, y, school, district)
            r2 = M.ols_cluster(Xk, y, school)["r2"]
            base = base or v
            vp.append((name, label, v["n"], v["schools"], v["districts"],
                       f4(v["sigma_d"]), f4(v["sigma_s"]), f4(v["sigma_e"]),
                       f4(1 - v["sigma_d"] / base["sigma_d"]),
                       f4(1 - v["sigma_s"] / base["sigma_s"]),
                       f4(1 - v["sigma_e"] / base["sigma_e"]), f4(r2)))
        log(f"Q1 variance partition done: {name}")
    write(out / "q1_variance_partition.csv",
          ["outcome", "step", "students", "schools", "districts",
           "var_district", "var_school", "var_student",
           "explained_district", "explained_school", "explained_student",
           "ols_r2"], vp)

    coefs = []
    full = {}
    for name, y in outcomes.items():
        full[name] = fit(A, idx, y, FULL_Q1, school)
        for nm, b, se in zip(full[name]["names"], full[name]["beta"],
                             full[name]["se"]):
            if not nm.startswith("cohort"):
                coefs.append((name, "full", nm, f4(b), f4(se),
                              f4(M.pvalue(b, se)) if se > 0 else ""))
        g = fit(A, idx, y, ["cohort", "cap", "F_split", "D"], school)
        for nm in ("agi_within", "agi_between", "nofafsa_within",
                   "nofafsa_between"):
            b, se = coef(g, nm)
            coefs.append((name, "income gradient", nm, f4(b), f4(se),
                          f4(M.pvalue(b, se))))
        b, se = contrast(g, "agi_between", "agi_within")
        coefs.append((name, "income gradient", "agi_between_minus_within",
                      f4(b), f4(se), f4(M.pvalue(b, se))))
    b, se = coef(full["gap"], "advmath_index")
    res["H1"] = {"estimate": b, "se": se, "lo": b - 1.96 * se,
                 "hi": b + 1.96 * se, "p": M.pvalue(b, se),
                 "students": int(len(idx)), "schools": full["gap"]["G"],
                 "math_score_sd_points": sd_m,
                 "estimate_score_points": b * sd_m}
    bm, sem = coef(full["math"], "advmath_index")
    res["index_on_math_score"] = {"estimate": bm, "se": sem,
                                  "estimate_score_points": bm * sd_m}

    # secondary outcomes
    lvl = D.entry_math_level(C, A["n"])
    sec = {"entry_math_level": (ok & (lvl >= 0)
                                & (A["cohort"] <= D.LAST_Q2_COHORT), lvl),
           "ap_math_credit": (ok, (A["ap"] > 0).astype(float)),
           "dual_math_credit": (ok, (A["dual"] > 0).astype(float))}
    for name, (mask, yv) in sec.items():
        i2 = np.flatnonzero(mask)
        r = fit(A, i2, yv[i2], FULL_Q1, A["school"][i2])
        for nm, bb, ss in zip(r["names"], r["beta"], r["se"]):
            if not nm.startswith("cohort"):
                coefs.append((name, "secondary", nm, f4(bb), f4(ss),
                              f4(M.pvalue(bb, ss)) if ss > 0 else ""))
        res.setdefault("secondary_n", {})[name] = guard(len(i2), name)
    write(out / "q1_coefficients.csv",
          ["outcome", "model", "term", "estimate", "se", "p"], coefs)
    log(f"Q1 done: H1 index coefficient {b:+.4f} (SE {se:.4f})")
    return idx


def h1_variant(A, mask, fblock="F", w=None):
    ok = mask & A["linked"] & np.isfinite(A["zm"]) & np.isfinite(A["zv"])
    idx = np.flatnonzero(ok)
    if len(np.unique(A["school"][idx])) < 30:
        return np.nan, np.nan, len(idx)
    blocks = ["cohort", "cap", fblock, "D", "P", "S_index"]
    r = fit(A, idx, (A["zm"] - A["zv"])[idx], blocks, A["school"][idx],
            w=None if w is None else w[idx])
    b, se = coef(r, "advmath_index")
    return b, se, len(idx)


# --------------------------------------------------------------------- Q2
def subject_rows(A, C, subj, sample, outcome):
    r = np.flatnonzero((C["subj"] == subj) & sample[C["stu"]]
                       & np.isfinite(C[outcome]))
    cell = C["num"][r].astype(np.int64) * 100000 + C["tix"][r]
    g, ng = M.group_index(cell)
    keep = np.bincount(g, minlength=ng)[g] >= 2
    return r[keep], cell[keep]


STEP_B = ["T", "F", "D", "cap"]
STEP_C = STEP_B + ["P", "S_index"]
STUDENT_TERMS = ["math_score", "verbal_score", "agi_rank", "no_fafsa",
                 "fg:First Generation", "cap", "credit_dual_only",
                 "credit_exam", "credit_any"]
CONTEXT_TERMS = ["district_poverty", "advmath_index", "ap_science_rate",
                 "dual_rate", "school_enrollment_log"]


def subject_primary(A, C, subj, outcome, sample, cluster_key, fblock="F",
                    w=None, steps="b"):
    r, cell = subject_rows(A, C, subj, sample, outcome)
    idx = C["stu"][r]
    if len(np.unique(idx)) < 200:
        return None
    y = C[outcome][r]
    cl = A[cluster_key][idx]
    blocks = ["T", fblock, "D", "cap"]
    out = {"rows": len(r), "students": len(np.unique(idx)),
           "schools": len(np.unique(cl)), "cells": len(np.unique(cell)),
           "idx": idx, "cell": cell, "y": y, "cl": cl}
    out["b"] = fit(A, idx, y, blocks, cl, cell,
                   None if w is None else w[idx], want_raw=True)
    if "a" in steps:
        out["a"] = fit(A, idx, y, ["T_scores"], cl, cell)
    if "c" in steps:
        out["c"] = fit(A, idx, y, blocks + ["P", "S_index"], cl, cell)
    return out


def run_q2(A, C, subjects, out, res):
    rows, prim, logit = [], [], []
    for outcome in ("grade", "dfw"):
        for s in subjects:
            m = subject_primary(A, C, s, outcome, A["linked"], "school",
                                steps="abc")
            if m is None:
                continue
            guard(m["students"], f"{s} {outcome}")
            cls = "quantitative" if s in QUANT else "other"
            bm, sm = coef(m["b"], "math_score")
            bv, sv = coef(m["b"], "verbal_score")
            bd, sdiff = contrast(m["b"], "math_score", "verbal_score")
            am, asm = coef(m["a"], "math_score")
            al = subject_primary(A, C, s, outcome, np.ones(A["n"], bool),
                                 "hs_key")
            alm, als = coef(al["b"], "math_score") if al else (np.nan, np.nan)
            prim.append([outcome, s, cls, m["students"], m["rows"],
                         m["schools"], m["cells"], bm, sm, bv, sv, bd, sdiff,
                         am, asm, alm, als, al["students"] if al else 0])
            for nm in STUDENT_TERMS:
                b, se = coef(m["b"], nm)
                if np.isfinite(b):
                    rows.append((outcome, s, cls, "b", nm, f4(b), f4(se),
                                 f4(M.pvalue(b, se))))
            for nm in CONTEXT_TERMS:
                b, se = coef(m["c"], nm)
                if np.isfinite(b):
                    rows.append((outcome, s, cls, "c", nm, f4(b), f4(se),
                                 f4(M.pvalue(b, se))))
            if outcome == "dfw":
                try:
                    lg = M.logit_fe(m["b"]["raw"], m["y"], m["cell"], m["cl"])
                    nm = m["b"]["names"]
                    k1, k2 = nm.index("math_score"), nm.index("verbal_score")
                    se = np.sqrt(np.diag(lg["V"]))
                    logit.append((s, lg["n"], f4(lg["beta"][k1]), f4(se[k1]),
                                  f4(lg["beta"][k2]), f4(se[k2]),
                                  int(np.sign(lg["beta"][k1]) == np.sign(bm))))
                except Exception as e:  # noqa: BLE001
                    logit.append((s, 0, "", "", "", "", f"failed: {e}"))
        log(f"Q2 subject models done: {outcome}")
    # false-discovery control within each family and outcome
    P = np.array([[M.pvalue(r[7], r[8]), M.pvalue(r[9], r[10]),
                   M.pvalue(r[11], r[12])] for r in prim])
    for outcome in ("grade", "dfw"):
        sel = np.array([r[0] == outcome for r in prim])
        for j in range(3):
            flags = np.zeros(len(prim), dtype=bool)
            flags[sel] = M.bh(P[sel, j])
            for r, fl in zip(prim, flags):
                if r[0] == outcome:
                    r.append(int(fl))
    write(out / "q2_primary.csv",
          ["outcome", "subject", "class", "students", "rows", "schools",
           "course_term_cells", "math", "math_se", "verbal", "verbal_se",
           "math_minus_verbal", "diff_se", "math_scores_only",
           "math_scores_only_se", "math_all_entrants",
           "math_all_entrants_se", "all_entrant_students", "bh_math",
           "bh_verbal", "bh_diff"],
          [r[:7] + [f4(v) for v in r[7:17]] + r[17:] for r in prim])
    write(out / "q2_coefficients.csv",
          ["outcome", "subject", "class", "step", "term", "estimate", "se",
           "p"], rows)
    write(out / "q2_logit_check.csv",
          ["subject", "rows_used", "math_logit", "math_se", "verbal_logit",
           "verbal_se", "same_sign_as_linear"], logit)

    pooled = []
    for outcome in ("grade", "dfw"):
        for label, quant in (("registered classes", QUANT),
                             ("broad quantitative class", QUANT_BROAD)):
            for cls in ("other", "quantitative"):
                sel = [r for r in prim if r[0] == outcome
                       and ((r[1] in quant) == (cls == "quantitative"))]
                for nm, bi, si, fi in (("math", 7, 8, 18), ("verbal", 9, 10, 19),
                                       ("math_minus_verbal", 11, 12, 20)):
                    p = M.pool_dl([r[bi] for r in sel], [r[si] for r in sel])
                    sign = -1 if (outcome == "dfw" and nm == "math") else 1
                    hits = sum(1 for r in sel if r[fi] and sign * r[bi] > 0)
                    pooled.append((outcome, label, cls, nm, len(sel),
                                   f4(p.get("estimate", np.nan)),
                                   f4(p.get("lo", np.nan)),
                                   f4(p.get("hi", np.nan)), hits))
                    if (outcome, label, cls, nm) == ("grade",
                                                     "registered classes",
                                                     "other", "math"):
                        res["H2"] = {
                            "pooled": p.get("estimate"), "lo": p.get("lo"),
                            "hi": p.get("hi"), "subjects": len(sel),
                            "subjects_passing_fdr_positive": hits,
                            "supported": bool(p.get("lo", -1) > 0
                                              and hits >= len(sel) / 2)}
    write(out / "q2_pooled.csv",
          ["outcome", "classification", "class", "contrast", "subjects",
           "pooled", "lo", "hi", "subjects_passing_fdr_expected_sign"],
          pooled)
    log(f"Q2 done: H2 {res.get('H2')}")


def q2_pooled_variant(A, C, subjects, mask, fblock="F", w=None):
    est, se, dif, dse = [], [], [], []
    for s in subjects:
        if s in QUANT:
            continue
        m = subject_primary(A, C, s, "grade", mask & A["linked"], "school",
                            fblock, w)
        if m is None:
            continue
        b, e = coef(m["b"], "math_score")
        d, de = contrast(m["b"], "math_score", "verbal_score")
        est.append(b), se.append(e), dif.append(d), dse.append(de)
    return M.pool_dl(est, se), M.pool_dl(dif, dse)


# ------------------------------------------------------------- sensitivity
def linkage_weights(A):
    from sklearn.linear_model import LogisticRegression
    idx = np.arange(A["n"])
    X, _ = build(A, idx, ["cohort", "cap", "F", "D", "T"])
    X = X[:, M.keep_columns(X)]
    X = (X - X.mean(0)) / X.std(0)
    p = LogisticRegression(max_iter=1000).fit(
        X, A["linked"].astype(int)).predict_proba(X)[:, 1]
    return 1.0 / np.clip(p, 0.05, 1.0)


def run_sensitivity(A, C, subjects, out, res):
    w = linkage_weights(A)
    all_ = np.ones(A["n"], dtype=bool)
    variants = [
        ("primary", all_, "F", None),
        ("snapshot lag two years or less", A["lag"] <= 2, "F", None),
        ("home within 10 miles of school", A["miles"] <= 10, "F", None),
        ("entrants through Fall 2015", A["cohort"] <= 2015, "F", None),
        ("entrants from Fall 2016", A["cohort"] >= 2016, "F", None),
        ("CAP flag not set", A["cap"] == 0, "F", None),
        ("CAP flag set", A["cap"] > 0, "F", None),
        ("log AGI among positive values", all_, "F_logagi", None),
        ("Pell status in place of AGI", all_, "F_pell", None),
        ("both scores recorded", A["score_missing"] == 0, "F", None),
        ("inverse-probability-of-linkage weights", all_, "F", w),
    ]
    rows = []
    for name, mask, fb, wt in variants:
        b, se, n = h1_variant(A, mask, fb, wt)
        pm, pd_ = q2_pooled_variant(A, C, subjects, mask, fb, wt)
        guard(n, name)
        rows.append((name, n, f4(b), f4(b - 1.96 * se), f4(b + 1.96 * se),
                     pm.get("k", 0), f4(pm.get("estimate", np.nan)),
                     f4(pm.get("lo", np.nan)), f4(pm.get("hi", np.nan)),
                     f4(pd_.get("estimate", np.nan)),
                     f4(pd_.get("lo", np.nan)), f4(pd_.get("hi", np.nan))))
        log(f"sensitivity: {name}")
    write(out / "sensitivity.csv",
          ["variant", "q1_students", "h1_index_on_gap", "h1_lo", "h1_hi",
           "q2_subjects", "pooled_math_other_subjects", "math_lo", "math_hi",
           "pooled_math_minus_verbal", "diff_lo", "diff_hi"], rows)
    lag_ok = [r for r in rows if r[0] in ("snapshot lag two years or less",
                                          "home within 10 miles of school")]
    h1 = res["H1"]
    h1["supported"] = bool(h1["lo"] > 0 and all(
        r[2] != "" and float(r[2]) > 0 for r in lag_ok))
    # common coefficients, linked against all entrants (gap outcome)
    comp = []
    scored = np.isfinite(A["zm"]) & np.isfinite(A["zv"])
    for label, mask in (("linked", A["linked"] & scored),
                        ("all entrants", scored)):
        idx = np.flatnonzero(mask)
        for oname, y in (("math", A["zm"][idx]),
                         ("gap", (A["zm"] - A["zv"])[idx])):
            r = fit(A, idx, y, ["cohort", "cap", "F", "D"], A["hs_key"][idx])
            for nm in ("agi_rank", "no_fafsa", "fg:First Generation", "cap"):
                b, se = coef(r, nm)
                comp.append((oname, label, len(idx), nm, f4(b), f4(se)))
    write(out / "sensitivity_linked_vs_all.csv",
          ["outcome", "sample", "students", "term", "estimate", "se"], comp)


# ------------------------------------------------------------------ ladder
def folds_by_group(groups, k=10):
    u = np.unique(groups)
    rng = np.random.default_rng(SEED)
    rng.shuffle(u)
    pos = {g: i % k for i, g in enumerate(u)}
    return np.array([pos[g] for g in groups])


def fit_predict(family, Xtr, ytr, Xte, cfg=None, trees=500):
    if family == "linear":
        Z = np.column_stack([np.ones(len(Xtr)), Xtr])
        beta = np.linalg.lstsq(Z, ytr, rcond=None)[0]
        return np.column_stack([np.ones(len(Xte)), Xte]) @ beta
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1.0
    if family == "ridge":
        from sklearn.linear_model import RidgeCV
        mdl = RidgeCV(alphas=np.logspace(-2, 4, 13)).fit((Xtr - mu) / sd, ytr)
        return mdl.predict((Xte - mu) / sd)
    from sklearn.ensemble import RandomForestRegressor
    mdl = RandomForestRegressor(n_estimators=trees, max_features=1 / 3,
                                n_jobs=-1, random_state=SEED, **cfg)
    return mdl.fit(Xtr, ytr).predict(Xte)


def oof(family, X, y, fold, cfg=None, trees=500):
    pred = np.zeros(len(y))
    for k in np.unique(fold):
        te = fold == k
        pred[te] = fit_predict(family, X[~te], y[~te], X[te], cfg, trees)
    return pred


def r2(y, p):
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


RF_GRID = [{"max_depth": d, "min_samples_leaf": m}
           for d in (6, 10, None) for m in (20, 50)]


def select_rf(X, y, groups):
    fold = folds_by_group(groups, 3)
    best = None
    for cfg in RF_GRID:
        e = float(np.sqrt(((y - oof("rf", X, y, fold, cfg, 200)) ** 2).mean()))
        if best is None or e < best[0]:
            best = (e, cfg)
    return best[1]


def ladder_target(A, idx, y, groups, cohort, order, tag, rows, blocks_rows,
                  sub_rows, use_rf, binary=None, offset=None):
    full = ["cap"] + order
    mats = {}

    def X(blocks):
        key = tuple(blocks)
        if key not in mats:
            mats[key] = build(A, idx, list(blocks))[0]
        return mats[key]

    fold = folds_by_group(groups)
    train = cohort <= 2015
    preds = {}
    for family in ("linear", "ridge") + (("rf",) if use_rf else ()):
        cfg = None
        if family == "rf":
            cfg = select_rf(X(full)[train], y[train], groups[train])
        p = oof(family, X(full), y, fold, cfg)
        preds[family] = p
        fw = np.full(len(y), np.nan)
        if train.sum() > 200 and (~train).sum() > 200:
            fw[~train] = fit_predict(family, X(full)[train], y[train],
                                     X(full)[~train], cfg)
        row = [tag, family, len(y), f4(r2(y, p)),
               f4(float(np.sqrt(((y - p) ** 2).mean()))),
               f4(r2(y[~train], fw[~train])) if np.isfinite(fw[~train]).all()
               and (~train).sum() > 200 else "", json.dumps(cfg) if cfg else ""]
        if binary is not None:
            from sklearn.metrics import roc_auc_score
            score = np.clip(offset + p, 0, 1)
            row += [f4(roc_auc_score(binary, offset + p)),
                    f4(float(((binary - score) ** 2).mean())),
                    f4(roc_auc_score(binary, offset))]
        else:
            row += ["", "", ""]
        rows.append(row)
        if family in ("linear", "ridge"):
            prev = r2(y, oof(family, X(["cap"]), y, fold))
            base_r2 = r2(y, p)
            for j, b in enumerate(order):
                cur = r2(y, oof(family, X(["cap"] + order[: j + 1]), y, fold))
                drop = [o for o in order if o != b]
                lost = base_r2 - r2(y, oof(family, X(["cap"] + drop), y, fold))
                blocks_rows.append((tag, family, b, f4(cur - prev), f4(lost)))
                prev = cur
    # subgroup error of the full models, out of fold
    stu = idx
    groups_def = {
        "aid: did not apply": ~A["applied"][stu],
        "aid: applicant, lower AGI half": A["applied"][stu]
        & (A["agi_rank"][stu] < 0.5),
        "aid: applicant, upper AGI half": A["applied"][stu]
        & (A["agi_rank"][stu] >= 0.5),
        "first generation": np.array(A["fg_c"][stu] == A["fg_levels"].index(
            "First Generation")) if "First Generation" in A["fg_levels"]
        else np.zeros(len(stu), bool),
        "CAP flag set": A["cap"][stu] > 0,
        "CAP flag not set": A["cap"][stu] == 0,
    }
    q = np.nanpercentile(A["sch_enr"][stu], [33.3, 66.7])
    groups_def["school size: lower third"] = A["sch_enr"][stu] <= q[0]
    groups_def["school size: upper third"] = A["sch_enr"][stu] > q[1]
    for family, p in preds.items():
        for g, m in groups_def.items():
            n_stu = len(np.unique(stu[m]))
            if n_stu >= MIN_CELL:
                sub_rows.append((tag, family, g, n_stu, f4(float(
                    np.sqrt(((y[m] - p[m]) ** 2).mean()))),
                    f4(float((y[m] - p[m]).mean()))))


def run_ladder(A, C, subjects, q1_idx, out, use_rf, rf_subjects):
    rows, blocks_rows, sub_rows = [], [], []
    for name, y in (("Q1 math score", A["zm"][q1_idx]),
                    ("Q1 math-verbal gap", (A["zm"] - A["zv"])[q1_idx])):
        ladder_target(A, q1_idx, y, A["school"][q1_idx], A["cohort"][q1_idx],
                      ["F", "D", "P", "S_comp"], name, rows, blocks_rows,
                      sub_rows, use_rf)
        log(f"ladder done: {name}")
    for outcome in ("grade", "dfw"):
        for s in subjects:
            r, cell = subject_rows(A, C, s, A["linked"], outcome)
            idx = C["stu"][r]
            y = C[outcome][r]
            g, ng = M.group_index(cell)
            cnt = np.bincount(g, minlength=ng)[g]
            tot = np.bincount(g, y, ng)[g]
            rel = y - tot / cnt                       # relative outcome
            loo = (tot - y) / (cnt - 1)               # classmates' mean
            ladder_target(A, idx, rel, A["school"][idx], A["cohort"][idx],
                          ["T", "F", "D", "P", "S_comp"],
                          f"Q2 {outcome} {s}", rows, blocks_rows, sub_rows,
                          use_rf and (rf_subjects is None or s in rf_subjects),
                          binary=y if outcome == "dfw" else None, offset=loo)
        log(f"ladder done: Q2 {outcome}")
    write(out / "ladder_skill.csv",
          ["target", "family", "rows", "oof_r2", "oof_rmse", "forward_r2",
           "rf_setting", "auc", "brier", "auc_classmates_rate_only"], rows)
    write(out / "ladder_blocks.csv",
          ["target", "family", "block", "added_r2_in_order",
           "lost_r2_when_dropped"], blocks_rows)
    write(out / "ladder_subgroups.csv",
          ["target", "family", "group", "students", "rmse", "mean_error"],
          sub_rows)


# ----------------------------------------------------------------- driver
def permute(A, C):
    """shuffle outcomes: scores within cohort, grades within course-term"""
    rng = np.random.default_rng(SEED + 1)
    for co in np.unique(A["cohort"]):
        i = np.flatnonzero(A["cohort"] == co)
        p = rng.permutation(i)
        for k in ("zm", "zv", "hm", "he", "ap", "dual", "clep", "route",
                  "score_missing"):
            A[k][i] = A[k][p]
    key = np.array([f"{s}|{n}|{t}" for s, n, t in
                    zip(C["subj"], C["num"], C["tix"])], dtype=object)
    g, ng = M.group_index(key)
    order = np.argsort(g, kind="stable")
    starts = np.flatnonzero(np.diff(g[order], prepend=-1))
    for a, b in zip(starts, list(starts[1:]) + [len(order)]):
        i = order[a:b]
        p = rng.permutation(i)
        C["grade"][i], C["dfw"][i] = C["grade"][p], C["dfw"][p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--permute", action="store_true")
    ap.add_argument("--no-rf", action="store_true")
    ap.add_argument("--rf-subjects", default=None,
                    help="comma list; default all subjects")
    ap.add_argument("--stage0-only", action="store_true")
    ap.add_argument("--first-cohort", type=int, default=None,
                    help="deviation of 2026-11-19: restrict to entrants of "
                         "this fall and later (registered default: 2009)")
    ap.add_argument("--tag", default=None, help="output folder name")
    a = ap.parse_args()
    if a.first_cohort:
        D.set_first_cohort(a.first_cohort)
    out = OUT / (a.tag or ("dryrun" if a.permute else "registered"))
    out.mkdir(parents=True, exist_ok=True)
    salt = D.new_salt()
    S = D.load_students(salt)
    log(f"students loaded: {S['n']:,}")
    ctx = D.load_context(set(zip(S["hs_name"], S["hs_city"])))
    A = D.assemble(S, ctx)
    C = D.load_courses(salt, S["sid"])
    A["sid"] = None                       # surrogate no longer needed
    log(f"first attempts loaded: {len(C['stu']):,} student-course rows")
    prepare(A)
    subjects = sample_flow(A, C, out)
    if a.stage0_only:
        return
    if a.permute:
        permute(A, C)
        prepare(A)
        log("outcomes permuted (dry run)")
    res = {"mode": "dry run on permuted outcomes" if a.permute
           else ("registered estimation" if not a.first_cohort else
                 "deviation: cohort-restricted estimation"),
           "seed": SEED, "first_cohort": D.FIRST_COHORT,
           "last_cohort": D.LAST_COHORT}
    q1_idx = run_q1(A, C, out, res)
    run_q2(A, C, subjects, out, res)
    run_sensitivity(A, C, subjects, out, res)
    rf_subj = set(a.rf_subjects.split(",")) if a.rf_subjects else None
    run_ladder(A, C, subjects, q1_idx, out, not a.no_rf, rf_subj)
    res["seconds"] = round(time.time() - T0)
    (out / "results.json").write_text(json.dumps(res, indent=1),
                                      encoding="utf-8")
    log(f"finished: {out}")


if __name__ == "__main__":
    main()
