"""CineRank fast inference engine.

Serves recommendations from a trained, validated release directory
(backend/artifacts/models/releases/<release_id>/). It reproduces the behaviour of the
reference implementation (`reference_inference.CineRankRecommender`) and is tested for
parity against it, but is organised for low latency and high throughput:

  * everything is loaded once; derived structures (transposed content matrix, ALS Gram
    matrix, popularity order, id lookup tables) are built at start-up;
  * sparse model scoring touches only the rows of the history items (gather + bincount)
    instead of multiplying through the whole matrix;
  * ALS fold-in uses a Cholesky solve of a single F x F system;
  * top-k selection is O(N) (partition), never a full sort of the catalogue;
  * the popularity fallback and popularity candidate source need no scan of the catalogue;
  * the ONNX session is created once with tuned options; CUDA calls use I/O binding;
  * `recommend_many` batches the attention model across users in one ONNX call;
  * an optional LRU cache is safe because a release is immutable.

Security: no pickle, no joblib; np.load always uses allow_pickle=False (done by the
reference loader this module builds on). The engine never opens a database or the network.

This module is thread-safe after construction: recommend()/recommend_many() hold no
mutable per-request state, apart from the optional cache (guarded by a lock).
"""
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import scipy.linalg as sla

from . import reference_inference as ref


class InferenceError(RuntimeError):
    """Raised for invalid requests or an unusable runtime configuration."""


# --------------------------------------------------------------------------
# Low-level kernels
# --------------------------------------------------------------------------
def _gather_weighted_rows(indptr, indices, data, rows, row_weights, out_len):
    """sum_r w_r * M[r, :] for a CSR matrix M, returned as a dense float32 vector.

    Touches only the requested rows. Equivalent to (w @ M) for a sparse weight row w."""
    rows = np.asarray(rows, dtype=np.int64)
    if rows.size == 0:
        return np.zeros(out_len, dtype=np.float32)
    starts = indptr[rows].astype(np.int64)
    lens = indptr[rows + 1].astype(np.int64) - starts
    total = int(lens.sum())
    if total == 0:
        return np.zeros(out_len, dtype=np.float32)
    cum = np.cumsum(lens)
    pos = np.arange(total, dtype=np.int64) + np.repeat(starts - (cum - lens), lens)
    vals = data[pos].astype(np.float64)
    if row_weights is not None:
        vals = vals * np.repeat(np.asarray(row_weights, dtype=np.float64), lens)
    out = np.bincount(indices[pos], weights=vals, minlength=out_len)
    return out.astype(np.float32)


def _topk_masked(scores, k, exclude_idx):
    """Top-k indices of a writable float32 vector (modified in place: excluded -> -inf).

    Same ordering as reference_inference.topk_indices: descending score, ties by ascending
    index, excluded and non-finite entries never returned, possibly fewer than k results."""
    if exclude_idx.size:
        scores[exclude_idx] = -np.inf
    n = scores.size
    k = int(min(k, n))
    if k <= 0:
        return np.zeros(0, dtype=np.int64)
    if k == n:
        top = np.arange(n, dtype=np.int64)
    else:
        kth = np.partition(scores, n - k)[n - k]
        greater = np.flatnonzero(scores > kth)
        ties = np.flatnonzero(scores == kth)[: k - greater.size]
        top = np.concatenate([greater, ties])
    top = top[np.isfinite(scores[top])]
    order = np.lexsort((top, -scores[top]))
    return top[order].astype(np.int64)


