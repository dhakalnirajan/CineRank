"""Parity + latency check of FastRecommender against the reference recommender.
Usage: python3 test_fast_inference.py <release_dir> [n_requests]
Uses only inference (no training, no optimizer step). On a synthetic release the latency
numbers say nothing about production; run it against the real release on real hardware."""
import sys, time, pathlib, importlib
import numpy as np
root = pathlib.Path(__file__).resolve().parents[1] / "backend" / "ml"
sys.path.insert(0, str(root))
fast_mod = importlib.import_module("cinerank_inference")
from cinerank_inference import reference_inference as ref
release = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 200

# the shipped package copy must be the notebook's reference module, byte for byte
a = (root / "cinerank_inference" / "reference_inference.py").read_bytes()
b = (pathlib.Path(__file__).parent / "reference_inference.py").read_bytes()
assert a == b, "package reference_inference.py differs from verification copy"

R = ref.CineRankRecommender(release)
F = fast_mod.FastRecommender(release, cache_size=64)
print("release:", F.release_id, "| items:", F.n_items, "| attention provider:", F.attention_provider)
print("generators:", F._generators, "| scoring:", F._score_models)

rng = np.random.default_rng(1)
n = F.n_items
reqs = []
for _ in range(N):
    h = int(rng.choice([0, 1, 3, 8, 20, 60]))
    items = rng.choice(n, size=min(h, n), replace=False)
    ratings = rng.choice([1.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0], size=items.size)
    reqs.append((items, ratings.astype(np.float32)))

same_items = 0; max_score_diff = 0.0; fallbacks = {}
for items, ratings in reqs:
    hist = list(zip(items.tolist(), ratings.tolist()))
    r = R.recommend(hist, k=10); f = F.recommend(hist, k=10)
    assert r["fallback"] == f["fallback"], (r["fallback"], f["fallback"])
    fallbacks[f["fallback"]] = fallbacks.get(f["fallback"], 0) + 1
    assert f["models_used"] == list(r["models_used"]), (f["models_used"], r["models_used"])
    if np.array_equal(r["items"], f["items"]):
        same_items += 1
        max_score_diff = max(max_score_diff, float(np.abs(r["scores"] - f["scores"]).max()) if r["items"].size else 0.0)
    else:
        # accept only a float-rounding swap: the overlap must be near-total
        ov = len(set(r["items"]) & set(f["items"])) / max(len(r["items"]), 1)
        assert ov >= 0.8, ("top-10 mismatch", ov, r["items"], f["items"])
print(f"identical top-10 on {same_items}/{N} requests; max |score diff| on those: {max_score_diff:.2e}; fallbacks: {fallbacks}")
assert same_items >= 0.95 * N, "too many differing top-10 lists"

# batched path must agree with the single path (padded candidates must not change scores)
batch = F.recommend_many(reqs[:40], k=10, use_cache=False)
agree = 0
for (items, ratings), bres in zip(reqs[:40], batch):
    s = F.recommend_arrays(items, ratings, k=10, use_cache=False)
    if np.array_equal(s["items"], bres["items"]): agree += 1
print(f"batched == single on {agree}/40")
assert agree >= 38

# cache returns the same object content and is read-only
x = F.recommend_arrays(*reqs[5], k=10); y = F.recommend_arrays(*reqs[5], k=10)
assert np.array_equal(x["items"], y["items"]) and not y["items"].flags.writeable

# provider-id mapping round trip
pid = F.provider_ids[[3, 7, 11]]
assert np.array_equal(F.provider_ids_to_indices(np.r_[pid, -5]), [3, 7, 11, -1])
res = F.recommend_by_provider_ids([(int(pid[0]), 5.0), (-5, 5.0)], k=5)
assert res["dropped_unknown_history_items"] == 1 and len(res["provider_ids"]) == 5

# invalid input
for bad in [([n], [5.0]), ([-1], [5.0]), ([0], [float("nan")]), ([0, 1], [5.0])]:
    try: F.recommend_arrays(*bad); raise SystemExit("accepted bad input %r" % (bad,))
    except fast_mod.InferenceError: pass

# determinism
a1 = F.recommend_arrays(*reqs[7], k=10, use_cache=False); a2 = F.recommend_arrays(*reqs[7], k=10, use_cache=False)
assert np.array_equal(a1["items"], a2["items"])

# latency (single user, k=10); informational
def bench(fn, rounds=300):
    t = []
    for q in reqs[:rounds] * (rounds // max(len(reqs[:rounds]), 1) + 1):
        pass
    sel = [q for q in reqs if len(q[0]) >= 3][:100]
    for q in sel[:10]: fn(q)
    for _ in range(3):
        for q in sel:
            t0 = time.perf_counter(); fn(q); t.append((time.perf_counter() - t0) * 1e3)
    return np.percentile(t, [50, 95, 99])
rf = lambda q: R.recommend(list(zip(q[0].tolist(), q[1].tolist())), k=10)
ff = lambda q: F.recommend_arrays(q[0], q[1], k=10, use_cache=False)
pr, pf = bench(rf), bench(ff)
print("single-user latency ms p50/p95/p99  reference: %.2f/%.2f/%.2f   fast: %.2f/%.2f/%.2f" % (*pr, *pf))
sel = [q for q in reqs if len(q[0]) >= 3][:64]
t0 = time.perf_counter(); F.recommend_many(sel, k=10, use_cache=False); tb = time.perf_counter() - t0
t0 = time.perf_counter(); [rf(q) for q in sel]; tr = time.perf_counter() - t0
print("64 users: reference loop %.1f ms, fast recommend_many %.1f ms" % (tr * 1e3, tb * 1e3))
F.close()
print("FAST INFERENCE PARITY CHECKS PASSED")
