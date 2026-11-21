"""figCourseGradients: is the Algebra II poverty gradient subject-specific?

Context exhibit for Paper 0 (source-specific, standalone, no person-level
joins). Repeats the estimator of figAlgebraIIPoverty for every CRDC
course family and places the 15 families on one scale. Reads
mart.course_poverty in the GATEWAY database (CRDC district aggregation x
SAIPE, loaded by code/ingest/crdc_courses.py).

FRAME. The districts of figAlgebraIIPoverty (SAIPE-matched, at least 200
children aged 5-17, Algebra II enrollment reported) that hold no
missing-coded course item. Three states of a district total are kept
apart: a count; a structural zero (every school skips the item: CRDC
skip logic for zero classes); and an incomplete total (some school holds
a reserve code other than the skip code). A district with an incomplete
total in any of the 15 course families leaves the common frame, so every
course is compared on the same districts. Two variants go to the stats
file: the frame with the incomplete districts kept, and a neutral frame
(districts reporting any core high-school course enrollment).

SCALE. Raw slopes are incomparable across courses with different base
rates, so each slope is divided by the national mean intensity of its
course and scaled to ten percentage points of child poverty: the
relative gradient, in percent of the national mean. Two denominators:
resident children aged 5-17 (the measure of figAlgebraIIPoverty) and
estimated high-school enrollment (CRDC total enrollment of schools
serving grades 9-12, prorated by grade span).

INFERENCE. State-cluster bootstrap on per-state sufficient statistics
(the national mean is re-estimated in every resample), percentile 95%
intervals; the analytic state-clustered standard error of the raw slope
is reported alongside for comparison with figAlgebraIIPoverty.

Analysis uses SQL for cross-referencing and lists / numpy arrays for
computation; no dataframes. Writes vector PDF, 300-DPI PNG, TeX snippet
with the canonical caption, backing CSVs and a stats JSON into
code/figures/paper0.
"""
import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gateway import db  # noqa: E402

FIG_DIR = HERE.parent / "figures" / "paper0"

BLUE, RED, NEUTRAL = "#2a78d6", "#e34948", "#f0efec"
INK, INK_MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"
CMAP = LinearSegmentedColormap.from_list("ratio", [RED, NEUTRAL, BLUE])

CYCLES = ("2015-16", "2017-18", "2021-22")
PRIMARY = "2017-18"
MIN_POP = 200            # denominator filter of figAlgebraIIPoverty
N_BOOT = 5000
SEED = 20261118
Z95 = 1.96               # normal quantile of a 95% interval
NQ = 10                  # child-weighted poverty deciles
FIG_WIDTH = "0.92"       # of \textwidth: the two panels with the caption
                         # fill one page

# key -> display label; the order here is irrelevant (rows are sorted)
SUBJECTS = {
    "alg1_g0708": "Algebra I, grades 7-8",
    "alg1_g0910": "Algebra I, grades 9-10",
    "alg1_g1112": "Algebra I, grades 11-12",
    "geometry": "Geometry",
    "alg2": "Algebra II",
    "adv_math": "Advanced mathematics",
    "calculus": "Calculus",
    "biology": "Biology",
    "chemistry": "Chemistry",
    "physics": "Physics",
    "ap_any": "AP, any course",
    "ap_math": "AP mathematics",
    "ap_science": "AP science",
    "ib": "Intl. Baccalaureate",
    "dual": "Dual enrollment",
}
KEYS = list(SUBJECTS)
REF = "hs_enrollment"    # reference row: high-school enrollment itself
REF_LABEL = "High-school enrollment"
MS_SUBJECTS = ["alg1_g0708"]     # courses taken in grades 7 and 8
HS_CORE = ["alg1_g0910", "alg1_g1112", "geometry", "alg2", "adv_math",
           "calculus", "biology", "chemistry", "physics"]

plt.rcParams.update({"pdf.fonttype": 42, "font.family": "sans-serif",
                     "text.color": INK})

SQL = """
select leaid, state_pc, name, pop_5_17, pov_rate, hs_enr_est, subject,
       enrollees, n_reported, n_missing, ms_enr_est
from mart.course_poverty
where cycle = %s and pop_5_17 >= %s and pov_rate is not null
"""

SQL_BEXAR = """
select leaid
from (select leaid, avg((cnty = '48029')::int) as f
      from raw_xwalk.edge_school where cycle = %s group by leaid) t
where f > 0.5
"""


def load(cycle: str) -> dict:
    """district arrays plus the district x subject enrollee matrix"""
    with db.connect() as cn, cn.cursor() as cur:
        cur.execute(SQL, (cycle, MIN_POP))
        rows = cur.fetchall()
    leas = sorted({r[0] for r in rows})
    ix = {l: i for i, l in enumerate(leas)}
    sx = {s: j for j, s in enumerate(KEYS)}
    n = len(leas)
    d = {"leaid": leas, "state": np.empty(n, dtype=object),
         "name": [""] * n, "pop": np.zeros(n), "pov": np.zeros(n),
         "hs": np.full(n, np.nan), "ms": np.full(n, np.nan),
         "E": np.zeros((n, len(KEYS))),
         "alg2_reported": np.zeros(n, dtype=bool),
         "complete": np.ones(n, dtype=bool)}
    for leaid, st, name, pop, pov, hs, subj, enr, nrep, nmiss, ms in rows:
        i = ix[leaid]
        d["state"][i], d["name"][i] = st, name
        d["pop"][i], d["pov"][i] = float(pop), float(pov)
        if hs is not None:
            d["hs"][i] = float(hs)
        if ms is not None:
            d["ms"][i] = float(ms)
        d["E"][i, sx[subj]] = float(enr)
        if subj == "alg2" and nrep and nrep > 0:
            d["alg2_reported"][i] = True
        if nmiss and nmiss > 0:
            d["complete"][i] = False     # incomplete total in some course
    return d