def _bpr_fold_in_fast(item_factors, positive_items, seen_items, n_iterations, learning_rate, reg,
                      negatives_per_positive, seed, max_positives):
    """Same algorithm and RNG draw order as reference_inference.bpr_fold_in, with the repeated
    np.isin lookups replaced by one boolean mask. Returns the user vector (float32)."""
    v = item_factors[:, :-1]
    bias = item_factors[:, -1]
    n_items, f = v.shape
    pos = np.unique(np.asarray(positive_items, dtype=np.int64))
    if pos.size > max_positives:
        pos = pos[-max_positives:]
    if pos.size == 0:
        return np.zeros(f, dtype=np.float32)
    seen_mask = np.zeros(n_items, dtype=bool)
    seen_mask[np.asarray(seen_items, dtype=np.int64)] = True
    rng = np.random.default_rng(int(seed))
    u = rng.normal(0.0, 0.01, f)
    m = np.zeros(f)
    s = np.zeros(f)
    pos_rep = np.repeat(pos, int(negatives_per_positive))
    vp = np.asarray(v[pos_rep], dtype=np.float64)
    bp = np.asarray(bias[pos_rep], dtype=np.float64)
    for t in range(1, int(n_iterations) + 1):
        neg = rng.integers(0, n_items, size=pos_rep.size)
        for _ in range(10):
            hit = seen_mask[neg]
            if not hit.any():
                break
            neg[hit] = rng.integers(0, n_items, size=int(hit.sum()))
        keep = ~seen_mask[neg]
        if not keep.any():
            break
        nk = neg[keep]
        dv = vp[keep] - v[nk].astype(np.float64)
        db = bp[keep] - bias[nk].astype(np.float64)
        x = dv @ u + db
        g = -1.0 / (1.0 + np.exp(np.clip(x, -50.0, 50.0)))
        grad = (g[:, None] * dv).mean(axis=0) + reg * u
        m = 0.9 * m + 0.1 * grad
        s = 0.999 * s + 0.001 * grad * grad
        u = u - learning_rate * (m / (1 - 0.9 ** t)) / (np.sqrt(s / (1 - 0.999 ** t)) + 1e-8)
    return u.astype(np.float32)


def _mmr_fast(scores, candidate_items, item_vectors, k, lam, depth):
    """Vectorised Maximal Marginal Relevance; same decisions as reference_inference.mmr_rerank."""
    scores = np.asarray(scores, dtype=np.float64)
    depth = int(min(depth, scores.size))
    top = _topk_masked(scores.astype(np.float32), depth, np.zeros(0, dtype=np.int64))
    if lam >= 1.0 or item_vectors is None or top.size <= 1:
        return top[:k]
    s = scores[top]
    rel = (s - s.min()) / (s.max() - s.min() + 1e-9)
    vec = item_vectors[np.asarray(candidate_items, dtype=np.int64)[top]]
    sim = np.asarray((vec @ vec.T).todense(), dtype=np.float64)
    n = top.size
    selected = [0]
    chosen = np.zeros(n, dtype=bool)
    chosen[0] = True
    max_sim = sim[0].copy()
    base = lam * rel
    while len(selected) < min(k, n):
        value = base - (1.0 - lam) * max_sim
        value[chosen] = -np.inf
        j = int(np.argmax(value))
        selected.append(j)
        chosen[j] = True
        np.maximum(max_sim, sim[j], out=max_sim)
    return top[np.asarray(selected, dtype=np.int64)]


