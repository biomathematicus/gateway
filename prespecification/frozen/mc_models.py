"""Module C estimators (analysis_plan.md, Sections 6 and 7).

numpy / scipy implementations: cluster-robust least squares with an
absorbed fixed effect, a nested random-intercept model fitted by REML on
per-school sufficient statistics, a fixed-effects logit check, the
Benjamini-Hochberg procedure, and DerSimonian-Laird pooling.
"""
import numpy as np
from scipy import optimize, sparse, stats


def group_index(labels):
    """integer codes and number of groups for an array of labels"""
    _, codes = np.unique(np.asarray(labels), return_inverse=True)
    return codes, int(codes.max()) + 1 if len(codes) else 0


def demean(M, g, ng):
    """subtract group means from every column of M (or from a vector)"""
    cnt = np.bincount(g, minlength=ng)
    if M.ndim == 1:
        return M - (np.bincount(g, M, ng) / cnt)[g]
    out = np.empty_like(M, dtype=float)
    for j in range(M.shape[1]):
        out[:, j] = M[:, j] - (np.bincount(g, M[:, j], ng) / cnt)[g]
    return out


def keep_columns(X, tol=1e-10):
    """indices of columns that are non-constant and not collinear"""
    sd = X.std(0)
    cand = np.flatnonzero(sd > tol)
    if not len(cand):
        return cand
    Z = (X[:, cand] - X[:, cand].mean(0)) / sd[cand]
    # greedy rank check through pivoted QR on the Gram matrix
    G = Z.T @ Z / len(Z)
    keep = []
    for j in range(len(cand)):
        trial = keep + [j]
        sub = G[np.ix_(trial, trial)]
        if np.linalg.eigvalsh(sub)[0] > 1e-8:
            keep.append(j)
    return cand[keep]


def _cluster_sums(U, codes, G):
    order = np.argsort(codes, kind="stable")
    cs = codes[order]
    starts = np.flatnonzero(np.diff(cs, prepend=-1))
    return np.add.reduceat(U[order], starts, axis=0)


def ols_cluster(X, y, cluster, w=None, absorbed=0):
    """least squares with cluster-robust covariance (CR1)

    `absorbed` is the number of fixed effects removed beforehand by
    demeaning; it enters the small-sample factor.
    """
    n, k = X.shape
    if w is not None:
        r = np.sqrt(w)
        X, y = X * r[:, None], y * r
    XtX = X.T @ X
    bread = np.linalg.pinv(XtX)
    beta = bread @ (X.T @ y)
    e = y - X @ beta
    codes, G = group_index(cluster)
    S = _cluster_sums(X * e[:, None], codes, G)
    V = bread @ (S.T @ S) @ bread
    V *= (G / (G - 1)) * ((n - 1) / max(n - k - absorbed, 1))
    tss = ((y - y.mean()) ** 2).sum()
    return {"beta": beta, "V": V, "n": n, "G": G,
            "r2": 1 - (e @ e) / tss if tss > 0 else np.nan}


def nested_reml(X, y, school, district):
    """random intercepts for district and school within district (REML)

    The marginal covariance within a district is
    sigma_e^2 I + sigma_s^2 (school blocks) + sigma_d^2 (all ones), whose
    inverse and determinant follow from per-school sums, so the
    criterion is evaluated without forming any n-by-n matrix.
    """
    n, p = X.shape
    sc, J = group_index(school)
    dc, K = group_index(district)
    sd = np.zeros(J, dtype=int)
    sd[sc] = dc                                  # district of each school
    nj = np.bincount(sc, minlength=J).astype(float)
    SX = np.column_stack([np.bincount(sc, X[:, c], J) for c in range(p)])
    sy = np.bincount(sc, y, J)
    XtX, Xty, yty = X.T @ X, X.T @ y, float(y @ y)

    def parts(ts, td):
        d = 1.0 + nj * ts
        g = ts / d
        A = XtX - (SX * g[:, None]).T @ SX
        b = Xty - SX.T @ (g * sy)
        c = yty - float((g * sy * sy).sum())
        TX = np.column_stack([np.bincount(sd, SX[:, c_] / d, K)
                              for c_ in range(p)])
        ty = np.bincount(sd, sy / d, K)
        m = np.bincount(sd, nj / d, K)
        h = td / (1.0 + td * m)
        A = A - (TX * h[:, None]).T @ TX
        b = b - TX.T @ (h * ty)
        c = c - float((h * ty * ty).sum())
        return A, b, c, float(np.log(d).sum() + np.log1p(td * m).sum())

    def crit(par):
        ts, td = np.exp(np.clip(par, -16.0, 5.0))
        A, b, c, logdet = parts(ts, td)
        sign, ldA = np.linalg.slogdet(A)
        if sign <= 0:
            return 1e300
        rss = c - float(b @ np.linalg.solve(A, b))
        if rss <= 0:
            return 1e300
        return (n - p) * np.log(rss / (n - p)) + logdet + ldA

    best = None
    for x0 in ((-3.0, -4.0), (-5.0, -6.0), (-2.0, -8.0)):
        res = optimize.minimize(crit, x0, method="Nelder-Mead",
                                options={"xatol": 1e-5, "fatol": 1e-8,
                                         "maxiter": 4000})
        if best is None or res.fun < best.fun:
            best = res
    ts, td = np.exp(np.clip(best.x, -16.0, 5.0))
    A, b, c, _ = parts(ts, td)
    beta = np.linalg.solve(A, b)
    s2 = (c - float(b @ beta)) / (n - p)
    return {"sigma_e": s2, "sigma_s": ts * s2, "sigma_d": td * s2,
            "beta": beta, "n": n, "schools": J, "districts": K}