def _suff(x, w, Y, state):
    """per-state sufficient statistics of the weighted regressions"""
    groups = np.unique(state)
    gi = {g: k for k, g in enumerate(groups)}
    idx = np.array([gi[s] for s in state])
    G = len(groups)
    A = np.bincount(idx, w, G)
    B = np.bincount(idx, w * x, G)
    C = np.bincount(idx, w * x * x, G)
    D = np.zeros((G, Y.shape[1]))
    E = np.zeros((G, Y.shape[1]))
    for j in range(Y.shape[1]):
        D[:, j] = np.bincount(idx, Y[:, j], G)       # sum w*y
        E[:, j] = np.bincount(idx, x * Y[:, j], G)   # sum w*x*y
    return A, B, C, D, E


def _rel(A, B, C, D, E):
    """relative gradient per 10 points, national fit; rows = resamples"""
    slope = (A[:, None] * E - B[:, None] * D) / (A * C - B * B)[:, None]
    mean = D / A[:, None]
    return 10.0 * slope / mean, slope, mean


def _cluster_se(x, y, w, cluster):
    """state-clustered sandwich SE of the WLS slope (figAlgebraIIPoverty)"""
    X = np.column_stack([np.ones(len(x)), x])
    XtWX = X.T @ (w[:, None] * X)
    beta = np.linalg.solve(XtWX, X.T @ (w * y))
    e = y - X @ beta
    groups = np.unique(cluster)
    meat = np.zeros((2, 2))
    for g in groups:
        m = cluster == g
        ug = (w[m, None] * X[m]).T @ e[m]
        meat += np.outer(ug, ug)
    bread = np.linalg.inv(XtWX)
    V = bread @ meat @ bread
    G, N = len(groups), len(x)
    V *= (G / (G - 1)) * ((N - 1) / (N - 2))
    return float(np.sqrt(V[1, 1]))


def gradients(d: dict, frame: np.ndarray, denom: str, rng) -> dict:
    """relative gradients of every course under one frame and denominator

    denom = 'child' (resident children 5-17) or 'hs' (estimated
    high-school enrollment). The reference row (high-school enrollment
    per resident child) is appended under the child denominator.
    """
    m = frame.copy()
    if denom == "hs":
        m &= np.isfinite(d["hs"]) & (d["hs"] > 0)
    w = d["pop"][m] if denom == "child" else d["hs"][m]
    x, st = d["pov"][m], d["state"][m]
    Y = d["E"][m]
    keys = list(KEYS)
    if denom == "child":
        hs = np.where(np.isfinite(d["hs"][m]), d["hs"][m], 0.0)
        Y = np.column_stack([Y, hs])
        keys.append(REF)
    A, B, C, D, E = _suff(x, w, Y, st)
    G = len(A)
    one = np.ones((1, G))
    rel, slope, mean = _rel(one @ A, one @ B, one @ C, one @ D, one @ E)
    rel, slope, mean = rel[0], slope[0], mean[0]
    # state fixed effects: pooled within-state slope over the same mean
    fe = (E - (B / A)[:, None] * D).sum(0) / (C - B * B / A).sum()
    rel_fe = 10.0 * fe / mean
    # bootstrap over states
    cnt = rng.multinomial(G, np.full(G, 1.0 / G), size=N_BOOT).astype(float)
    brel, _, _ = _rel(cnt @ A, cnt @ B, cnt @ C, cnt @ D, cnt @ E)
    lo, hi = np.percentile(brel, [2.5, 97.5], axis=0)
    ja = keys.index("alg2")
    out = {"n_districts": int(m.sum()), "n_states": int(G),
           "denominator_total": float(w.sum()), "subjects": {}}
    for j, k in enumerate(keys):
        se = _cluster_se(x, Y[:, j] / w, w, st)
        diff = brel[:, j] - brel[:, ja]
        out["subjects"][k] = {
            "mean": float(mean[j]), "slope": float(slope[j]),
            "se_cluster": se, "z": float(slope[j] / se),
            "rel10": float(rel[j]), "rel10_lo": float(lo[j]),
            "rel10_hi": float(hi[j]), "rel10_state_fe": float(rel_fe[j]),
            "diff_vs_alg2": float(rel[j] - rel[ja]),
            "diff_vs_alg2_lo": float(np.percentile(diff, 2.5)),
            "diff_vs_alg2_hi": float(np.percentile(diff, 97.5)),
        }
    # rank of Algebra II among the 15 courses (1 = steepest decline)
    ns = len(KEYS)
    rank = 1 + (rel[:ns] < rel[ja]).sum()
    brank = 1 + (brel[:, :ns] < brel[:, [ja]]).sum(1)
    out["alg2_rank"] = int(rank)
    out["alg2_rank_lo"] = int(np.percentile(brank, 2.5))
    out["alg2_rank_hi"] = int(np.percentile(brank, 97.5))
    if denom == "hs":
        # a middle-school course takes a middle-school denominator:
        # estimated enrollment in grades 7 and 8. A separate random
        # stream keeps every other interval unchanged.
        rng2 = np.random.default_rng(SEED + 7)
        mm = frame & np.isfinite(d["ms"]) & (d["ms"] > 0)
        for k in MS_SUBJECTS:
            j = KEYS.index(k)
            xw, ww, stw = d["pov"][mm], d["ms"][mm], d["state"][mm]
            Yk = d["E"][mm][:, [j]]
            A2, B2, C2, D2, E2 = _suff(xw, ww, Yk, stw)
            G2 = len(A2)
            o2 = np.ones((1, G2))
            r2, s2, m2 = _rel(o2 @ A2, o2 @ B2, o2 @ C2, o2 @ D2, o2 @ E2)
            c2 = rng2.multinomial(G2, np.full(G2, 1.0 / G2),
                                  size=N_BOOT).astype(float)
            b2 = _rel(c2 @ A2, c2 @ B2, c2 @ C2, c2 @ D2, c2 @ E2)[0][:, 0]
            se2 = _cluster_se(xw, Yk[:, 0] / ww, ww, stw)
            fe2 = float(((E2 - (B2 / A2)[:, None] * D2).sum(0)
                         / (C2 - B2 * B2 / A2).sum())[0])
            prev = out["subjects"][k]
            out["subjects"][k] = {
                "mean": float(m2[0, 0]), "slope": float(s2[0, 0]),
                "se_cluster": se2, "z": float(s2[0, 0] / se2),
                "rel10": float(r2[0, 0]),
                "rel10_lo": float(np.percentile(b2, 2.5)),
                "rel10_hi": float(np.percentile(b2, 97.5)),
                "rel10_state_fe": 10.0 * fe2 / float(m2[0, 0]),
                "diff_vs_alg2": float("nan"),
                "diff_vs_alg2_lo": float("nan"),
                "diff_vs_alg2_hi": float("nan"),
                "denominator": "estimated enrollment in grades 7-8",
                "n_districts": int(mm.sum()),
                "per_high_school_student": prev}
    # The gradient in seats: how many fewer enrollees per 100 students of
    # the course's grades a district has for ten percentage points more
    # child poverty, with the normal interval of the state-clustered
    # standard error.
    for s in out["subjects"].values():
        s["seats_per_100"] = -10.0 * s["slope"]
        s["seats_lo"] = s["seats_per_100"] - 10.0 * Z95 * s["se_cluster"]
        s["seats_hi"] = s["seats_per_100"] + 10.0 * Z95 * s["se_cluster"]
    return out