def _cholesky_solve(a, b):
    try:
        return sla.cho_solve(sla.cho_factor(a, lower=True, check_finite=False), b, check_finite=False)
    except np.linalg.LinAlgError:
        return np.linalg.solve(a, b)


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
class FastRecommender:
    """Low-latency recommender over one immutable release.

    Parameters
    ----------
    release_dir : path of the release directory (flat layout, see model_artifacts.md).
    use_gpu : request the ONNX Runtime CUDA provider for the attention model. The actual
        provider is exposed as `attention_provider`; with require_gpu=True a CPU fallback raises.
    disabled_models : model names to switch off (e.g. {"attention"}); the hybrid renormalises.
    verify_checksums, require_complete : release verification. Keep both True in production.
    intra_op_threads : ONNX Runtime intra-op threads (default min(4, cpu_count)).
    cache_size : number of recent responses kept (0 disables the cache).
    warmup : run a few dummy requests at start-up so the first real request is not slow.
    max_workers : threads used by recommend_many for the per-user scoring stage.
    """

    def __init__(self, release_dir, use_gpu=False, require_gpu=False, disabled_models=(),
                 verify_checksums=True, require_complete=True, intra_op_threads=None,
                 cache_size=0, warmup=True, max_workers=None):
        self.release = ref.load_release(release_dir, verify_checksums=verify_checksums,
                                        require_complete=require_complete)
        rel = self.release
        self.release_id = rel.manifest.get("release_id")
        self.n_items = rel.n_items
        self.hybrid = rel.configs["hybrid"]
        self.disabled = frozenset(disabled_models)
        self.threshold = float(self.hybrid["feedback"]["positive_rating_threshold"])
        self.io_binding_failures = 0

        # item id lookup (provider id <-> item index)
        ids = rel.item_provider_ids
        self.provider_ids = ids
        if bool(np.all(np.diff(ids) > 0)):
            self._sorted_ids, self._sorted_to_index = ids, None
        else:
            order = np.argsort(ids, kind="stable")
            self._sorted_ids, self._sorted_to_index = ids[order], order.astype(np.int64)

        # popularity
        self.popularity = np.ascontiguousarray(rel.arrays["popularity"], dtype=np.float32)
        self.cold_mask = self.popularity <= 0.0
        self._pop_order = np.lexsort((np.arange(self.n_items), -self.popularity)).astype(np.int64)

        # content
        self._content = None
        if rel.model_enabled("content") and "content" not in self.disabled:
            v = rel.arrays["content"]
            vt = v.T.tocsr()
            self._content = {
                "matrix": v,
                "v_indptr": v.indptr, "v_indices": v.indices, "v_data": v.data,
                "t_indptr": vt.indptr, "t_indices": vt.indices, "t_data": vt.data,
                "vocab": v.shape[1],
            }
        # ItemKNN
        self._knn = None
        if rel.model_enabled("itemknn") and "itemknn" not in self.disabled:
            m = rel.arrays["itemknn"]
            self._knn = (m.indptr, m.indices, m.data)
        # ALS
        self._als = None
        if rel.model_enabled("als") and "als" not in self.disabled:
            cfg = rel.configs["als"]
            self._als = {"Y": np.ascontiguousarray(rel.arrays["als"], dtype=np.float32),
                         "gram": rel.arrays["als_gram"], "alpha": float(cfg["confidence_alpha"]),
                         "reg": float(cfg["regularization"]), "eye": np.eye(rel.arrays["als"].shape[1])}
        # BPR (only when the release enables it)
        self._bpr = None
        if rel.model_enabled("bpr") and "bpr" not in self.disabled:
            self._bpr = {"factors": rel.arrays["bpr"], "fold": rel.configs["bpr"]["fold_in"]}

        # attention
        self.session = None
        self.attention_cfg = rel.configs.get("attention")
        self.attention_provider = None
        self._use_cuda = False
        if rel.model_enabled("attention") and "attention" not in self.disabled:
            self.session = self._make_session(rel.directory / "attention.onnx", use_gpu, intra_op_threads)
            self.attention_provider = self.session.get_providers()[0]
            self._use_cuda = self.attention_provider == "CUDAExecutionProvider"
            if use_gpu and require_gpu and not self._use_cuda:
                raise InferenceError("GPU required but the active provider is %s" % self.attention_provider)
            self._max_history = int(self.attention_cfg["max_history"])

        gen_cfg = self.hybrid["candidate_generation"]
        self._per_source = int(gen_cfg["per_source"])
        self._generators = [m for m in gen_cfg["sources"] if m != "attention" and self._active(m)]
        self._score_models = [m for m in self.hybrid["scoring_models"] if self._active(m)]
        mmr = self.hybrid["mmr"]
        self._mmr_lambda = float(mmr["lambda"])
        self._mmr_depth = int(mmr["candidate_depth"])
        self._mmr_vectors = rel.arrays.get("content") if mmr["enabled"] and self._active("content") else None

        self._cache = OrderedDict() if cache_size > 0 else None
        self._cache_size = int(cache_size)
        self._cache_lock = threading.Lock()
        self._workers = int(max_workers or min(8, os.cpu_count() or 1))
        self._executor = None
        self._executor_lock = threading.Lock()
        if warmup:
            self.warmup()

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _make_session(path, use_gpu, intra_op_threads):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.intra_op_num_threads = int(intra_op_threads or min(4, os.cpu_count() or 1))
        opts.inter_op_num_threads = 1
        opts.enable_mem_pattern = False  # dynamic candidate counts make the pattern cache useless
        providers = ["CPUExecutionProvider"]
        if use_gpu and "CUDAExecutionProvider" in ort.get_available_providers():
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        return ort.InferenceSession(str(path), sess_options=opts, providers=providers)

    def _active(self, name):
        if name in self.disabled or not self.release.model_enabled(name):
            return False
        return name != "attention" or self.session is not None

    def warmup(self, rounds=3):
        """Exercise every enabled model so lazy initialisation happens before real traffic."""
        n = self.n_items
        rng = np.random.default_rng(0)
        for _ in range(rounds):
            items = rng.choice(n, size=min(12, n), replace=False)
            self.recommend_arrays(items, np.full(items.size, 5.0, dtype=np.float32), k=10, use_cache=False)

    def close(self):
        with self._executor_lock:
            if self._executor is not None:
                self._executor.shutdown(wait=True)
                self._executor = None

    # ------------------------------------------------------------- id mapping
    def provider_ids_to_indices(self, provider_ids):
        """Vectorised lookup; unknown provider ids map to -1."""
        q = np.asarray(provider_ids, dtype=np.int64).ravel()
        pos = np.searchsorted(self._sorted_ids, q)
        pos = np.minimum(pos, self._sorted_ids.size - 1)
        hit = self._sorted_ids[pos] == q
        idx = pos if self._sorted_to_index is None else self._sorted_to_index[pos]
        return np.where(hit, idx, -1).astype(np.int64)

    def indices_to_provider_ids(self, indices):
        return self.provider_ids[np.asarray(indices, dtype=np.int64)]

    # ------------------------------------------------------- per-model scoring
    def _dense_scores(self, name, pos_items, pos_rel, seen):
        n = self.n_items
        if name == "itemknn":
            indptr, indices, data = self._knn
            return _gather_weighted_rows(indptr, indices, data, pos_items, None, n)
        if name == "content":
            c = self._content
            profile = _gather_weighted_rows(c["v_indptr"], c["v_indices"], c["v_data"], pos_items, None, c["vocab"])
            norm = float(np.sqrt(np.dot(profile.astype(np.float64), profile.astype(np.float64))))
            if norm <= 0.0:
                return np.zeros(n, dtype=np.float32)
            nz = np.flatnonzero(profile)
            return _gather_weighted_rows(c["t_indptr"], c["t_indices"], c["t_data"], nz,
                                         profile[nz] / norm, n)
        if name == "als":
            a = self._als
            idx = pos_items
            y = a["Y"][idx].astype(np.float64)
            conf = 1.0 + a["alpha"] * pos_rel.astype(np.float64)
            system = a["gram"] + (y.T * (conf - 1.0)) @ y + a["reg"] * a["eye"]
            x = _cholesky_solve(system, y.T @ conf).astype(np.float32)
            return a["Y"] @ x
        if name == "bpr":
            b = self._bpr
            fi = b["fold"]
            u = _bpr_fold_in_fast(b["factors"], pos_items, seen, fi["iterations"], fi["learning_rate"],
                                  fi["regularization"], fi["negatives_per_positive"],
                                  ref.bpr_seed(fi["seed"], pos_items), fi["max_positives"])
            return ref.bpr_scores(b["factors"], u)[0]
        raise KeyError(name)

    def _popularity_topk(self, k, excluded):
        """Top-k popular items not in `excluded`, without scanning the catalogue."""
        k = max(int(k), 0)
        if k == 0:
            return np.zeros(0, dtype=np.int64)
        head = self._pop_order[: k + excluded.size]
        if excluded.size:
            head = head[~np.isin(head, excluded, assume_unique=False)]
        return head[:k]

    # ------------------------------------------------------------ request prep
    def _prepare(self, items, ratings, exclude):
        n = self.n_items
        items = np.asarray(items, dtype=np.int64).ravel()
        ratings = np.asarray(ratings, dtype=np.float32).ravel()
        if items.size != ratings.size:
            raise InferenceError("items and ratings must have the same length")
        if items.size:
            if items.min() < 0 or items.max() >= n:
                raise InferenceError("history item index out of range")
            if not np.all(np.isfinite(ratings)):
                raise InferenceError("ratings must be finite")
            _, last_rev = np.unique(items[::-1], return_index=True)
            keep = np.sort(items.size - 1 - last_rev)
            items, ratings = items[keep], ratings[keep]
        extra = np.zeros(0, dtype=np.int64) if exclude is None else np.asarray(exclude, dtype=np.int64).ravel()
        if extra.size and (extra.min() < 0 or extra.max() >= n):
            raise InferenceError("excluded item index out of range")
        excluded = np.unique(np.concatenate([items, extra]))
        pos = ratings >= self.threshold
        return items, excluded, items[pos], ref.rating_to_relevance(ratings[pos])

    def _fallback_result(self, k, excluded, tag, t0, timings, return_timings):
        idx = self._popularity_topk(k, excluded)
        return self._result(idx, self.popularity[idx], ["popularity"], tag, t0, timings, return_timings)

    @staticmethod
    def _result(items, scores, models, fallback, t0, timings, return_timings):
        timings["total_ms"] = (time.perf_counter() - t0) * 1000.0
        res = {"items": np.asarray(items, dtype=np.int64), "scores": np.asarray(scores, dtype=np.float32),
               "models_used": list(models), "fallback": fallback}
        if return_timings:
            res["timings_ms"] = dict(timings)
        return res

    def _stage_candidates(self, items, excluded, pos_items, pos_rel, k, t0, return_timings):
        """Everything up to (not including) attention. Returns ('done', result) or ('pool', state)."""
        timings = {}
        if pos_items.size == 0:
            return "done", self._fallback_result(k, excluded, "cold_start_popularity", t0, timings, return_timings)
        if not self._generators or not self._score_models:
            return "done", self._fallback_result(k, excluded, "popularity_only", t0, timings, return_timings)
        dense = {}
        for name in set(self._score_models) | set(self._generators):
            if name in ("attention", "popularity"):
                continue
            t1 = time.perf_counter()
            dense[name] = self._dense_scores(name, pos_items, pos_rel, items)
            timings[name + "_ms"] = (time.perf_counter() - t1) * 1000.0
        t1 = time.perf_counter()
        parts = []
        for g in self._generators:
            if g == "popularity":
                parts.append(self._popularity_topk(self._per_source, excluded))
            else:
                parts.append(_topk_masked(dense[g], self._per_source, excluded))
        pool = np.unique(np.concatenate(parts)) if parts else np.zeros(0, dtype=np.int64)
        timings["pool_ms"] = (time.perf_counter() - t1) * 1000.0
        if pool.size == 0:
            return "done", self._fallback_result(k, excluded, "empty_pool_popularity", t0, timings, return_timings)
        state = {"pool": pool, "dense": dense, "pos_items": pos_items, "excluded": excluded,
                 "k": k, "t0": t0, "timings": timings, "return_timings": return_timings}
        return "pool", state

    # ----------------------------------------------------------------- attention
    def _run_attention(self, hist, cand):
        feeds = {"history": np.ascontiguousarray(hist, dtype=np.int64),
                 "candidates": np.ascontiguousarray(cand, dtype=np.int64)}
        if self._use_cuda:
            try:
                binding = self.session.io_binding()
                binding.bind_cpu_input("history", feeds["history"])
                binding.bind_cpu_input("candidates", feeds["candidates"])
                binding.bind_output("scores", "cuda")
                self.session.run_with_iobinding(binding)
                return binding.copy_outputs_to_cpu()[0]
            except Exception:  # noqa: BLE001 - keep serving; the counter makes the problem visible
                self.io_binding_failures += 1
        return self.session.run(["scores"], feeds)[0]

    def _attention_for_states(self, states):
        """One ONNX call for all states. Candidates are right-padded with id 0 and ignored."""
        t1 = time.perf_counter()
        width = max(s["pool"].size for s in states)
        cand = np.zeros((len(states), width), dtype=np.int64)
        for i, s in enumerate(states):
            cand[i, : s["pool"].size] = s["pool"] + 1
        hist = ref.pad_histories([s["pos_items"] for s in states], self._max_history)
        out = self._run_attention(hist, cand)
        elapsed = (time.perf_counter() - t1) * 1000.0 / len(states)
        for i, s in enumerate(states):
            scores = out[i, : s["pool"].size].astype(np.float64)
            cold = self.cold_mask[s["pool"]]
            if cold.any() and (~cold).any():
                scores[cold] = scores[~cold].min()
            s["attention"] = scores
            s["timings"]["attention_ms"] = elapsed

    # ------------------------------------------------------------------ finishing
    def _finish(self, s):
        pool, k, timings = s["pool"], s["k"], s["timings"]
        t1 = time.perf_counter()
        pool_scores = {}
        for name in self._score_models:
            if name == "attention":
                pool_scores[name] = s["attention"]
            elif name == "popularity":
                pool_scores[name] = self.popularity[pool].astype(np.float64)
            else:
                pool_scores[name] = s["dense"][name][pool].astype(np.float64)
        valid = np.ones((1, pool.size), dtype=bool)
        normed = {m: ref.normalize_scores(pool_scores[m][None, :], valid, self.hybrid["normalization"])
                  for m in self._score_models}
        fused = ref.fuse_scores(normed, self.hybrid["weights"])[0]
        pos = _mmr_fast(fused, pool, self._mmr_vectors, k, self._mmr_lambda, self._mmr_depth)
        timings["fusion_mmr_ms"] = (time.perf_counter() - t1) * 1000.0
        out = pool[pos]
        if out.size < k:
            extra = self._popularity_topk(k - out.size, np.concatenate([s["excluded"], out]))
            out = np.concatenate([out, extra])[:k]
            return self._result(out, np.zeros(out.size), self._score_models, "pool_smaller_than_k",
                                s["t0"], timings, s["return_timings"])
        return self._result(out, fused[pos], self._score_models, None, s["t0"], timings, s["return_timings"])

    # ------------------------------------------------------------------ cache
    def _cache_key(self, items, ratings, exclude, k):
        ex = b"" if exclude is None else np.asarray(exclude, dtype=np.int64).tobytes()
        return (int(k), np.asarray(items, dtype=np.int64).tobytes(),
                np.asarray(ratings, dtype=np.float32).tobytes(), ex)

    def _cache_get(self, key):
        if self._cache is None:
            return None
        with self._cache_lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
            return hit

    def _cache_put(self, key, value):
        if self._cache is None:
            return
        for a in (value["items"], value["scores"]):
            a.setflags(write=False)
        with self._cache_lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    # ------------------------------------------------------------------ public API
    def recommend_arrays(self, items, ratings, k=20, exclude=None, return_timings=False, use_cache=True):
        """Recommend for one user. items/ratings are parallel arrays, oldest -> newest.
        `items` are release item indices. Returns a dict (items, scores, models_used, fallback)."""
        return self.recommend_many([(items, ratings)], k=k, excludes=[exclude],
                                   return_timings=return_timings, use_cache=use_cache)[0]

    def recommend(self, history, k=20, exclude=None, return_timings=False):
        """Same signature as the reference recommender: history = [(item_index, rating), ...]."""
        items = [h[0] for h in history]
        ratings = [h[1] for h in history]
        return self.recommend_arrays(items, ratings, k=k, exclude=exclude, return_timings=return_timings)

    def recommend_by_provider_ids(self, history, k=20, exclude_provider_ids=None):
        """history = [(provider_id, rating), ...]. Unknown provider ids are dropped and counted.
        Returns the result with `provider_ids` added and `dropped_unknown_history_items`."""
        if len(history):
            pids = np.asarray([h[0] for h in history], dtype=np.int64)
            ratings = np.asarray([h[1] for h in history], dtype=np.float32)
        else:
            pids, ratings = np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)
        idx = self.provider_ids_to_indices(pids)
        ok = idx >= 0
        exclude = None
        if exclude_provider_ids is not None and len(exclude_provider_ids):
            ex = self.provider_ids_to_indices(exclude_provider_ids)
            exclude = ex[ex >= 0]
        res = dict(self.recommend_arrays(idx[ok], ratings[ok], k=k, exclude=exclude))
        res["provider_ids"] = self.indices_to_provider_ids(res["items"])
        res["dropped_unknown_history_items"] = int((~ok).sum())
        return res

    def similar_by_provider_id(self, provider_id, k=10, exclude_provider_ids=None):
        """Return item-to-item neighbours for one provider title.

        The trained ItemKNN row is the primary signal. Content cosine similarity
        completes the list when ItemKNN is disabled or sparse, and popularity
        fills any remaining slots so the endpoint always returns a usable set.
        """
        idx = int(self.provider_ids_to_indices([provider_id])[0])
        if idx < 0:
            return {"items": np.zeros(0, dtype=np.int64),
                    "scores": np.zeros(0, dtype=np.float32),
                    "provider_ids": np.zeros(0, dtype=np.int64),
                    "models_used": [], "fallback": "unknown_item"}
        k = int(min(max(1, int(k)), max(0, self.n_items - 1)))
        excluded = np.array([idx], dtype=np.int64)
        if exclude_provider_ids is not None and len(exclude_provider_ids):
            extra = self.provider_ids_to_indices(exclude_provider_ids)
            extra = extra[extra >= 0]
            if extra.size:
                excluded = np.unique(np.concatenate([excluded, extra]))

        result_items = np.zeros(0, dtype=np.int64)
        result_scores = np.zeros(0, dtype=np.float32)
        models = []
        source = np.array([idx], dtype=np.int64)
        weight = np.array([5.0], dtype=np.float32)

        if self._knn is not None and k > 0:
            indptr = self._knn[0]
            # An empty row means the source has no trained neighbours. Do not
            # let arbitrary zero scores crowd out the content fallback.
            if int(indptr[idx + 1] - indptr[idx]) > 0:
                scores = self._dense_scores("itemknn", source, weight, set())
                top = _topk_masked(scores, k, excluded)
                result_items, result_scores = top, scores[top]
                models.append("itemknn")

        if self._content is not None and result_items.size < k:
            scores = self._dense_scores("content", source, weight, set())
            if scores.size and float(scores.max()) > 0.0:
                already = excluded if result_items.size == 0 else np.unique(
                    np.concatenate([excluded, result_items])
                )
                top = _topk_masked(scores, k - result_items.size, already)
                result_items = np.concatenate([result_items, top])
                result_scores = np.concatenate([result_scores, scores[top]])
                models.append("content")

        if result_items.size < k:
            scores = self.popularity.copy()
            already = excluded if result_items.size == 0 else np.unique(
                np.concatenate([excluded, result_items])
            )
            top = _topk_masked(scores, k - result_items.size, already)
            result_items = np.concatenate([result_items, top])
            result_scores = np.concatenate([result_scores, scores[top]])
            models.append("popularity")

        return {
            "items": result_items,
            "scores": result_scores,
            "provider_ids": self.indices_to_provider_ids(result_items),
            "models_used": models,
            "fallback": None,
        }

    def recommend_many(self, requests, k=20, excludes=None, return_timings=False, use_cache=True, parallel=True):
        """Recommend for several users. requests = [(items, ratings), ...].

        Per-user scoring runs in a thread pool; the attention model is evaluated for all
        users in one batched ONNX call (the main reason to use this with a GPU)."""
        t_start = time.perf_counter()
        n_req = len(requests)
        excludes = excludes if excludes is not None else [None] * n_req
        results = [None] * n_req
        todo = []
        for i, ((items, ratings), ex) in enumerate(zip(requests, excludes)):
            key = None
            if use_cache and self._cache is not None and not return_timings:
                key = self._cache_key(items, ratings, ex, k)
                hit = self._cache_get(key)
                if hit is not None:
                    results[i] = hit
                    continue
            todo.append((i, items, ratings, ex, key))

        def stage1(job):
            _, items, ratings, ex, _ = job
            t0 = time.perf_counter()
            it, excluded, pi, pr = self._prepare(items, ratings, ex)
            return self._stage_candidates(it, excluded, pi, pr, int(k), t0, return_timings)

        if parallel and len(todo) > 1 and self._workers > 1:
            with self._executor_lock:
                if self._executor is None:
                    self._executor = ThreadPoolExecutor(max_workers=self._workers, thread_name_prefix="cinerank")
            staged = list(self._executor.map(stage1, todo))
        else:
            staged = [stage1(j) for j in todo]

        pool_states = [(job, st) for job, (kind, st) in zip(todo, staged) if kind == "pool"]
        if pool_states and "attention" in self._score_models:
            self._attention_for_states([st for _, st in pool_states])
        for job, (kind, st) in zip(todo, staged):
            res = st if kind == "done" else self._finish(st)
            results[job[0]] = res
            if job[4] is not None:
                self._cache_put(job[4], res)
        return results
