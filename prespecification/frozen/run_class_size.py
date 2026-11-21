"""Class-size addendum runner
(Economics/Paper0/module_c/class_size_addendum.md).

    python run_class_size.py --stage0-only   outcome-blind checks
    python run_class_size.py --permute       dry run on shuffled outcomes
    python run_class_size.py                 registered estimation

Student rows live in memory only. Every file written here is an
aggregate: counts, coefficients, and scenario totals. No output is
indexed by section or by instructor. Released counts below the minimum
cell stop the run.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mc_data as D  # noqa: E402
import mc_models as M  # noqa: E402
import run_module_c as R  # noqa: E402
import cs_data as CS  # noqa: E402

OUT = R.OUT / "class_size"
SUBJECTS_FILE = R.OUT / "cohorts_2014_2019" / "stage0_subjects.csv"
FIRST_COHORT, SEED = 2014, 20261119
CAP = 45                              # scenario cap (addendum, Section 7)
BANDS = [(11, 30), (31, 45), (46, 75), (76, 120), (121, 10 ** 6)]
REF_BAND = 1
BLOCKS = ["T", "F", "D", "cap"]       # the Module C student blocks
BALANCE = ("zm", "zv", "agi_rank", "first_gen", "cap", "pell")
MIN_STUDENTS, MIN_SD = 200, 0.20      # subject entry rule (Section 2)
NBOOT = 999                           # wild bootstrap draws (Section 8)
CALIBRATE = ("MAT", "POL", "CHE", "ECO", "GRG")   # dry-run calibration
log, guard, write, f4 = R.log, R.guard, R.write, R.f4


def tcrit(G):
    """two-sided 95% critical value on G - 1 degrees of freedom"""
    return float(stats.t.ppf(0.975, max(int(G) - 1, 1)))


def pt(b, se, G):
    """two-sided p-value of b / se on G - 1 degrees of freedom"""
    if not (np.isfinite(b) and np.isfinite(se) and se > 0):
        return np.nan
    return float(2 * stats.t.sf(abs(b / se), max(int(G) - 1, 1)))


# ------------------------------------------------------------- estimation
def absorb(Z, fes, tol=1e-9, maxit=2000):
    """remove several sets of fixed effects by alternating demeaning"""
    X = np.array(Z, dtype=float, copy=True)
    codes = [M.group_index(g) for g in fes]
    if not codes:
        return X, 0
    for _ in range(maxit if len(codes) > 1 else 1):
        prev = X.copy()
        for g, ng in codes:
            X = M.demean(X, g, ng)
        if len(codes) == 1 or np.abs(X - prev).max() < tol:
            break
    return X, sum(ng for _, ng in codes) - (len(codes) - 1)


def fit_fe(cols, names, y, fes, cluster):
    X = np.column_stack([np.asarray(c, dtype=float) for c in cols])
    if fes:
        Z, absorbed = absorb(np.column_stack([X, y]), fes)
        Xd, yd = Z[:, :-1], Z[:, -1]
        keep = M.keep_columns(Xd)
        Xk, nm = Xd[:, keep], [names[k] for k in keep]
    else:
        keep = M.keep_columns(X)
        Xk = np.column_stack([np.ones(len(y)), X[:, keep]])
        nm, yd, absorbed = ["const"] + [names[k] for k in keep], y, 0
    res = M.ols_cluster(Xk, yd, cluster, None, absorbed)
    res["names"] = nm
    res["se"] = np.sqrt(np.clip(np.diag(res["V"]), 0, None))
    return res


def cell_key(C, r):
    s, _ = M.group_index(C["subj"])
    return (s[r].astype(np.int64) * 10 ** 10
            + C["num"][r].astype(np.int64) * 100000 + C["tix"][r])


def exposure_mask(C, formats):
    """first-year first attempts that sit in one eligible section"""
    fmt = np.array([s in formats for s in C["sched"]])
    return ((C["off"] <= 2) & (C["nsec"] == 1)
            & (C["size"] > CS.MIN_SECTION) & fmt)


def rows_of(C, subj, base, outcome=None):
    m = (C["subj"] == subj) & base
    if outcome is not None:
        m &= np.isfinite(C[outcome])
    r = np.flatnonzero(m)
    cell = cell_key(C, r)
    g, ng = M.group_index(cell)
    keep = np.bincount(g, minlength=ng)[g] >= 2
    return r[keep], cell[keep]


def band_cols(size):
    cols, names = [], []
    for j, (a, b) in enumerate(BANDS):
        if j == REF_BAND:
            continue
        cols.append(((size >= a) & (size <= b)).astype(float))
        names.append(f"size_{a}_{'plus' if b > 10 ** 5 else b}")
    return cols, names


def ladder(A, C, r, cell, y, models="01234"):
    """the comparison ladder for one subject and one outcome"""
    idx, inst = C["stu"][r], C["inst"][r]
    ls = np.log2(C["size"][r]) - np.log2(CAP)
    X, names = R.build(A, idx, BLOCKS)
    covs = [X[:, j] for j in range(X.shape[1])]
    zm = np.nan_to_num(A["zm"][idx])
    out = {}
    if "0" in models:
        out["M0"] = fit_fe([ls], ["log2_size"], y, [], inst)
    if "1" in models:
        out["M1"] = fit_fe([ls], ["log2_size"], y, [cell], inst)
    if "2" in models:
        out["M2"] = fit_fe([ls] + covs, ["log2_size"] + names, y, [cell], inst)
    if "3" in models:
        out["M3"] = fit_fe([ls] + covs, ["log2_size"] + names, y,
                           [cell, inst], inst)
    if "4" in models:
        out["M4"] = fit_fe([ls, ls * zm] + covs,
                           ["log2_size", "log2_size_x_math"] + names, y,
                           [cell, inst], inst)
    if "b" in models:
        bc, bn = band_cols(C["size"][r])
        out["bands"] = fit_fe(bc + covs, bn + names, y, [cell, inst], inst)
    return out


class TwoWay:
    """exact residual maker for course-by-term and instructor effects"""

    def __init__(self, cell, inst):
        self.g1, self.n1 = M.group_index(cell)
        self.g2, self.n2 = M.group_index(inst)
        k = self.n1 + self.n2
        A = np.zeros((k, k))
        A[np.arange(self.n1), np.arange(self.n1)] = np.bincount(
            self.g1, minlength=self.n1)
        j = self.n1 + np.arange(self.n2)
        A[j, j] = np.bincount(self.g2, minlength=self.n2)
        cross = np.zeros((self.n1, self.n2))
        np.add.at(cross, (self.g1, self.g2), 1.0)
        A[:self.n1, self.n1:], A[self.n1:, :self.n1] = cross, cross.T
        self.P = np.linalg.pinv(A)
        self.o1 = np.argsort(self.g1, kind="stable")
        self.s1 = np.flatnonzero(np.diff(self.g1[self.o1], prepend=-1))
        self.o2 = np.argsort(self.g2, kind="stable")
        self.s2 = np.flatnonzero(np.diff(self.g2[self.o2], prepend=-1))

    def resid(self, V):
        V = np.asarray(V, dtype=float)
        t = np.concatenate([np.add.reduceat(V[self.o1], self.s1, axis=0),
                            np.add.reduceat(V[self.o2], self.s2, axis=0)])
        c = self.P @ t
        return V - c[:self.n1][self.g1] - c[self.n1:][self.g2]


def weights(rng, G, B):
    """wild bootstrap weights: Rademacher, or Webb's six points when
    there are fewer than 12 clusters"""
    if G >= 12:
        return rng.choice([-1.0, 1.0], size=(G, B))
    pts = np.sqrt([1.5, 1.0, 0.5])
    return rng.choice(np.concatenate([-pts, pts]), size=(G, B))


class SizeTest:
    """one term of a model, with every other regressor and the fixed
    effects partialled out"""

    def __init__(self, tw, Zr, col, g, G):
        N = np.delete(Zr, col, axis=1)
        keep = M.keep_columns(N) if N.shape[1] else []
        self.Q = (np.linalg.qr(N[:, keep])[0] if len(keep)
                  else np.zeros((len(Zr), 0)))
        x = Zr[:, col]
        self.x = x - self.Q @ (self.Q.T @ x)
        self.sxx = float(self.x @ self.x)
        self.tw, self.g, self.G = tw, g, G
        self.order = np.argsort(g, kind="stable")
        self.starts = np.flatnonzero(np.diff(g[self.order], prepend=-1))

    def partial(self, V):
        V = self.tw.resid(V)
        return V - self.Q @ (self.Q.T @ V)

    def stat(self, U):
        """coefficient and cluster-robust t (no small-sample factor) from
        residuals of the model that leaves the term out"""
        b = self.x @ U / self.sxx
        x = self.x if U.ndim == 1 else self.x[:, None]
        S = np.add.reduceat((x * (U - x * b))[self.order], self.starts,
                            axis=0)
        return b, b * self.sxx / np.sqrt((S ** 2).sum(0))

    def wild(self, u, rng, draws):
        """wild cluster bootstrap-t with the null imposed: the estimate,
        its p-value, and the half-width of the 95% interval (the 95th
        percentile of |t*| times the cluster-robust standard error)"""
        b0, t0 = self.stat(u)
        ts = []
        for start in range(0, draws, 200):
            W = weights(rng, self.G, min(200, draws - start))
            ts.append(np.abs(self.stat(self.partial(W[self.g]
                                                    * u[:, None]))[1]))
        ts = np.concatenate(ts)
        p = (1.0 + (ts >= abs(t0) - 1e-12).sum()) / (draws + 1.0)
        hw = float(np.quantile(ts, 0.95) * abs(b0 / t0)) if t0 else np.nan
        return float(b0), float(p), hw


def term_tests(E, names, X, fe1, fe2, cluster):
    """SizeTest objects for the columns of E, given nuisance columns X
    (or None) and up to two sets of fixed effects (None for absent)"""
    const = np.zeros(len(E), dtype=int)
    tw = TwoWay(const if fe1 is None else fe1, const if fe2 is None else fe2)
    g, G = M.group_index(cluster)
    Zr = tw.resid(E if X is None else np.column_stack([X, E]))
    k0 = 0 if X is None else X.shape[1]
    return {nm: SizeTest(tw, Zr, k0 + j, g, G) for j, nm in enumerate(names)}


def model_tests(A, C, r, cell, kind):
    """the size terms of M0 to M4 or of the banded form"""
    idx, inst = C["stu"][r], C["inst"][r]
    ls = np.log2(C["size"][r]) - np.log2(CAP)
    if kind == "M4":
        E = np.column_stack([ls, ls * np.nan_to_num(A["zm"][idx])])
        names = ["log2_size", "log2_size_x_math"]
    elif kind == "bands":
        bc, names = band_cols(C["size"][r])
        E = np.column_stack(bc)
    else:
        E, names = ls[:, None], ["log2_size"]
    X = None if kind in ("M0", "M1") else R.build(A, idx, BLOCKS)[0]
    return term_tests(E, names, X, None if kind == "M0" else cell,
                      inst if kind in ("M3", "M4", "bands") else None, inst)


def wild(tests, y, seed):
    """{term: (estimate, wild bootstrap p-value, interval half-width)}"""
    rng = np.random.default_rng(seed)
    out = {}
    for nm, st in tests.items():
        if st.sxx < 1e-10:
            out[nm] = (np.nan, np.nan, np.nan)
            continue
        out[nm] = st.wild(st.partial(y), rng, NBOOT)
    return out


def calibrate(A, C, base, out, shuffles=200, draws=199):
    """rejection rates of the two tests of the M3 size coefficient when
    grades are shuffled within course-by-term cells (dry run only)"""
    rows = []
    for si, s in enumerate(CALIBRATE):
        r, cell = rows_of(C, s, base, "grade")
        y = C["grade"][r]
        st = model_tests(A, C, r, cell, "M3")["log2_size"]
        f = ladder(A, C, r, cell, y, models="3")["M3"]
        b0, t0 = st.stat(st.partial(y))
        fac = (R.coef(f, "log2_size")[1] / abs(b0 / t0)) ** 2
        by_cell = np.argsort(cell, kind="stable")
        rng = np.random.default_rng(SEED + 77 + si)
        pc, pw = [], []
        for _ in range(shuffles):
            ys = np.empty(len(y))
            ys[by_cell] = y[np.lexsort((rng.random(len(y)), cell))]
            u = st.partial(ys)
            _, t = st.stat(u)
            pc.append(2 * stats.t.sf(abs(t) / np.sqrt(fac), st.G - 1))
            pw.append(st.wild(u, rng, draws)[1])
        pc, pw = np.array(pc), np.array(pw)
        rows.append((s, st.G, len(r), shuffles, f4(float((pc < 0.05).mean())),
                     f4(float((pw < 0.05).mean())),
                     f4(float((pc < 0.10).mean())),
                     f4(float((pw < 0.10).mean()))))
        log(f"calibration: {s}")
    write(out / "cs_calibration.csv",
          ["subject", "instructor_clusters", "rows", "shuffles",
           "cluster_t_reject_05", "wild_reject_05", "cluster_t_reject_10",
           "wild_reject_10"], rows)


def describe(C, r, cell):
    return {"rows": len(r), "students": len(np.unique(C["stu"][r])),
            "sections": len(np.unique(C["secid"][r])),
            "instructors": len(np.unique(C["inst"][r])),
            "cells": len(np.unique(cell))}


# ---------------------------------------------------------------- stage 0
def stage0(A, C, sec, subjects, base, out):
    """outcome-blind flow, exposure, and balance; returns the subjects
    that enter the models under the entry rule"""
    in25 = np.isin(C["subj"], subjects)
    fy = in25 & (C["off"] <= 2)
    one = fy & (C["nsec"] == 1)
    big = one & (C["size"] > CS.MIN_SECTION)
    steps = [("first attempts in the first-year window, 25 subjects", fy),
             ("held in one section of the course", one),
             ("section holds more than 10 students", big),
             ("face-to-face lecture section (primary set)", in25 & base)]
    multi = np.zeros(len(C["stu"]), dtype=bool)
    r_all = np.flatnonzero(in25 & base)
    g, _ = M.group_index(cell_key(C, r_all))
    order = np.argsort(g, kind="stable")
    starts = np.flatnonzero(np.diff(g[order], prepend=-1))
    for a, b in zip(starts, list(starts[1:]) + [len(order)]):
        i = order[a:b]
        if len(np.unique(C["secid"][r_all[i]])) >= 2:
            multi[r_all[i]] = True
    steps.append(("course-by-term cell holds two or more sections", multi))
    write(out / "cs_stage0_flow.csv", ["step", "rows", "students"],
          [(s, int(m.sum()), guard(len(np.unique(C["stu"][m])), s))
           for s, m in steps])

    sched = {}
    for s in sec.values():
        if s["subj"] in subjects:
            e = sched.setdefault(s["sched"] or "(none)", [0, 0, 0])
            e[0] += 1
            e[1] += int(s["size"] > CS.MIN_SECTION)
            e[2] += s["size"]
    write(out / "cs_stage0_schedule.csv",
          ["schedule_type", "sections", "sections_over_10", "seats"],
          sorted(((k, *v) for k, v in sched.items()), key=lambda t: -t[3]))

    A["first_gen"] = np.array([v == "First Generation" for v in A["fg"]],
                              dtype=float)
    expo, bal, modeled = [], [], []
    for s in list(subjects) + ["ALL"]:
        if s == "ALL":
            r = np.flatnonzero(in25 & base)
            c = cell_key(C, r)
        else:
            r, c = rows_of(C, s, base)
        d = describe(C, r, c)
        guard(d["students"], f"stage 0 {s}")
        size = C["size"][r]
        ls = np.log2(size)
        g, ng = M.group_index(c)
        within = M.demean(ls, g, ng)
        two, _ = absorb(ls[:, None], [c, C["inst"][r]])
        sd_two = float(two.std())
        enters = (s != "ALL" and d["students"] >= MIN_STUDENTS
                  and sd_two >= MIN_SD)
        if enters:
            modeled.append(s)
        secs = {}
        for k, sid in zip(c, C["secid"][r]):
            secs.setdefault(k, set()).add(sid)
        expo.append((s, d["rows"], d["students"], d["sections"],
                     d["instructors"], d["cells"],
                     sum(1 for v in secs.values() if len(v) >= 2),
                     f"{np.percentile(size, 10):.0f}",
                     f"{np.percentile(size, 50):.0f}",
                     f"{np.percentile(size, 90):.0f}",
                     f4(float(ls.std())), f4(float(within.std())),
                     f4(sd_two), f4(float((size > CAP).mean())),
                     "" if s == "ALL" else int(enters)))
        for k in BALANCE:
            v = A[k][C["stu"][r]]
            ok = np.isfinite(v)
            if ok.sum() < 200:
                continue
            f = fit_fe([ls[ok]], ["log2_size"], v[ok], [c[ok]],
                       C["inst"][r][ok])
            b, se = R.coef(f, "log2_size")
            bal.append((s, k, int(ok.sum()), f4(b), f4(se),
                        f4(pt(b, se, f["G"]))))
    write(out / "cs_stage0_exposure.csv",
          ["subject", "rows", "students", "sections", "instructors",
           "course_term_cells", "cells_with_2plus_sections", "size_p10",
           "size_p50", "size_p90", "sd_log2_size", "sd_within_cell",
           "sd_within_cell_and_instructor", "share_rows_above_cap",
           "enters_models"], expo)
    write(out / "cs_stage0_balance.csv",
          ["subject", "covariate", "rows", "per_doubling_of_size", "se", "p"],
          bal)
    log(f"stage 0 written: {int((in25 & base).sum()):,} eligible rows; "
        f"{len(modeled)} of {len(subjects)} subjects enter the models")
    return modeled


# ------------------------------------------------------------- the models
def run_models(A, C, modeled, base, out, res):
    coefs, prim, keepres, gap = [], [], {}, 0.0
    for oi, outcome in enumerate(("grade", "dfw")):
        for si, s in enumerate(modeled):
            r, cell = rows_of(C, s, base, outcome)
            d = describe(C, r, cell)
            guard(d["students"], f"{s} {outcome}")
            y = C[outcome][r]
            L = ladder(A, C, r, cell, y,
                       "01234b" if s == "MAT" else "01234")
            seed = SEED + 1000 * oi + 10 * si
            kinds = (("M0", "M1", "M2", "M3", "M4", "bands") if s == "MAT"
                     else ("M3", "M4"))
            W = {k: wild(model_tests(A, C, r, cell, k), y, seed + j)
                 for j, k in enumerate(kinds)}
            for k in kinds:
                if k not in ("M4", "bands"):
                    gap = max(gap, abs(R.coef(L[k], "log2_size")[0]
                                       - W[k]["log2_size"][0]))
            keepres[(outcome, s)] = (L, r, W)
            row = {"outcome": outcome, "subject": s,
                   "class": "quantitative" if s in R.QUANT else "other", **d}
            for m in ("M0", "M1", "M2", "M3"):
                b, se = R.coef(L[m], "log2_size")
                row[m.lower()], row[m.lower() + "_se"] = b, se
                row[m.lower() + "_hw"] = W[m]["log2_size"][2] if m in W \
                    else np.nan
            row["m3_p_wild"] = W["M3"]["log2_size"][1]
            row["m4"], row["m4_se"] = R.coef(L["M4"], "log2_size_x_math")
            _, row["m4_p_wild"], row["m4_hw"] = W["M4"].get(
                "log2_size_x_math", (np.nan, np.nan, np.nan))
            prim.append(row)
            for m, f in L.items():
                for nm, b, se in zip(f["names"], f["beta"], f["se"]):
                    if nm.startswith(("log2_size", "size_", "math_score",
                                      "verbal_score")):
                        _, pw, hw = W.get(m, {}).get(nm, (np.nan,) * 3)
                        coefs.append((outcome, s, m, nm, f4(b), f4(se),
                                      f4(pt(b, se, f["G"])), f4(pw), f4(hw),
                                      f["n"], f["G"]))
        log(f"subject ladders done: {outcome}")
    for outcome in ("grade", "dfw"):
        sel = [r for r in prim if r["outcome"] == outcome]
        for key, flag in (("m3_p_wild", "bh_m3"), ("m4_p_wild", "bh_m4")):
            for r, fl in zip(sel, M.bh([r[key] for r in sel])):
                r[flag] = int(fl)
    head = ["outcome", "subject", "class", "rows", "students", "sections",
            "instructors", "cells", "m0", "m0_se", "m0_hw", "m1", "m1_se",
            "m1_hw", "m2", "m2_se", "m2_hw", "m3", "m3_se", "m3_hw",
            "m3_p_wild", "bh_m3", "m4", "m4_se", "m4_hw", "m4_p_wild",
            "bh_m4"]
    write(out / "cs_primary.csv", head,
          [[f4(r[k]) if isinstance(r[k], float) else r[k] for k in head]
           for r in prim])
    write(out / "cs_coefficients.csv",
          ["outcome", "subject", "model", "term", "estimate", "se",
           "p_cluster_t", "p_wild_bootstrap", "wild_half_width", "rows",
           "instructor_clusters"], coefs)

    # pooling uses the bootstrap half-width as the standard error scale
    pooled = []
    for outcome in ("grade", "dfw"):
        for cls in ("all", "quantitative", "other",
                    "all with 20 or more instructors"):
            sel = [r for r in prim if r["outcome"] == outcome
                   and (cls == "all" or r["class"] == cls
                        or (cls.startswith("all with")
                            and r["instructors"] >= 20))]
            for nm, flag in (("m3", "bh_m3"), ("m4", "bh_m4")):
                p = M.pool_dl([r[nm] for r in sel],
                              [r[nm + "_hw"] / 1.96 for r in sel])
                pooled.append((outcome, cls, nm, len(sel),
                               f4(p.get("estimate", np.nan)),
                               f4(p.get("lo", np.nan)),
                               f4(p.get("hi", np.nan)),
                               sum(r[flag] for r in sel)))
    write(out / "cs_pooled.csv",
          ["outcome", "class", "model", "subjects", "pooled", "lo", "hi",
           "subjects_passing_fdr"], pooled)
    res["solver_agreement"] = gap
    pr = np.array([[r["m3_p_wild"], r["m4_p_wild"]] for r in prim])
    res["share_wild_p_below_0.05"] = {
        "m3": float(np.nanmean(pr[:, 0] < 0.05)),
        "m4_interaction": float(np.nanmean(pr[:, 1] < 0.05)),
        "tests": len(prim)}
    return prim, keepres


def student_fe(A, C, subjects, base, out):
    rows = []
    for outcome in ("grade", "dfw"):
        r = np.flatnonzero(np.isin(C["subj"], subjects) & base
                           & np.isfinite(C[outcome]))
        for _ in range(3):                 # drop singleton students / cells
            cell = cell_key(C, r)
            g, ng = M.group_index(cell)
            s, ns = M.group_index(C["stu"][r])
            ok = ((np.bincount(g, minlength=ng)[g] >= 2)
                  & (np.bincount(s, minlength=ns)[s] >= 2))
            r = r[ok]
        cell, stu, inst = cell_key(C, r), C["stu"][r], C["inst"][r]
        guard(len(np.unique(stu)), f"student fixed effects {outcome}")
        ls = np.log2(C["size"][r])
        mat = (C["subj"][r] == "MAT").astype(float)
        f1 = fit_fe([ls], ["log2_size"], C[outcome][r], [stu, cell], inst)
        f2 = fit_fe([ls * mat, ls * (1 - mat)],
                    ["log2_size_MAT", "log2_size_other"], C[outcome][r],
                    [stu, cell], inst)
        for f in (f1, f2):
            for nm, b, se in zip(f["names"], f["beta"], f["se"]):
                rows.append((outcome, nm, f4(b), f4(se),
                             f4(pt(b, se, f["G"])), f4(tcrit(f["G"]) * se),
                             len(r), len(np.unique(stu)), f["G"]))
    write(out / "cs_student_fe.csv",
          ["outcome", "term", "estimate", "se", "p_cluster_t",
           "cluster_t_half_width", "rows", "students",
           "instructor_clusters"], rows)
    log("student fixed-effects models done")
    return rows


def next_course(A, C, base, out):
    """the leniency check on the mathematics sequence (Section 6)"""
    nm = CS.next_math(C)
    o, nx = nm["row"], nm["nxt"]
    ok = base[o] & np.isfinite(C["dfw"][o])
    o, nx = o[ok], nx[ok]
    rows = []

    def rec(label, f, n, students, w=None,
            terms=("log2_size", "origin_grade")):
        for t in terms:
            b, se = R.coef(f, t)
            if not np.isfinite(b):
                continue
            pw, hw = (w[t][1], w[t][2]) if w and t in w else (np.nan, np.nan)
            rows.append((label, t, f4(b), f4(se), f4(pt(b, se, f["G"])),
                         f4(pw), f4(hw if np.isfinite(hw)
                                    else tcrit(f["G"]) * se),
                         "wild bootstrap" if np.isfinite(hw) else "cluster t",
                         n, students, f["G"]))

    def design(r):
        X, names = R.build(A, C["stu"][r], BLOCKS)
        return X, [X[:, j] for j in range(X.shape[1])], names

    # continuation: takes a later mathematics course in the window
    cell = cell_key(C, o)
    g, ng = M.group_index(cell)
    k = np.bincount(g, minlength=ng)[g] >= 2
    r, c, y = o[k], cell[k], (nx[k] >= 0).astype(float)
    guard(len(np.unique(C["stu"][r])), "continuation")
    ls, inst = np.log2(C["size"][r]), C["inst"][r]
    X, covs, names = design(r)
    for j, (label, fes) in enumerate((
            ("continuation: course-term effects", [c]),
            ("continuation: course-term and instructor effects", [c, inst]))):
        f = fit_fe([ls] + covs, ["log2_size"] + names, y, fes, inst)
        w = wild(term_tests(ls[:, None], ["log2_size"], X, c,
                            inst if j else None, inst), y, SEED + 500 + j)
        rec(label, f, len(r), len(np.unique(C["stu"][r])), w)
    # next-course grade among continuers
    k = (nx >= 0)
    k[k] &= np.isfinite(C["grade"][nx[k]])
    k &= np.isfinite(C["grade"][o])
    r, n2 = o[k], nx[k]
    guard(len(np.unique(C["stu"][r])), "next-course grade")
    c1, c2 = cell_key(C, r), cell_key(C, n2)
    ls, y, g0 = np.log2(C["size"][r]), C["grade"][n2], C["grade"][r]
    X, covs, names = design(r)
    inst = C["inst"][r]
    f = fit_fe([ls] + covs, ["log2_size"] + names, y, [c1, c2], inst)
    w = wild(term_tests(ls[:, None], ["log2_size"], X, c1, c2, inst), y,
             SEED + 510)
    rec("next grade: total", f, len(r), len(np.unique(C["stu"][r])), w)
    f = fit_fe([ls, g0] + covs, ["log2_size", "origin_grade"] + names, y,
               [c1, c2], inst)
    w = wild(term_tests(ls[:, None], ["log2_size"],
                        np.column_stack([g0, X]), c1, c2, inst), y,
             SEED + 511)
    rec("next grade: given the origin grade", f, len(r),
        len(np.unique(C["stu"][r])), w)
    f = fit_fe([ls, g0] + covs, ["log2_size", "origin_grade"] + names, y,
               [c1, c2, inst], inst)
    rec("next grade: given the origin grade and instructor effects", f,
        len(r), len(np.unique(C["stu"][r])))
    write(out / "cs_next_course.csv",
          ["model", "term", "estimate", "se", "p_cluster_t",
           "p_wild_bootstrap", "half_width", "interval_from", "rows",
           "students", "instructor_clusters"], rows)
    log("next-course models done")
    return rows


def projection(A, C, sec, modeled, keepres, out, res):
    """scenario: every primary section above the cap is split evenly"""
    first, last = FIRST_COHORT * 3 + 2, (D.LAST_Q2_COHORT + 1) * 3 + 1
    years = D.LAST_Q2_COHORT - FIRST_COHORT + 1
    rows, tot = [], {}
    for s in modeled:
        have = [n["size"] for (tix, _), n in sec.items()
                if n["subj"] == s and n["sched"] == CS.LECTURE
                and n["size"] > CS.MIN_SECTION and first <= tix <= last]
        added = sum(int(np.ceil(n / CAP)) - 1 for n in have if n > CAP)
        for outcome in ("grade", "dfw"):
            L, r, W = keepres[(outcome, s)]
            n = C["size"][r]
            hit = n > CAP
            delta = np.where(hit, np.log2(n / np.ceil(n / CAP)) - np.log2(n),
                             0.0)
            b = R.coef(L["M3"], "log2_size")[0]
            hw = W["M3"]["log2_size"][2]
            total, thw = b * delta.sum(), hw * abs(delta.sum())
            scale = 100.0 if outcome == "dfw" else 1.0
            aff = max(int(hit.sum()), 1)
            per = outcome == "dfw"
            rows.append((
                s, outcome, len(r), int(hit.sum()),
                f4(float(delta[hit].mean()) if hit.any() else 0.0),
                f4(scale * total / aff), f4(scale * (total - thw) / aff),
                f4(scale * (total + thw) / aff),
                f4(scale * total / len(r)),
                f4(total / years) if per else "",
                f4((total - thw) / years) if per else "",
                f4((total + thw) / years) if per else "",
                len(have), added, f4(len(have) / years), f4(added / years)))
            t = tot.setdefault(outcome, [0.0, 0.0, 0, 0, 0, 0])
            t[0] += total
            t[1] += (thw / 1.96) ** 2
            t[2] += len(r)
            t[3] += int(hit.sum())
            if per:
                t[4] += len(have)
                t[5] += added
    write(out / "cs_projection.csv",
          ["subject", "outcome", "first_attempts", "affected_first_attempts",
           "mean_change_log2_size", "change_among_affected",
           "lo", "hi", "change_over_all_first_attempts",
           "dfw_outcomes_per_cohort", "per_cohort_lo", "per_cohort_hi",
           "sections_in_window", "sections_added", "sections_per_year",
           "sections_added_per_year"], rows)
    t = tot["dfw"]
    s_ = np.sqrt(t[1])
    res["scenario_all_subjects"] = {
        "cap": CAP, "subjects": len(modeled),
        "dfw_outcomes_per_cohort": t[0] / years,
        "lo": (t[0] - 1.96 * s_) / years, "hi": (t[0] + 1.96 * s_) / years,
        "first_attempts": t[2], "affected": t[3],
        "sections_per_year": t[4] / years,
        "sections_added_per_year": t[5] / years,
        "note": "interval assumes independent subject estimates"}
    # mathematics: the scenario by entry-score third, from the interaction
    ter = []
    for outcome in ("grade", "dfw"):
        L, r, _ = keepres[(outcome, "MAT")]
        f = L["M4"]
        if "log2_size_x_math" not in f["names"]:
            continue
        i = f["names"].index("log2_size")
        j = f["names"].index("log2_size_x_math")
        zm = A["zm"][C["stu"][r]]
        n = C["size"][r]
        hit = (n > CAP) & np.isfinite(zm)
        delta = np.log2(n / np.ceil(n / CAP)) - np.log2(n)
        cut = np.percentile(zm[np.isfinite(zm)], [100 / 3, 200 / 3])
        band = np.digitize(zm, cut)
        tc = tcrit(f["G"])
        for k, lab in enumerate(("lowest third", "middle third",
                                 "highest third")):
            m = hit & (band == k)
            guard(len(np.unique(C["stu"][r][m])), f"MAT {lab}")
            a = np.zeros(len(f["beta"]))
            a[i], a[j] = delta[m].sum(), (zm[m] * delta[m]).sum()
            est = float(a @ f["beta"])
            se = float(np.sqrt(max(a @ f["V"] @ a, 0.0)))
            scale = 100.0 if outcome == "dfw" else 1.0
            k_ = max(int(m.sum()), 1)
            ter.append((outcome, lab, int(m.sum()), f4(scale * est / k_),
                        f4(scale * (est - tc * se) / k_),
                        f4(scale * (est + tc * se) / k_)))
    write(out / "cs_projection_mat_thirds.csv",
          ["outcome", "entry_math_score", "affected_first_attempts",
           "change_among_affected", "cluster_t_lo", "cluster_t_hi"], ter)
    log("scenario written")


def sensitivity(A, C, modeled, out):
    """the primary model (M3) under alternative samples"""
    lec = exposure_mask(C, {CS.LECTURE})
    variants = {
        "primary": lec,
        "linked sample": lec & A["linked"][C["stu"]],
        "all lecture formats": exposure_mask(C, CS.LECTURE_ANY),
        "CAP entrants excluded": lec & (A["cap"][C["stu"]] == 0),
        "entry fall only": lec & (C["off"] == 0),
        "sections of 20 or more": lec & (C["size"] >= 20),
    }
    rows = []
    for vi, (label, base) in enumerate(variants.items()):
        for oi, outcome in enumerate(("grade", "dfw")):
            est, ses = [], []
            for si, s in enumerate(modeled):
                r, cell = rows_of(C, s, base, outcome)
                if len(np.unique(C["stu"][r])) < MIN_STUDENTS:
                    continue
                y = C[outcome][r]
                b, pw, hw = wild(model_tests(A, C, r, cell, "M3"), y,
                                 SEED + 7000 + 100 * vi + 50 * oi + si
                                 )["log2_size"]
                if not (np.isfinite(b) and np.isfinite(hw)):
                    continue
                est.append(b)
                ses.append(hw / 1.96)
                if s == "MAT":
                    rows.append((label, outcome, "MAT", f4(b), f4(b - hw),
                                 f4(b + hw), f4(pw), len(r)))
            p = M.pool_dl(est, ses)
            rows.append((label, outcome, f"pooled, {p['k']} subjects",
                         f4(p.get("estimate", np.nan)),
                         f4(p.get("lo", np.nan)), f4(p.get("hi", np.nan)),
                         "", ""))
        log(f"sensitivity: {label}")
    write(out / "cs_sensitivity.csv",
          ["variant", "outcome", "estimate_for", "m3_per_doubling", "lo",
           "hi", "p_wild_bootstrap", "rows"], rows)


# ----------------------------------------------------------------- driver
def permute(C):
    """shuffle grades within course-by-term cells (dry run)"""
    rng = np.random.default_rng(SEED + 1)
    key = cell_key(C, np.arange(len(C["stu"])))
    g, _ = M.group_index(key)
    order = np.argsort(g, kind="stable")
    starts = np.flatnonzero(np.diff(g[order], prepend=-1))
    for a, b in zip(starts, list(starts[1:]) + [len(order)]):
        i = order[a:b]
        p = rng.permutation(i)
        C["grade"][i], C["dfw"][i] = C["grade"][p], C["dfw"][p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--permute", action="store_true")
    ap.add_argument("--stage0-only", action="store_true")
    ap.add_argument("--calibrate", action="store_true",
                    help="dry run only: rejection rates under shuffles")
    ap.add_argument("--tag", default=None, help="output folder name")
    a = ap.parse_args()
    D.set_first_cohort(FIRST_COHORT)
    out = OUT / (a.tag or ("stage0" if a.stage0_only else
                           "dryrun" if a.permute else "registered"))
    out.mkdir(parents=True, exist_ok=True)
    with open(SUBJECTS_FILE, encoding="utf-8") as fh:
        subjects = [r["subject"] for r in csv.DictReader(fh)]
    salt = D.new_salt()
    S = D.load_students(salt)
    log(f"students loaded: {S['n']:,}")
    ctx = D.load_context(set(zip(S["hs_name"], S["hs_city"])))
    A = D.assemble(S, ctx)
    sec = CS.load_sections(salt)
    C = CS.load_rows(salt, S["sid"], sec, with_outcomes=not a.stage0_only)
    A["sid"] = None                       # surrogate no longer needed
    log(f"sections: {len(sec):,}; first attempts: {len(C['stu']):,}"
        + (" (no grade field read)" if a.stage0_only else ""))
    R.prepare(A)
    base = exposure_mask(C, {CS.LECTURE})
    modeled = stage0(A, C, sec, subjects, base, out)
    if a.stage0_only:
        return
    if a.calibrate and not a.permute:
        raise SystemExit("--calibrate runs only with --permute")
    if a.permute:
        permute(C)
        log("grades permuted within course-by-term cells (dry run)")
        if a.calibrate:
            calibrate(A, C, base, out)
    res = {"mode": "dry run on permuted outcomes" if a.permute
           else "registered estimation", "seed": SEED, "cap": CAP,
           "cohorts": [FIRST_COHORT, D.LAST_Q2_COHORT],
           "subjects_modeled": modeled,
           "subjects_outside_entry_rule": [s for s in subjects
                                           if s not in modeled]}
    prim, keepres = run_models(A, C, modeled, base, out, res)
    sfe = student_fe(A, C, subjects, base, out)
    nxt = next_course(A, C, base, out)
    projection(A, C, sec, modeled, keepres, out, res)
    sensitivity(A, C, modeled, out)

    g = next(r for r in prim if r["outcome"] == "grade"
             and r["subject"] == "MAT")
    d = next(r for r in prim if r["outcome"] == "dfw"
             and r["subject"] == "MAT")
    sfe_mat = next(float(r[2]) for r in sfe
                   if r[0] == "grade" and r[1] == "log2_size_MAT")
    res["H3"] = {
        "mat_m3_grade_per_doubling": g["m3"],
        "lo": g["m3"] - g["m3_hw"], "hi": g["m3"] + g["m3_hw"],
        "wild_bootstrap_p": g["m3_p_wild"],
        "mat_m3_dfw_per_doubling": d["m3"],
        "dfw_lo": d["m3"] - d["m3_hw"], "dfw_hi": d["m3"] + d["m3_hw"],
        "dfw_wild_bootstrap_p": d["m3_p_wild"],
        "student_fe_mat_grade": sfe_mat,
        "supported": bool(g["m3"] + g["m3_hw"] < 0
                          and g["m3_p_wild"] < 0.05 and sfe_mat < 0)}
    res["H4"] = {
        "mat_m4_size_x_math_grade": g["m4"],
        "lo": g["m4"] - g["m4_hw"], "hi": g["m4"] + g["m4_hw"],
        "wild_bootstrap_p": g["m4_p_wild"],
        "supported": bool(g["m4"] - g["m4_hw"] > 0
                          and g["m4_p_wild"] < 0.05)}
    row = next(r for r in nxt if r[0] == "next grade: given the origin grade"
               and r[1] == "log2_size")
    e, hw = float(row[2]), float(row[6])
    res["leniency_check"] = {
        "next_grade_per_doubling_given_origin_grade": e,
        "lo": e - hw, "hi": e + hw, "wild_bootstrap_p": float(row[5]),
        "leniency_indicated": bool(e - hw > 0)}
    res["seconds"] = round(R.time.time() - R.T0)
    (out / "results.json").write_text(json.dumps(res, indent=1),
                                      encoding="utf-8")
    log(f"finished: {out}")


if __name__ == "__main__":
    main()