def deciles(d: dict, frame: np.ndarray):
    """child-weighted poverty deciles: (ratio matrix, bounds, children)

    ratio[j, q] = pooled enrollees per resident child of course j in
    decile q, over the national pooled value; the last row is the
    reference (estimated high-school enrollment per resident child).
    """
    pop, pov = d["pop"][frame], d["pov"][frame]
    hs = np.where(np.isfinite(d["hs"][frame]), d["hs"][frame], 0.0)
    Y = np.column_stack([d["E"][frame], hs])
    order = np.argsort(pov, kind="stable")
    mid = (np.cumsum(pop[order]) - pop[order] / 2) / pop.sum()
    q = np.empty(len(pop), dtype=int)
    q[order] = np.minimum((mid * NQ).astype(int), NQ - 1)
    nat = Y.sum(0) / pop.sum()
    ratio = np.zeros((Y.shape[1], NQ))
    inten = np.zeros((Y.shape[1], NQ))
    bounds, kids, nd = [], [], []
    for k in range(NQ):
        m = q == k
        inten[:, k] = Y[m].sum(0) / pop[m].sum()
        ratio[:, k] = inten[:, k] / nat
        bounds.append((float(pov[m].min()), float(pov[m].max())))
        kids.append(float(pop[m].sum()))
        nd.append(int(m.sum()))
    return ratio, inten, nat, bounds, kids, nd


def deciles_student(d: dict, frame: np.ndarray):
    """tenths of high-school students ordered by district child poverty

    ratio[j, q] = pooled enrollees of course j per student in the
    course's grades in tenth q, over the national pooled value. The
    denominator is estimated high-school enrollment, or estimated
    enrollment in grades 7 and 8 for a middle-school course. Each tenth
    holds a tenth of the frame's estimated high-school enrollment.
    """
    m = frame & np.isfinite(d["hs"]) & (d["hs"] > 0)
    hs, pov, Y = d["hs"][m], d["pov"][m], d["E"][m]
    ms = np.where(np.isfinite(d["ms"][m]), d["ms"][m], 0.0)
    order = np.argsort(pov, kind="stable")
    mid = (np.cumsum(hs[order]) - hs[order] / 2) / hs.sum()
    q = np.empty(len(hs), dtype=int)
    q[order] = np.minimum((mid * NQ).astype(int), NQ - 1)
    den = np.tile(hs[:, None], (1, Y.shape[1]))
    for k in MS_SUBJECTS:
        den[:, KEYS.index(k)] = ms
    Yd = np.where(den > 0, Y, 0.0)     # no grades of the course, no count
    nat = Yd.sum(0) / den.sum(0)
    ratio = np.zeros((Y.shape[1], NQ))
    inten = np.zeros((Y.shape[1], NQ))
    bounds, studs, nd = [], [], []
    for k in range(NQ):
        b = q == k
        inten[:, k] = Yd[b].sum(0) / den[b].sum(0)
        ratio[:, k] = inten[:, k] / nat
        bounds.append((float(pov[b].min()), float(pov[b].max())))
        studs.append(float(hs[b].sum()))
        nd.append(int(b.sum()))
    return ratio, inten, nat, bounds, studs, nd


def texas(d: dict, frame: np.ndarray) -> dict:
    """within-Texas relative gradients, heteroskedasticity-robust z"""
    out = {}

    def fit(m, w, j):
        """weighted fit of course j per unit of the denominator w"""
        x = d["pov"][m]
        X = np.column_stack([np.ones(len(x)), x])
        bread = np.linalg.inv(X.T @ (w[:, None] * X))
        y = d["E"][m, j] / w
        beta = bread @ (X.T @ (w * y))
        e = y - X @ beta
        meat = (X * (w * e)[:, None]).T @ (X * (w * e)[:, None])
        V = bread @ meat @ bread * len(x) / (len(x) - 2)
        mean = d["E"][m, j].sum() / w.sum()
        return {"mean": float(mean), "slope": float(beta[1]),
                "rel10": float(10 * beta[1] / mean),
                "z_hc1": float(beta[1] / np.sqrt(V[1, 1]))}

    for denom in ("child", "hs"):
        m = frame & (d["state"] == "TX")
        if denom == "hs":
            m &= np.isfinite(d["hs"]) & (d["hs"] > 0)
        w = d["pop"][m] if denom == "child" else d["hs"][m]
        res = {"n_districts": int(m.sum()), "subjects": {}}
        for j, k in enumerate(KEYS):
            res["subjects"][k] = fit(m, w, j)
        if denom == "hs":
            # a middle-school course takes a middle-school denominator, as
            # in gradients(): estimated enrollment in grades 7 and 8
            mm = (frame & (d["state"] == "TX") & np.isfinite(d["ms"])
                  & (d["ms"] > 0))
            for k in MS_SUBJECTS:
                prev = res["subjects"][k]
                res["subjects"][k] = dict(
                    fit(mm, d["ms"][mm], KEYS.index(k)),
                    denominator="estimated enrollment in grades 7-8",
                    n_districts=int(mm.sum()),
                    per_high_school_student=prev)
        out[denom] = res
    return out


