"""Kernel-level comparison at a realistic catalogue size using RANDOM stand-in matrices
(no model files, no training). Shows the cost of the scoring kernels, reference vs fast.
Absolute numbers depend on this machine and on random sparsity patterns."""
import sys, time, pathlib
import numpy as np, scipy.sparse as sp
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend" / "ml"))
from cinerank_inference import reference_inference as ref
from cinerank_inference import fast_recommender as fr

N, V, F, K = 87_000, 20_000, 64, 100
rng = np.random.default_rng(0)
def rand_csr(r, c, per_row):
    indptr = np.arange(0, r * per_row + 1, per_row, dtype=np.int64)
    idx = rng.integers(0, c, size=r * per_row).astype(np.int32)
    m = sp.csr_matrix((rng.random(r * per_row).astype(np.float32), idx, indptr), shape=(r, c)); m.sum_duplicates(); return m
knn = rand_csr(N, N, K); content = rand_csr(N, V, 8); Y = rng.normal(0, .3, (N, F)).astype(np.float32)
gram = ref.als_gram(Y); vt = content.T.tocsr()
hist = np.sort(rng.choice(N, 40, replace=False)); rel = rng.random(40).astype(np.float32)

def t(fn, n=30):
    fn(); xs = []
    for _ in range(n):
        a = time.perf_counter(); fn(); xs.append((time.perf_counter() - a) * 1e3)
    return np.median(xs)

h = ref.history_matrix([hist], [None], N)
r_knn = lambda: ref.itemknn_scores(knn, h)[0]
f_knn = lambda: fr._gather_weighted_rows(knn.indptr, knn.indices, knn.data, hist, None, N)
r_con = lambda: ref.content_scores(content, h)[0]
def f_con():
    p = fr._gather_weighted_rows(content.indptr, content.indices, content.data, hist, None, V)
    nz = np.flatnonzero(p); nrm = np.sqrt((p.astype(np.float64) ** 2).sum())
    return fr._gather_weighted_rows(vt.indptr, vt.indices, vt.data, nz, p[nz] / nrm, N)
r_als = lambda: (Y @ ref.als_fold_in(Y, gram, hist, rel, 40.0, 0.05))
eye = np.eye(F)
def f_als():
    y = Y[hist].astype(np.float64); c = 1 + 40.0 * rel.astype(np.float64)
    x = fr._cholesky_solve(gram + (y.T * (c - 1)) @ y + 0.05 * eye, y.T @ c).astype(np.float32); return Y @ x
sc = rng.random(N).astype(np.float32); ex = hist
r_top = lambda: ref.topk_indices(sc, 100, ex)
f_top = lambda: fr._topk_masked(sc.copy(), 100, ex)

for name, a, b in [("ItemKNN", r_knn, f_knn), ("content", r_con, f_con), ("ALS", r_als, f_als), ("top-100", r_top, f_top)]:
    ra, fb = a(), b()
    if name != "top-100":
        assert np.allclose(ra, fb, rtol=1e-3, atol=1e-5), name
    else:
        assert np.array_equal(ra, fb)
    print(f"{name:8s} reference {t(a):8.3f} ms   fast {t(b):8.3f} ms")