def logit_fe(X, y, cell, cluster, maxit=60):
    """logit with cell fixed effects (sparse dummies), clustered sandwich

    Cells without variation in the outcome are dropped, as is standard.
    """
    cc, K = group_index(cell)
    s = np.bincount(cc, y, K)
    cnt = np.bincount(cc, minlength=K)
    keep = ((s > 0) & (s < cnt))[cc]
    X, y, cluster = X[keep], y[keep], np.asarray(cluster)[keep]
    cc, K = group_index(np.asarray(cell)[keep])
    n, p = X.shape
    D = sparse.csr_matrix((np.ones(n), (np.arange(n), cc)), shape=(n, K))
    Z = sparse.hstack([sparse.csr_matrix(X), D]).tocsr()
    beta = np.zeros(p + K)
    H = None
    for _ in range(maxit):
        mu = 1.0 / (1.0 + np.exp(-(Z @ beta)))
        W = mu * (1.0 - mu)
        H = (Z.T @ sparse.diags(W) @ Z).toarray() + 1e-8 * np.eye(p + K)
        step = np.linalg.solve(H, Z.T @ (y - mu))
        beta += step
        if np.abs(step).max() < 1e-7:
            break
    mu = 1.0 / (1.0 + np.exp(-(Z @ beta)))
    codes, G = group_index(cluster)
    R = sparse.csr_matrix((np.ones(n), (codes, np.arange(n))), shape=(G, n))
    Sg = (R @ Z.multiply((y - mu)[:, None]).tocsr()).toarray()
    Hi = np.linalg.inv(H)
    V = Hi @ (Sg.T @ Sg) @ Hi * (G / (G - 1))
    return {"beta": beta[:p], "V": V[:p, :p], "n": n}


def bh(pvals, q=0.05):
    """Benjamini-Hochberg: boolean array of rejected hypotheses"""
    p = np.asarray(pvals, dtype=float)
    ok = np.isfinite(p)
    out = np.zeros(len(p), dtype=bool)
    idx = np.flatnonzero(ok)
    if not len(idx):
        return out
    order = idx[np.argsort(p[idx])]
    m = len(order)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    if passed.any():
        out[order[: np.flatnonzero(passed).max() + 1]] = True
    return out


def pool_dl(est, se):
    """DerSimonian-Laird random-effects pooled estimate"""
    est, se = np.asarray(est, float), np.asarray(se, float)
    ok = np.isfinite(est) & np.isfinite(se) & (se > 0)
    est, se = est[ok], se[ok]
    k = len(est)
    if k == 0:
        return {"k": 0}
    w = 1.0 / se ** 2
    fixed = (w * est).sum() / w.sum()
    Q = float((w * (est - fixed) ** 2).sum())
    cc = w.sum() - (w ** 2).sum() / w.sum()
    tau2 = max(0.0, (Q - (k - 1)) / cc) if k > 1 and cc > 0 else 0.0
    ws = 1.0 / (se ** 2 + tau2)
    mu = float((ws * est).sum() / ws.sum())
    s = float(np.sqrt(1.0 / ws.sum()))
    return {"k": k, "estimate": mu, "se": s, "lo": mu - 1.96 * s,
            "hi": mu + 1.96 * s, "tau2": tau2}


def pvalue(est, se):
    z = est / se
    return float(2 * stats.norm.sf(abs(z)))