SQL_PURE_ENR = """
select a.leaid, sum(a.enr_total), count(*)
from stg.crdc_course_school_attr a
where a.cycle = %s and a.n_k12 = 4 and a.n_hs = 4 and a.enr_total > 0
group by a.leaid
"""
SQL_PURE_CRS = """
select a.leaid, c.subject, coalesce(sum(c.enr), 0)
from stg.crdc_course_school_attr a
join stg.crdc_course_school c
  on c.cycle = a.cycle and c.combokey = a.combokey
where a.cycle = %s and a.n_k12 = 4 and a.n_hs = 4 and a.enr_total > 0
group by a.leaid, c.subject
"""


def grade_9_12_check(d: dict, frame: np.ndarray, cycle: str, rng) -> dict:
    """denominator check on ordinary high schools only

    Uses schools whose grade span is exactly 9-12, so the denominator is
    their actual enrollment and no grade-span proration is involved.
    Numerators and denominators both come from those schools.
    """
    with db.connect() as cn, cn.cursor() as cur:
        cur.execute(SQL_PURE_ENR, (cycle,))
        enr = {r[0]: (float(r[1]), int(r[2])) for r in cur.fetchall()}
        cur.execute(SQL_PURE_CRS, (cycle,))
        crs = {}
        for leaid, subj, e in cur.fetchall():
            crs.setdefault(leaid, {})[subj] = float(e)
    idx = [i for i in np.flatnonzero(frame) if d["leaid"][i] in enr]
    x = d["pov"][idx]
    st = d["state"][idx]
    w = np.array([enr[d["leaid"][i]][0] for i in idx])
    Y = np.array([[crs.get(d["leaid"][i], {}).get(k, 0.0) for k in KEYS]
                  for i in idx])
    A, B, C, D, E = _suff(x, w, Y, st)
    G = len(A)
    one = np.ones((1, G))
    rel = _rel(one @ A, one @ B, one @ C, one @ D, one @ E)[0][0]
    cnt = rng.multinomial(G, np.full(G, 1.0 / G), size=N_BOOT).astype(float)
    brel = _rel(cnt @ A, cnt @ B, cnt @ C, cnt @ D, cnt @ E)[0]
    lo, hi = np.percentile(brel, [2.5, 97.5], axis=0)
    return {"n_districts": len(idx),
            "n_schools": int(sum(enr[d["leaid"][i]][1] for i in idx)),
            "students": float(w.sum()),
            "subjects": {k: {"rel10": float(rel[j]), "rel10_lo": float(lo[j]),
                             "rel10_hi": float(hi[j])}
                         for j, k in enumerate(KEYS)}}


def _short(name: str) -> str:
    return (name.replace("Independent School District", "ISD")
                .replace("School District", "SD").strip())


MIN_SHARE = 0.10         # county panel: least share of students in a group
X_RANGE = (-82, 72)      # gradient axis shared by the two panels; wide
                         # enough for the intervals of fifteen districts


def county_profile(d: dict, frame: np.ndarray, leaids: set,
                   nat: np.ndarray, rng) -> dict:
    """the national profile and gradient repeated for one county

    Rates are enrollees of a course per student in the course's grades
    (the denominators of deciles_student), divided by the national
    pooled value `nat`, so 1.00 is the national rate in both panels.

    GROUPS. A county holds too few districts for tenths: districts are
    taken in order of child poverty and merged until a group holds at
    least MIN_SHARE of the county's estimated high-school enrollment;
    a short tail joins the last group.

    GRADIENT. The enrollment-weighted slope of the rate on child poverty
    over the county's districts, divided by the national mean and scaled
    to ten percentage points. Intervals are percentile intervals from a
    bootstrap that resamples the districts (the level at which child
    poverty varies), on per-district sufficient statistics.
    """
    m = frame & np.isfinite(d["hs"]) & (d["hs"] > 0)
    idx = [int(i) for i in np.argsort(d["pov"], kind="stable")
           if m[i] and d["leaid"][i] in leaids]
    hs, pov, Y = d["hs"][idx], d["pov"][idx], d["E"][idx]
    ms = np.where(np.isfinite(d["ms"][idx]), d["ms"][idx], 0.0)
    den = np.tile(hs[:, None], (1, Y.shape[1]))
    for k in MS_SUBJECTS:
        den[:, KEYS.index(k)] = ms
    Yd = np.where(den > 0, Y, 0.0)
    rate = np.where(den > 0, Yd / np.where(den > 0, den, 1.0), np.nan)

    members, cur, acc = [], [], 0.0
    for c in range(len(idx)):
        cur.append(c)
        acc += hs[c]
        if acc >= MIN_SHARE * hs.sum():
            members.append(cur)
            cur, acc = [], 0.0
    if cur:
        if members:
            members[-1].extend(cur)
        else:
            members.append(cur)
    groups = [{"members": g, "n_districts": len(g),
               "pov_lo": float(pov[g].min()), "pov_hi": float(pov[g].max()),
               "hs_students": float(hs[g].sum()),
               "ratio": Yd[g].sum(0) / den[g].sum(0) / nat}
              for g in members]

    # weighted slopes from per-district sufficient statistics
    n = len(idx)
    cnt = rng.multinomial(n, np.full(n, 1.0 / n), size=N_BOOT).astype(float)
    one = np.ones((1, n))
    J = Y.shape[1]
    slope, lo, hi = np.zeros(J), np.zeros(J), np.zeros(J)
    for j in range(J):
        w = den[:, j]
        S = np.column_stack([w, w * pov, w * pov * pov, Yd[:, j],
                             pov * Yd[:, j]])       # sums of w, wx, wxx, wy, wxy

        def fit(c):
            A, B, C, D, E = (c @ S).T
            with np.errstate(divide="ignore", invalid="ignore"):
                return (A * E - B * D) / (A * C - B * B)

        slope[j] = fit(one)[0]
        b = fit(cnt)
        lo[j], hi[j] = np.nanpercentile(b[np.isfinite(b)], [2.5, 97.5])
    return {"idx": idx, "pov": pov, "hs": hs, "ms": ms,
            "ratio": (rate / nat).T, "groups": groups,
            "county_ratio": Yd.sum(0) / den.sum(0) / nat,
            "slope": slope, "rel10": 10.0 * slope / nat,
            "rel10_lo": 10.0 * lo / nat, "rel10_hi": 10.0 * hi / nat}


