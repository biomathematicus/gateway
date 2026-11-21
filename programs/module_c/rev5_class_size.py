"""Class-size addendum: corrections after the REV5 review
(Economics/Paper0/module_c/class_size_addendum.md, Section 14, D1).

    python rev5_class_size.py               corrected inference
    python rev5_class_size.py --calibrate   also: rejection rates of the
                                            contrast tests under shuffles

The registered runner (run_class_size.py) is imported unchanged, and its
outputs in class_size/registered/ are left as they are. This script
writes to class_size/rev5/:

cs_contrasts.csv       linear contrasts of the size coefficient and the
                       size-by-score interaction of M4 in mathematics
                       (the cap scenario by third of the entry score,
                       the size slope at given entry scores), each with
                       the wild cluster bootstrap of the registered
                       terms, the interval obtained by inverting that
                       test, and the clustered-t interval the registered
                       table printed
cs_contrast_calibration.csv   rejection rates of those tests on grades
                       shuffled within course-by-term cells
cs_pooled_joint.csv    pooled M3 coefficients and the all-subject
                       scenario total with intervals that include the
                       covariance between subject estimates
cs_next_course_subset.csv   the next-course check on continuers whose
                       next course has a different instructor
cs_support.csv         support for the cap scenario inside course-by-term
                       cells, by third of the entry score
cs_section_sizes.csv   observed sizes of the Calculus I and II sections

Student rows live in memory only; every file is an aggregate.
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
import run_class_size as K  # noqa: E402  (registered, unchanged)

R, M, D, CS = K.R, K.M, K.D, K.CS
OUT = K.OUT / "rev5"
REG = K.OUT / "registered"
SEED = K.SEED + 50000
THIRDS = ("lowest third", "middle third", "highest third")
log, guard, write, f4 = K.log, K.guard, K.write, K.f4


def read(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load():
    D.set_first_cohort(K.FIRST_COHORT)
    salt = D.new_salt()
    S = D.load_students(salt)
    ctx = D.load_context(set(zip(S["hs_name"], S["hs_city"])))
    A = D.assemble(S, ctx)
    sec = CS.load_sections(salt)
    C = CS.load_rows(salt, S["sid"], sec, with_outcomes=True)
    A["sid"] = None
    R.prepare(A)
    log(f"students {S['n']:,}; sections {len(sec):,}; first attempts "
        f"{len(C['stu']):,}")
    return A, C, sec


# ------------------------------------------------------------- contrasts
def contrast_test(A, C, r, cell, w):
    """the M4 model reparametrized so that one coefficient equals
    w[0] * (size coefficient) + w[1] * (size-by-score interaction);
    returns the registered SizeTest object for that coefficient"""
    idx, inst = C["stu"][r], C["inst"][r]
    ls = np.log2(C["size"][r]) - np.log2(K.CAP)
    E = np.column_stack([ls, ls * np.nan_to_num(A["zm"][idx])])
    T = np.array([[w[0], w[1]], [-w[1], w[0]]], dtype=float)
    X = R.build(A, idx, K.BLOCKS)[0]
    return K.term_tests(E @ np.linalg.inv(T), ["contrast", "rest"], X, cell,
                        inst, inst)["contrast"]


def invert(st, ytil, b0, hw, seed, level=0.05):
    """the set of null values the wild bootstrap test does not reject:
    for a null value t0 the restricted residual is ytil - x * t0, and
    the registered test is applied to it with common random numbers"""
    def p_at(t0):
        return st.wild(ytil - st.x * t0, np.random.default_rng(seed),
                       K.NBOOT)[1]

    ends = []
    for sign in (-1.0, 1.0):
        inside, outside = b0, b0 + sign * 1.5 * hw
        for _ in range(10):
            if p_at(outside) < level:
                break
            inside, outside = outside, outside + sign * hw
        for _ in range(12):
            mid = 0.5 * (inside + outside)
            if p_at(mid) < level:
                outside = mid
            else:
                inside = mid
        ends.append(inside)
    return ends[0], ends[1]


def scenario_weights(A, C, r):
    """contrast weights of the cap scenario, per affected first attempt,
    by third of the entry mathematics score (the registered definition)"""
    zm = A["zm"][C["stu"][r]]
    n = C["size"][r]
    delta = np.log2(n / np.ceil(n / K.CAP)) - np.log2(n)
    hit = (n > K.CAP) & np.isfinite(zm)
    cut = np.percentile(zm[np.isfinite(zm)], [100 / 3, 200 / 3])
    band = np.digitize(zm, cut)
    out = []
    for k, lab in enumerate(THIRDS):
        m = hit & (band == k)
        guard(len(np.unique(C["stu"][r][m])), f"MAT {lab}")
        out.append((lab, int(m.sum()), float(delta[m].sum() / m.sum()),
                    float((zm[m] * delta[m]).sum() / m.sum())))
    out.append(("all affected", int(hit.sum()),
                float(delta[hit].sum() / hit.sum()),
                float((zm[hit] * delta[hit]).sum() / hit.sum())))
    return out


def specs_for(A, C, r):
    specs = [(f"cap scenario, {lab}", "per affected first attempt", n,
              (w1, w2)) for lab, n, w1, w2 in scenario_weights(A, C, r)]
    for z in (-1.0, 0.0, 1.0):
        specs.append((f"size slope at entry score {z:+.0f} SD",
                      "per doubling of section size", len(r), (1.0, z)))
    specs.append(("size-by-score interaction",
                  "per doubling and per SD of the entry score", len(r),
                  (0.0, 1.0)))
    return specs


def mat_contrasts(A, C, base, out, res):
    rows, check = [], 0.0
    for oi, outcome in enumerate(("grade", "dfw")):
        r, cell = K.rows_of(C, "MAT", base, outcome)
        y = C[outcome][r]
        f = K.ladder(A, C, r, cell, y, models="4")["M4"]
        i = f["names"].index("log2_size")
        j = f["names"].index("log2_size_x_math")
        tc = K.tcrit(f["G"])
        scale = 100.0 if outcome == "dfw" else 1.0
        for ci, (lab, unit, cnt, w) in enumerate(specs_for(A, C, r)):
            st = contrast_test(A, C, r, cell, w)
            ytil = st.partial(y)
            seed = SEED + 1000 * oi + 10 * ci
            b0, p, hw = st.wild(ytil, np.random.default_rng(seed), K.NBOOT)
            lo_i, hi_i = invert(st, ytil, b0, hw, seed + 5)
            a = np.zeros(len(f["beta"]))
            a[i], a[j] = w
            est = float(a @ f["beta"])
            se = float(np.sqrt(max(a @ f["V"] @ a, 0.0)))
            check = max(check, abs(est - b0))
            rows.append((outcome, lab, unit, cnt, f4(scale * b0),
                         f4(scale * (b0 - hw)), f4(scale * (b0 + hw)), f4(p),
                         f4(scale * lo_i), f4(scale * hi_i),
                         f4(scale * (est - tc * se)),
                         f4(scale * (est + tc * se)),
                         f4(K.pt(est, se, f["G"])), f["G"]))
            log(f"contrast {outcome}: {lab}  {scale * b0:+.4f}  "
                f"wild [{scale * (b0 - hw):+.4f}, {scale * (b0 + hw):+.4f}] "
                f"p={p:.3f}  inverted [{scale * lo_i:+.4f}, "
                f"{scale * hi_i:+.4f}]")
    write(out / "cs_contrasts.csv",
          ["outcome", "contrast", "unit", "first_attempts", "estimate",
           "wild_lo", "wild_hi", "p_wild_bootstrap", "inverted_lo",
           "inverted_hi", "cluster_t_lo", "cluster_t_hi", "p_cluster_t",
           "instructor_clusters"], rows)
    res["contrast_solver_agreement"] = check


def calibrate(A, C, base, out, shuffles=200, draws=199):
    """rejection rates of the contrast tests when grades are shuffled
    within course-by-term cells, so that every size term is null"""
    rows = []
    picks = ("cap scenario, lowest third", "cap scenario, highest third",
             "size slope at entry score -1 SD", "size-by-score interaction")
    for oi, outcome in enumerate(("grade", "dfw")):
        r, cell = K.rows_of(C, "MAT", base, outcome)
        y = C[outcome][r]
        f = K.ladder(A, C, r, cell, y, models="4")["M4"]
        i = f["names"].index("log2_size")
        j = f["names"].index("log2_size_x_math")
        tests = {}
        for lab, _, _, w in specs_for(A, C, r):
            if lab not in picks:
                continue
            st = contrast_test(A, C, r, cell, w)
            b0, t0 = st.stat(st.partial(y))
            a = np.zeros(len(f["beta"]))
            a[i], a[j] = w
            se = float(np.sqrt(max(a @ f["V"] @ a, 0.0)))
            tests[lab] = (st, (se / abs(b0 / t0)) ** 2)
        by_cell = np.argsort(cell, kind="stable")
        rng = np.random.default_rng(SEED + 77 + oi)
        pc = {k: [] for k in tests}
        pw = {k: [] for k in tests}
        for _ in range(shuffles):
            ys = np.empty(len(y))
            ys[by_cell] = y[np.lexsort((rng.random(len(y)), cell))]
            for lab, (st, fac) in tests.items():
                u = st.partial(ys)
                _, t = st.stat(u)
                pc[lab].append(2 * stats.t.sf(abs(t) / np.sqrt(fac),
                                              st.G - 1))
                pw[lab].append(st.wild(u, rng, draws)[1])
        for lab, (st, _) in tests.items():
            a, b = np.array(pc[lab]), np.array(pw[lab])
            rows.append((outcome, lab, st.G, len(r), shuffles,
                         f4(float((a < 0.05).mean())),
                         f4(float((b < 0.05).mean())),
                         f4(float((a < 0.10).mean())),
                         f4(float((b < 0.10).mean()))))
        log(f"calibration done: {outcome}")
    write(out / "cs_contrast_calibration.csv",
          ["outcome", "contrast", "instructor_clusters", "rows", "shuffles",
           "cluster_t_reject_05", "wild_reject_05", "cluster_t_reject_10",
           "wild_reject_10"], rows)


# ------------------------------------------------- covariance-aware pooling
def gram(keys, sj, psi, ns):
    g, ng = M.group_index(keys)
    H = np.zeros((ng, ns))
    np.add.at(H, (g, sj), psi)
    return H.T @ H


def to_corr(V):
    d = np.sqrt(np.clip(np.diag(V), 1e-300, None))
    Rm = V / np.outer(d, d)
    Rm = (Rm + Rm.T) / 2
    w, U = np.linalg.eigh(Rm)
    Rm = (U * np.clip(w, 0.0, None)) @ U.T
    d = np.sqrt(np.diag(Rm))
    return Rm / np.outer(d, d)


def joint(A, C, modeled, base, out, res):
    """the primary coefficient of every subject in one stacked system:
    each row's influence on its subject's coefficient is summed within
    instructors and within students, which gives the correlation between
    subject estimates that shared instructors and shared students
    produce (two-way clustering). The registered bootstrap standard
    error of each subject is kept on the diagonal."""
    prim = {(r["outcome"], r["subject"]): r for r in read(REG / "cs_primary.csv")}
    years = D.LAST_Q2_COHORT - K.FIRST_COHORT + 1
    ns = len(modeled)
    rows = []
    for outcome in ("grade", "dfw"):
        stu, ins, sj, psi = [], [], [], []
        b, se, big, nrow, ninst = (np.zeros(ns) for _ in range(5))
        for si, s in enumerate(modeled):
            r, cell = K.rows_of(C, s, base, outcome)
            y = C[outcome][r]
            st = K.model_tests(A, C, r, cell, "M3")["log2_size"]
            ytil = st.partial(y)
            bs = float(st.x @ ytil / st.sxx)
            reg = prim[(outcome, s)]
            if abs(bs - float(reg["m3"])) > 2e-4:
                raise SystemExit(f"{s} {outcome}: {bs} against registered "
                                 f"{reg['m3']}")
            psi.append(st.x * (ytil - st.x * bs) / st.sxx)
            stu.append(C["stu"][r])
            ins.append(C["inst"][r])
            sj.append(np.full(len(r), si))
            b[si], se[si] = bs, float(reg["m3_hw"]) / 1.96
            n = C["size"][r]
            hit = n > K.CAP
            big[si] = np.where(hit, np.log2(n / np.ceil(n / K.CAP))
                               - np.log2(n), 0.0).sum()
            nrow[si], ninst[si] = len(r), st.G
        stu, ins, sj, psi = map(np.concatenate, (stu, ins, sj, psi))
        gi, ni = M.group_index(ins)
        V_i = gram(gi, sj, psi, ns)
        V_s = gram(stu, sj, psi, ns)
        V_x = gram(stu.astype(np.int64) * ni + gi, sj, psi, ns)
        Rm = to_corr(V_i + V_s - V_x)
        R_i = to_corr(V_i)
        off = ~np.eye(ns, dtype=bool)
        cov = np.outer(se, se) * Rm
        quant = np.array([s in R.QUANT for s in modeled])
        for cls, sel in (("all", np.ones(ns, bool)), ("quantitative", quant),
                         ("other", ~quant),
                         ("all with 20 or more instructors", ninst >= 20)):
            p = M.pool_dl(b[sel], se[sel])
            w = 1.0 / (se[sel] ** 2 + p["tau2"])
            w /= w.sum()
            sj_ = float(np.sqrt(w @ (cov[np.ix_(sel, sel)]
                                     + p["tau2"] * np.eye(sel.sum())) @ w))
            rows.append((outcome, f"pooled M3, {cls}", int(sel.sum()),
                         f4(p["estimate"]), f4(p["lo"]), f4(p["hi"]),
                         f4(p["estimate"] - 1.96 * sj_),
                         f4(p["estimate"] + 1.96 * sj_)))
        if outcome == "dfw":
            c = big / years
            tot = float(c @ b)
            s_ind = float(np.sqrt(((c * se) ** 2).sum()))
            s_jnt = float(np.sqrt(c @ cov @ c))
            rows.append((outcome, "cap scenario, DFW outcomes per cohort, "
                         "all subjects", ns, f4(tot), f4(tot - 1.96 * s_ind),
                         f4(tot + 1.96 * s_ind), f4(tot - 1.96 * s_jnt),
                         f4(tot + 1.96 * s_jnt)))
            res["scenario_all_subjects_joint"] = {
                "dfw_outcomes_per_cohort": tot,
                "lo": tot - 1.96 * s_jnt, "hi": tot + 1.96 * s_jnt,
                "lo_independent": tot - 1.96 * s_ind,
                "hi_independent": tot + 1.96 * s_ind}
        pairs = np.unique(stu.astype(np.int64) * ns + sj)
        per = np.bincount(M.group_index(pairs // ns)[0])
        res[f"subject_correlation_{outcome}"] = {
            "mean_off_diagonal": float(Rm[off].mean()),
            "largest_absolute": float(np.abs(Rm[off]).max()),
            "mean_off_diagonal_instructors_only": float(R_i[off].mean()),
            "students": int(len(per)),
            "students_in_two_or_more_subjects": int((per >= 2).sum())}
        log(f"joint pooling done: {outcome}")
    write(out / "cs_pooled_joint.csv",
          ["outcome", "summary", "subjects", "estimate", "lo_independent",
           "hi_independent", "lo_joint", "hi_joint"], rows)


# ------------------------------------------------------ next-course subset
def next_course_subset(A, C, base, out, res):
    nm = CS.next_math(C)
    o, nx = nm["row"], nm["nxt"]
    ok = base[o] & np.isfinite(C["dfw"][o])
    o, nx = o[ok], nx[ok]
    k = nx >= 0
    cont = int(k.sum())
    k[k] &= np.isfinite(C["grade"][nx[k]])
    k &= np.isfinite(C["grade"][o])
    r, n2 = o[k], nx[k]
    known = C["secid"][n2] != 0
    diff = known & (C["inst"][n2] != C["inst"][r])
    res["next_course_flow"] = {
        "origin_first_attempts": guard(int(len(o)), "origin rows"),
        "take_a_later_mathematics_course": guard(cont, "continuers"),
        "with_grades_in_both_courses": guard(int(len(r)), "both grades"),
        "next_section_identified": guard(int(known.sum()), "known section"),
        "next_course_different_instructor": guard(int(diff.sum()), "diff"),
        "next_course_same_instructor": int((known & ~diff).sum())}
    rows = []
    for label, m in (("all continuers (registered)", np.ones(len(r), bool)),
                     ("next course with a different instructor", diff)):
        rr, nn = r[m], n2[m]
        guard(len(np.unique(C["stu"][rr])), label)
        c1, c2 = K.cell_key(C, rr), K.cell_key(C, nn)
        ls, y, g0 = np.log2(C["size"][rr]), C["grade"][nn], C["grade"][rr]
        X, names = R.build(A, C["stu"][rr], K.BLOCKS)
        covs = [X[:, q] for q in range(X.shape[1])]
        inst = C["inst"][rr]
        f = K.fit_fe([ls, g0] + covs, ["log2_size", "origin_grade"] + names,
                     y, [c1, c2], inst)
        w = K.wild(K.term_tests(ls[:, None], ["log2_size"],
                                np.column_stack([g0, X]), c1, c2, inst), y,
                   K.SEED + 511)["log2_size"]
        bb, se = R.coef(f, "log2_size")
        rows.append((label, "origin and next course-by-term effects",
                     f4(bb), f4(bb - w[2]), f4(bb + w[2]), f4(w[1]),
                     "wild bootstrap", len(rr), f["G"]))
        if m.all():
            continue
        f = K.fit_fe([ls, g0] + covs, ["log2_size", "origin_grade"] + names,
                     y, [c1, c2, C["inst"][nn]], inst)
        bb, se = R.coef(f, "log2_size")
        hw = K.tcrit(f["G"]) * se
        rows.append((label, "and next-course instructor effects", f4(bb),
                     f4(bb - hw), f4(bb + hw), f4(K.pt(bb, se, f["G"])),
                     "cluster t", len(rr), f["G"]))
    write(out / "cs_next_course_subset.csv",
          ["sample", "fixed_effects", "next_grade_per_doubling_given_origin",
           "lo", "hi", "p", "interval_from", "rows", "instructor_clusters"],
          rows)
    log("next-course subset done")


# ---------------------------------------------------- support and sizes
def support(A, C, sec, base, out):
    r, cell = K.rows_of(C, "MAT", base, "dfw")
    n = C["size"][r]
    zm = A["zm"][C["stu"][r]]
    g, ng = M.group_index(cell)
    has_small = (np.bincount(g, (n <= K.CAP).astype(float), ng) > 0)[g]
    cmin = np.full(ng, np.inf)
    np.minimum.at(cmin, g, n)
    post = n / np.ceil(n / K.CAP)
    seen = cmin[g] <= post * 1.10
    cut = np.percentile(zm[np.isfinite(zm)], [100 / 3, 200 / 3])
    band = np.where(np.isfinite(zm), np.digitize(zm, cut), -1)
    rows = []
    for k, lab in list(enumerate(THIRDS)) + [(None, "all with a score")]:
        m = (band == k) if k is not None else (band >= 0)
        aff = m & (n > K.CAP)
        guard(len(np.unique(C["stu"][r][aff])), f"support {lab}")
        rows.append((lab, int(m.sum()), int((m & (n <= K.CAP)).sum()),
                     int(aff.sum()), f"{np.median(n[aff]):.0f}",
                     f"{np.median(post[aff]):.0f}",
                     f4(float(has_small[aff].mean())),
                     f4(float(seen[aff].mean()))))
    write(out / "cs_support.csv",
          ["entry_math_score", "first_attempts", "in_sections_of_45_or_fewer",
           "affected_first_attempts", "median_size_now_among_affected",
           "median_size_after_split",
           "share_affected_in_cells_with_a_section_of_45_or_fewer",
           "share_affected_whose_cell_holds_a_section_near_the_split_size"],
          rows)
    first = K.FIRST_COHORT * 3 + 2
    last = (D.LAST_Q2_COHORT + 1) * 3 + 1
    rows = []
    for lab, nums in (("Calculus I and II (MAT 1214, 1224)", {1214, 1224}),
                      ("courses below Calculus (levels 0 to 2)",
                       {q for q, lv in D.MAT_LEVEL.items() if lv <= 2})):
        sz = np.array([s["size"] for (tix, _), s in sec.items()
                       if s["subj"] == "MAT" and s["num"] in nums
                       and s["sched"] == CS.LECTURE
                       and s["size"] > CS.MIN_SECTION
                       and first <= tix <= last], dtype=float)
        if len(sz) < 10:
            continue
        q = np.percentile(sz, [10, 25, 50, 75, 90])
        rows.append((lab, len(sz), *(f"{v:.0f}" for v in q),
                     f4(float((sz <= 45).mean())),
                     f4(float((sz <= 50).mean())),
                     f4(float((sz > 100).mean()))))
    write(out / "cs_section_sizes.csv",
          ["courses", "lecture_sections", "p10", "p25", "p50", "p75", "p90",
           "share_45_or_fewer", "share_50_or_fewer", "share_above_100"], rows)
    log("support and section sizes done")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--only", default="", help="comma list of steps: "
                    "contrasts, joint, next, support")
    a = ap.parse_args()
    steps = set(a.only.split(",")) if a.only else {"contrasts", "joint",
                                                   "next", "support"}
    OUT.mkdir(parents=True, exist_ok=True)
    reg = json.loads((REG / "results.json").read_text(encoding="utf-8"))
    modeled = reg["subjects_modeled"]
    A, C, sec = load()
    base = K.exposure_mask(C, {CS.LECTURE})
    path = OUT / "results.json"
    res = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    res.update({"mode": "post-registration corrections (addendum Section "
                "14, D1)", "seed": SEED, "bootstrap_draws": K.NBOOT})
    if "contrasts" in steps:
        mat_contrasts(A, C, base, OUT, res)
    if "joint" in steps:
        joint(A, C, modeled, base, OUT, res)
    if "next" in steps:
        next_course_subset(A, C, base, OUT, res)
    if "support" in steps:
        support(A, C, sec, base, OUT)
    if a.calibrate:
        calibrate(A, C, base, OUT)
    res["seconds"] = round(R.time.time() - R.T0)
    path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    log(f"finished: {OUT}")


if __name__ == "__main__":
    main()
