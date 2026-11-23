# cinerank_inference

Production inference engine for a CineRank release. Dependencies: `numpy`, `scipy`, `onnxruntime` (or `onnxruntime-gpu`). No PyTorch, no pickle, no database, no network.

Copy `backend/ml/cinerank_inference/` into the backend (or put `backend/ml` on `PYTHONPATH`).

## Use

```python
from cinerank_inference import FastRecommender

rec = FastRecommender(
    "backend/artifacts/models/releases/<release_id>",
    use_gpu=False,        # True requests CUDA; check rec.attention_provider afterwards
    cache_size=1024,      # 0 disables the LRU cache (safe: a release is immutable)
)

# history: provider ids (MovieLens movieId) with ratings, oldest -> newest
out = rec.recommend_by_provider_ids([(318, 5.0), (296, 4.5), (356, 2.0)], k=20)
out["provider_ids"]   # map to title UUIDs in the backend database
out["scores"], out["models_used"], out["fallback"]

# or with release item indices
out = rec.recommend_arrays(item_indices, ratings, k=20)

# many users at once: per-user scoring in a thread pool, ONE batched attention call
outs = rec.recommend_many([(items_a, ratings_a), (items_b, ratings_b)], k=20)
```

Create one `FastRecommender` per process at start-up. It verifies checksums and the manifest, loads everything, builds the ONNX session and warms up. Requests are then thread-safe.

## What is optimised

| Stage | Technique |
|---|---|
| Start-up | single load; transposed content matrix, ALS Gram matrix, popularity order and id lookup built once; warm-up requests |
| ItemKNN, content | gather only the history rows and accumulate with `bincount`; no whole-matrix product |
| ALS | one `F x F` Cholesky solve, float32 matrix-vector scoring |
| BPR fold-in | same algorithm and random draws as the reference, boolean mask instead of repeated `isin` |
| Top-k | O(N) partition, deterministic ties; popularity source and fallback need no catalogue scan |
| Attention | ONNX session created once with tuned options; CUDA path uses I/O binding; batch path pads candidates with id 0 and discards them |
| Diversity | vectorised MMR |
| Repeat requests | optional LRU cache |

## Behaviour contract

Output matches `reference_inference.CineRankRecommender` (same fallbacks, normalisation, weights, MMR, tie-breaking). `verification/verify_fast_inference.py` checks this on a release and fails if the top-10 lists diverge.

Fallbacks: `cold_start_popularity` (no positive history), `popularity_only`, `empty_pool_popularity`, `pool_smaller_than_k`. Disable a model with `disabled_models={"attention"}`; the hybrid renormalises.

Invalid input (index out of range, non-finite rating, length mismatch) raises `InferenceError`. Unknown provider ids in `recommend_by_provider_ids` are dropped and counted in `dropped_unknown_history_items`.

## Deployment notes

- CPU threads: set `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS` and `intra_op_threads` so that workers x threads does not exceed the cores available.
- GPU is optional and not automatically faster. Measure with `verification/verify_fast_inference.py` on production hardware. Use `require_gpu=True` if a silent CPU fallback must fail start-up.
- `recommend_many` helps most when the attention model runs on a GPU. On CPU the per-user stages are largely Python and NumPy, so extra threads give little.
- Not covered: serving new catalogue items that are not in the release index (see `model_artifacts.md`, section 8).