def figure() -> str:
    rng = np.random.default_rng(SEED)
    stats = {"primary_cycle": PRIMARY, "min_pop": MIN_POP,
             "n_boot": N_BOOT, "seed": SEED, "cycles": {}}
    data = {}
    for cycle in CYCLES:
        d = load(cycle)
        data[cycle] = d
        f0 = d["alg2_reported"]
        f1 = f0 & d["complete"]
        hs_cols = [KEYS.index(k) for k in HS_CORE]
        f2 = (d["E"][:, hs_cols].sum(1) > 0) & d["complete"]
        stats["cycles"][cycle] = {
            "figure5_frame": {den: gradients(d, f1, den, rng)
                              for den in ("child", "hs")},
            "neutral_frame": {den: gradients(d, f2, den, rng)
                              for den in ("child", "hs")},
            "incomplete_kept": {den: gradients(d, f0, den, rng)
                                for den in ("child", "hs")},
            "n_incomplete_excluded": int((f0 & ~d["complete"]).sum()),
        }
    d = data[PRIMARY]
    frame = d["alg2_reported"] & d["complete"]
    n_excl = stats["cycles"][PRIMARY]["n_incomplete_excluded"]
    gc = stats["cycles"][PRIMARY]["figure5_frame"]["child"]
    gh = stats["cycles"][PRIMARY]["figure5_frame"]["hs"]
    stats["texas_" + PRIMARY] = texas(d, frame)
    stats["grade_9_12_schools_" + PRIMARY] = grade_9_12_check(
        d, frame, PRIMARY, rng)
    ratio, inten, nat, bounds, studs, nd = deciles_student(d, frame)

    # row order: steepest decline per student in the course's grades at
    # the top. Every count in the figure is divided by the students who
    # can take the course; the per-resident-child estimates stay in the
    # statistics file and the gradient table only.
    order = sorted(KEYS, key=lambda k: gh["subjects"][k]["rel10"])
    rows = list(order)
    ridx = [KEYS.index(k) for k in order]
    M = ratio[ridx]
    ypos = np.arange(len(rows), dtype=float)

    # panel B: the display of panel A repeated for the school districts
    # of Bexar County (San Antonio). A separate random stream keeps the
    # national intervals unchanged.
    with db.connect() as cn, cn.cursor() as cur:
        cur.execute(SQL_BEXAR, (PRIMARY,))
        bexar = {r[0] for r in cur.fetchall()}
    bp = county_profile(d, frame, bexar, nat,
                        np.random.default_rng(SEED + 11))
    MB = np.column_stack([g_["ratio"][ridx] for g_ in bp["groups"]])
    NG = len(bp["groups"])

    VMAX = np.log2(2.4)
    norm = Normalize(-VMAX, VMAX)
    # two stacked panels of identical geometry (row height in inches)
    WIDTH, ROW = 15.5, 0.33
    TOP, MID, BOT = 1.40, 2.75, 1.80
    PH = len(rows) * ROW
    HEIGHT = TOP + PH + MID + PH + BOT
    fig = plt.figure(figsize=(WIDTH, HEIGHT))
    L, W1, GAPF, W2 = 0.215, 0.4586, 0.012, 0.2293
    y_a = 1 - (TOP + PH) / HEIGHT
    y_b = BOT / HEIGHT
    ax = fig.add_axes([L, y_a, W1, PH / HEIGHT])
    af = fig.add_axes([L + W1 + GAPF, y_a, W2, PH / HEIGHT])
    ab = fig.add_axes([L, y_b, W1, PH / HEIGHT])
    abf = fig.add_axes([L + W1 + GAPF, y_b, W2, PH / HEIGHT])

    XLO, XHI = X_RANGE

    def heat(a_, mat, labels, xlabel):
        """profile: one cell per course and poverty group"""
        for i in range(mat.shape[0]):
            for k in range(mat.shape[1]):
                v = float(mat[i, k])
                if not v > 0:
                    # no enrollment reported: kept apart from the scale
                    a_.add_patch(plt.Rectangle(
                        (k + 0.02, ypos[i] - 0.48), 0.96, 0.96,
                        facecolor="white", edgecolor=GRID, linewidth=0.9))
                    a_.text(k + 0.5, ypos[i], "0", ha="center",
                            va="center", fontsize=15, color=INK_MUTED)
                    continue
                lv = float(np.clip(np.log2(v), -VMAX, VMAX))
                a_.add_patch(plt.Rectangle(
                    (k + 0.02, ypos[i] - 0.48), 0.96, 0.96,
                    facecolor=CMAP(norm(lv)), edgecolor="none"))
                a_.text(k + 0.5, ypos[i], f"{v:.2f}", ha="center",
                        va="center", fontsize=15,
                        color="white" if abs(lv) > 0.62 * VMAX else INK)
        a_.set_xlim(0, mat.shape[1])
        a_.set_ylim(ypos[-1] + 0.5, -0.5)
        a_.set_xticks(np.arange(mat.shape[1]) + 0.5)
        a_.set_xticklabels(labels, rotation=45, ha="right",
                           rotation_mode="anchor", fontsize=15.5, color=INK)
        a_.set_yticks(ypos)
        a_.set_yticklabels([SUBJECTS[k] for k in rows], fontsize=17.5,
                           color=INK)
        a_.tick_params(length=0)
        for sp in a_.spines.values():
            sp.set_visible(False)
        a_.set_xlabel(xlabel, fontsize=17.5, labelpad=8)

    def forest(a_, est, lo, hi, slopes):
        """relative gradient per student in the course's grades, and the
        same gradient in seats: enrollees per 100 students in the
        course's grades per ten points of child poverty. The relative
        scale divides by each course's own mean, so a course with a
        small base can look steep while involving few students."""
        for i in range(len(rows)):
            a_.plot([max(lo[i], XLO), min(hi[i], XHI)], [ypos[i]] * 2,
                    color=INK, lw=1.8, zorder=3, solid_capstyle="round")
            # an interval that runs past the axis ends in an arrowhead
            if lo[i] < XLO:
                a_.plot(XLO + 1.2, ypos[i], marker="<", ms=8, color=INK,
                        mec="none", zorder=4)
            if hi[i] > XHI:
                a_.plot(XHI - 1.2, ypos[i], marker=">", ms=8, color=INK,
                        mec="none", zorder=4)
            if XLO <= est[i] <= XHI:
                a_.plot(est[i], ypos[i], "o", ms=10, color=INK, mec="white",
                        mew=1.0, zorder=4)
        a_.axvline(0, color=INK_MUTED, lw=1.0, zorder=1)
        tr = a_.get_yaxis_transform()
        for i in range(len(rows)):
            a_.text(1.19, ypos[i],
                    f"{10.0 * slopes[i]:+.1f}".replace("-", "\u2212"),
                    transform=tr, ha="right", va="center", fontsize=15.5,
                    color=INK, clip_on=False)
        a_.text(1.19, -0.62, "seats per\n100 students", transform=tr,
                ha="right", va="bottom", fontsize=13.5, color=INK_MUTED,
                linespacing=1.05, clip_on=False)
        a_.set_ylim(ypos[-1] + 0.5, -0.5)
        a_.set_yticks([])
        a_.set_xlim(XLO, XHI)
        a_.set_xticks([-60, -30, 0, 30, 60])
        a_.tick_params(labelsize=15.5, color=INK_MUTED)
        a_.grid(axis="x", color=GRID, linewidth=0.6, zorder=0)
        a_.set_axisbelow(True)
        for side in ("top", "right", "left"):
            a_.spines[side].set_visible(False)
        a_.spines["bottom"].set_color(INK_MUTED)
        a_.set_xlabel("change per 10 points of child\n"
                      "poverty (% of national mean)", fontsize=17.5,
                      labelpad=8)

    # panel A: the United States
    heat(ax, M, [f"{100 * a:.1f}-{100 * b:.1f}" for a, b in bounds],
         "district child poverty rate (%), tenths of high-school students")
    forest(af, [gh["subjects"][k]["rel10"] for k in rows],
           [gh["subjects"][k]["rel10_lo"] for k in rows],
           [gh["subjects"][k]["rel10_hi"] for k in rows],
           [gh["subjects"][k]["slope"] for k in rows])
    cax = fig.add_axes([0.325, 1 - 0.62 / HEIGHT, 0.30, 0.165 / HEIGHT])
    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=CMAP), cax=cax,
                      orientation="horizontal")
    ticks = [0.5, 0.67, 1.0, 1.5, 2.0]
    cb.set_ticks([np.log2(t) for t in ticks])
    cb.set_ticklabels([f"{t:g}" for t in ticks])
    cb.ax.tick_params(labelsize=15, color=INK_MUTED, length=3)
    cb.outline.set_visible(False)
    cax.set_title("enrollees per student in the course's grades, ratio "
                  "to the national mean of the course", fontsize=16,
                  color=INK, pad=7)

    # panel B: the same display for Bexar County
    nb = len(bp["idx"])
    heat(ab, MB,
         [f"{100 * g_['pov_lo']:.1f}" if g_["n_districts"] == 1 else
          f"{100 * g_['pov_lo']:.1f}-{100 * g_['pov_hi']:.1f}"
          for g_ in bp["groups"]],
         "district child poverty rate (%), groups of\n"
         "the county's high-school students")
    forest(abf, bp["rel10"][ridx], bp["rel10_lo"][ridx],
           bp["rel10_hi"][ridx], bp["slope"][ridx])
    # above the columns: the districts and the students in each group
    y_n = -0.5 - 0.52 / ROW
    y_size = -0.5 - 0.20 / ROW
    for c, g_ in enumerate(bp["groups"]):
        ab.text(c + 0.5, y_n, f"{g_['n_districts']}", ha="center",
                va="center", fontsize=14.5, color=INK, clip_on=False)
        ab.text(c + 0.5, y_size, f"{g_['hs_students'] / 1000:.1f}",
                ha="center", va="center", fontsize=14.5, color=INK,
                clip_on=False)
    ab.text(-0.06, y_n, "districts in the group", ha="right", va="center",
            fontsize=13.5, color=INK, clip_on=False)
    ab.text(-0.06, y_size, "high-school students (thousands)", ha="right",
            va="center", fontsize=13.5, color=INK, clip_on=False)

    # panel titles
    for letter, text, y in (
            ("A", f"United States: {gc['n_districts']:,} school districts",
             1 - (TOP - 0.30) / HEIGHT),
            ("B", f"Bexar County, Texas (San Antonio): {nb} school "
                  "districts",
             y_b + (PH + 0.98) / HEIGHT)):
        fig.text(0.012, y, letter, fontsize=23, fontweight="bold",
                 color=INK, va="center", ha="left")
        fig.text(0.040, y, text, fontsize=18.5, color=INK, va="center",
                 ha="left")

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    pdf = FIG_DIR / "figCourseGradients.pdf"
    fig.savefig(pdf)
    fig.savefig(FIG_DIR / "figCourseGradients.png", dpi=300)
    plt.close(fig)

    # backing data: decile profile (long) and the gradient table
    with open(FIG_DIR / "figCourseGradients_data.csv", "w", newline="",
              encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["cycle", "subject", "label", "tenth", "pov_lo",
                      "pov_hi", "n_districts", "hs_students_in_tenth",
                      "enrollees_per_student_in_course_grades",
                      "ratio_to_national"])
        for i, k in zip(ridx, rows):
            for q in range(NQ):
                out.writerow([PRIMARY, k, SUBJECTS[k], q + 1,
                              f"{bounds[q][0]:.4f}", f"{bounds[q][1]:.4f}",
                              nd[q], int(studs[q]), f"{inten[i, q]:.6f}",
                              f"{ratio[i, q]:.4f}"])
    with open(FIG_DIR / "figCourseGradients_gradients.csv", "w", newline="",
              encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["cycle", "frame", "denominator", "subject", "label",
                      "n_districts", "national_mean", "slope",
                      "se_state_cluster", "z", "rel10_pct", "rel10_lo",
                      "rel10_hi", "rel10_state_fe", "diff_vs_alg2",
                      "diff_vs_alg2_lo", "diff_vs_alg2_hi"])
        for cycle in CYCLES:
            for fr, byden in stats["cycles"][cycle].items():
                if not isinstance(byden, dict):
                    continue
                for den, g in byden.items():
                    for k, s in g["subjects"].items():
                        out.writerow(
                            [cycle, fr, den, k, SUBJECTS.get(k, REF_LABEL),
                             g["n_districts"], f"{s['mean']:.6f}",
                             f"{s['slope']:.6f}", f"{s['se_cluster']:.6f}",
                             f"{s['z']:.3f}", f"{s['rel10']:.2f}",
                             f"{s['rel10_lo']:.2f}", f"{s['rel10_hi']:.2f}",
                             f"{s['rel10_state_fe']:.2f}",
                             f"{s['diff_vs_alg2']:.2f}",
                             f"{s['diff_vs_alg2_lo']:.2f}",
                             f"{s['diff_vs_alg2_hi']:.2f}"])

    # Bexar County (panel B): one row per district, then the groups of
    # the panel and the county. Every ratio is enrollees per student in
    # the course's grades over the national value of the course.
    okh = frame & np.isfinite(d["hs"]) & (d["hs"] > 0)
    kx = [KEYS.index(k) for k in order]
    dname = [_short(d["name"][i]) for i in bp["idx"]]
    gof = {c: g for g, g_ in enumerate(bp["groups"]) for c in g_["members"]}
    with open(FIG_DIR / "figCourseGradients_bexar.csv", "w", newline="",
              encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["cycle", "row", "group", "leaid", "district",
                      "n_districts", "pov_rate_lo", "pov_rate_hi",
                      "children_5_17", "hs_enrollment_est",
                      "g7_8_enrollment_est"]
                     + [f"{k}_ratio_to_national" for k in order])
        for c, i in enumerate(bp["idx"]):
            out.writerow([PRIMARY, "district", gof[c] + 1, d["leaid"][i],
                          dname[c], 1, f"{d['pov'][i]:.4f}",
                          f"{d['pov'][i]:.4f}", int(d["pop"][i]),
                          int(round(bp["hs"][c])), int(round(bp["ms"][c]))]
                         + [f"{bp['ratio'][j, c]:.3f}" for j in kx])
        for g, g_ in enumerate(bp["groups"]):
            out.writerow([PRIMARY, "group", g + 1, "",
                          "; ".join(dname[c] for c in g_["members"]),
                          g_["n_districts"], f"{g_['pov_lo']:.4f}",
                          f"{g_['pov_hi']:.4f}", "",
                          int(round(g_["hs_students"])), ""]
                         + [f"{g_['ratio'][j]:.3f}" for j in kx])
        out.writerow([PRIMARY, "county", "", "", "Bexar County, all districts",
                      nb, f"{bp['pov'].min():.4f}", f"{bp['pov'].max():.4f}",
                      "", int(round(bp["hs"].sum())),
                      int(round(bp["ms"].sum()))]
                     + [f"{bp['county_ratio'][j]:.3f}" for j in kx])
    # the gradient within the county beside the national gradient
    with open(FIG_DIR / "figCourseGradients_bexar_slopes.csv", "w",
              newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["cycle", "subject", "label", "national_rel10_pct",
                      "national_lo", "national_hi", "national_seats_per_100",
                      "bexar_rel10_pct", "bexar_lo", "bexar_hi",
                      "bexar_seats_per_100", "ratio_county"])
        for k, j in zip(order, kx):
            h = gh["subjects"][k]
            out.writerow([PRIMARY, k, SUBJECTS[k], f"{h['rel10']:.2f}",
                          f"{h['rel10_lo']:.2f}", f"{h['rel10_hi']:.2f}",
                          f"{10 * h['slope']:.2f}", f"{bp['rel10'][j]:.2f}",
                          f"{bp['rel10_lo'][j]:.2f}",
                          f"{bp['rel10_hi'][j]:.2f}",
                          f"{10 * bp['slope'][j]:.2f}",
                          f"{bp['county_ratio'][j]:.3f}"])
    stats["bexar_" + PRIMARY] = {
        "denominator": "students in the course's grades",
        "n_districts": nb, "districts": dname,
        "pov": [float(v) for v in bp["pov"]],
        "hs_students": [float(v) for v in bp["hs"]],
        "min_share_of_students_per_group": MIN_SHARE,
        "groups": [{"districts": [dname[c] for c in g_["members"]],
                    "n_districts": g_["n_districts"],
                    "pov_lo": g_["pov_lo"], "pov_hi": g_["pov_hi"],
                    "hs_students": g_["hs_students"],
                    "ratio": {k: float(g_["ratio"][j])
                              for k, j in zip(order, kx)}}
                   for g_ in bp["groups"]],
        "county_ratio": {k: float(bp["county_ratio"][j])
                         for k, j in zip(order, kx)},
        "rel10": {k: {"rel10": float(bp["rel10"][j]),
                      "rel10_lo": float(bp["rel10_lo"][j]),
                      "rel10_hi": float(bp["rel10_hi"][j]),
                      "seats_per_100": float(10 * bp["slope"][j])}
                  for k, j in zip(order, kx)},
        "ratio": {k: [float(v) for v in bp["ratio"][j]]
                  for k, j in zip(order, kx)},
        "note": "slope over the county's districts, relative to the "
                "national mean; percentile intervals from a bootstrap "
                f"that resamples districts ({N_BOOT} resamples)"}

    # district income (the covariate of figAlgebraIIOA) against intensity
    inc_csv = FIG_DIR / "figAlgebraIIOA_data.csv"
    if inc_csv.exists():
        inc = {}
        with open(inc_csv, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                inc[r["leaid"]] = float(r["med_hhinc2016_k"])
        m = np.array([l in inc for l in d["leaid"]]) & okh
        x = np.array([inc.get(l, np.nan) for l in d["leaid"]])[m]
        w = d["pop"][m]

        def wcorr(y):
            mx, my = np.average(x, weights=w), np.average(y, weights=w)
            return float((w * (x - mx) * (y - my)).sum() / np.sqrt(
                (w * (x - mx) ** 2).sum() * (w * (y - my) ** 2).sum()))

        def spear(y):
            rx = np.argsort(np.argsort(x)).astype(float)
            ry = np.argsort(np.argsort(y)).astype(float)
            return float(np.corrcoef(rx, ry)[0, 1])

        rows_inc = [("hs_enrollment", "per resident child",
                     wcorr(d["hs"][m] / d["pop"][m]),
                     spear(d["hs"][m] / d["pop"][m]))]
        for k in KEYS:
            j = KEYS.index(k)
            rows_inc.append((k, "per resident child",
                             wcorr(d["E"][m, j] / d["pop"][m]),
                             spear(d["E"][m, j] / d["pop"][m])))
            rows_inc.append((k, "per high-school student",
                             wcorr(d["E"][m, j] / d["hs"][m]),
                             spear(d["E"][m, j] / d["hs"][m])))
        with open(FIG_DIR / "figCourseGradients_income.csv", "w",
                  newline="", encoding="utf-8") as f:
            out = csv.writer(f)
            out.writerow(["subject", "denominator", "n_districts",
                          "weighted_pearson", "spearman"])
            for k, den, a, b in rows_inc:
                out.writerow([k, den, int(m.sum()), f"{a:.4f}", f"{b:.4f}"])
        stats["income_association_" + PRIMARY] = {
            f"{k}|{den}": {"weighted_pearson": a, "spearman": b,
                           "n_districts": int(m.sum())}
            for k, den, a, b in rows_inc}

    stats["deciles_" + PRIMARY] = {
        "denominator": "students in the course's grades",
        "bounds": bounds, "hs_students": studs, "n_districts": nd,
        "rows": rows, "ratio": [[float(v) for v in r] for r in M]}
    (FIG_DIR / "figCourseGradients_stats.json").write_text(
        json.dumps(stats, indent=1), encoding="utf-8")

    a = gc["subjects"]["alg2"]

    past = int(((bp["rel10_lo"] < X_RANGE[0]) | (bp["rel10_hi"] > X_RANGE[1])).sum())
    (FIG_DIR / "figCourseGradients.tex").write_text(
        "% Canonical caption for figCourseGradients.pdf\n"
        "% Generated by: code/paper0/course_gradient_figure.py from\n"
        "% mart.course_poverty (GATEWAY; code/ingest/crdc_courses.py).\n"
        "% Regenerate: python code/paper0/course_gradient_figure.py\n"
        "\\begin{figure}[tbp]\n"
        "  \\centering\n"
        f"  \\includegraphics[width={FIG_WIDTH}\\textwidth]"
        "{figCourseGradients.pdf}\n"
        "  \\caption{Course enrollment and district child poverty, by\n"
        "    course family (CRDC 2017--18; SAIPE 2017). Each count is\n"
        "    divided by estimated enrollment in the grades of the course\n"
        "    (grades 9--12, or grades 7 and 8 for Algebra~I in grades\n"
        "    7--8), and each cell is the ratio of that rate to the\n"
        "    national rate of the same course (1.00 is the national rate;\n"
        "    blue above, red below; logarithmic color scale). (A) United\n"
        f"    States, the {gc['n_districts']:,} districts of\n"
        "    Figure~\\ref{figCalculusPanels}. Left: tenths of high-school\n"
        "    students ordered by district child poverty. Right: the\n"
        "    weighted least-squares slope of the rate on child poverty,\n"
        "    in percent of the national mean per ten percentage points of\n"
        "    child poverty, with 95\\% intervals from a state-cluster\n"
        f"    bootstrap ({N_BOOT:,} resamples); the numbers at the right\n"
        "    restate each slope in enrollees per 100 students. Rows are\n"
        "    ordered by this gradient in both panels. (B) The same\n"
        f"    display for the {nb} school districts of Bexar County,\n"
        "    Texas. The districts are ordered by child poverty and merged\n"
        f"    into {NG} groups that each hold at least a tenth of the\n"
        "    county's high-school students.\n"
        f"    The slope is computed over the {nb} districts, with 95\\%\n"
        "    intervals from a bootstrap that resamples districts"
        + (f"; an\n    arrowhead marks {past} interval"
           f"{'s' if past != 1 else ''} that run"
           f"{'' if past != 1 else 's'} past the axis" if past else "")
        + ". A\n"
        "    cell marked 0 reports no enrollment. Districts are the\n"
        "    units; enrollment counts seats within one cycle, with no\n"
        "    completion or outcome content.}\n"
        "  \\label{figCourseGradients}\n"
        "\\end{figure}\n",
        encoding="utf-8")

    print(f"{PRIMARY}: n={gc['n_districts']:,} districts, "
          f"{gc['n_states']} state clusters; Algebra II slope "
          f"{a['slope']:.4f} (SE {a['se_cluster']:.4f}; figure 5: "
          f"-0.0524, 0.0136)")
    print(f"{'course':28s} {'per child':>22s}   {'per HS student':>22s}"
          f"   {'state FE':>8s}")
    for k in rows + [REF]:
        c = gc["subjects"][k]
        line = (f"{SUBJECTS.get(k, REF_LABEL):28s} {c['rel10']:+6.1f} "
                f"[{c['rel10_lo']:+6.1f},{c['rel10_hi']:+6.1f}]")
        if k != REF:
            h = gh["subjects"][k]
            line += (f"   {h['rel10']:+6.1f} [{h['rel10_lo']:+6.1f},"
                     f"{h['rel10_hi']:+6.1f}]   {c['rel10_state_fe']:+6.1f}")
        print(line)
    for cycle in CYCLES:
        for fr in ("figure5_frame", "neutral_frame", "incomplete_kept"):
            g = stats["cycles"][cycle][fr]
            print(f"{cycle} {fr:14s} Algebra II rank per child "
                  f"{g['child']['alg2_rank']} "
                  f"[{g['child']['alg2_rank_lo']},"
                  f"{g['child']['alg2_rank_hi']}] of {len(KEYS)}; "
                  f"per HS student rel10 "
                  f"{g['hs']['subjects']['alg2']['rel10']:+.1f}")
    return str(pdf)


if __name__ == "__main__":
    print(" ", figure())
