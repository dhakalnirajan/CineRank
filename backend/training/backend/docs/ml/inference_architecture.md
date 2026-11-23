# CineRank inference architecture

Companion to `model_artifacts.md`. The reference implementation is `reference_inference.py` (`CineRankRecommender`), written into every training run and tested by the notebook against the extracted bundle.

The optimised production engine is `backend/ml/cinerank_inference/` (`FastRecommender`, see its README). It follows this document and is parity-tested against the reference implementation.

## 1. Lifecycle

1. **Startup (once per process):** verify the release (signature, checksums, manifest `complete`), load every array and sparse matrix with `allow_pickle=False`, create **one** ONNX Runtime session, precompute the ALS Gram matrix `Y^T Y`, build the `provider id -> item index` map from `item_provider_ids.npy` joined with the database's title ids.
2. **Request:** translate the user's interaction history from the database into `(item_index, rating)` pairs, call `recommend`, translate item indices back to title UUIDs.
3. **No per-request model loading, no repeated weight transfer, no embedding recomputation.** Item embeddings live inside the ONNX graph; item factors stay in memory (or resident on the GPU if GPU scoring is enabled).

The recommender holds no mutable per-request state, so one instance can serve concurrent requests (ONNX Runtime sessions are safe for concurrent `run`).

## 2. Request flow

```
history [(item, rating)...]  oldest -> newest
   |  de-duplicate (latest wins); positives = rating >= 3.5
   |  excluded = every history item (+ caller-provided exclusions)
   v
no positives?  ----yes---->  popularity top-k            (fallback: cold_start_popularity)
   |
   v
dense scores over the full catalogue:
   popularity | content | ItemKNN | ALS fold-in | (BPR fold-in if production-enabled)
   |
   v
candidate pool = union of top-N per source (N = candidate_generation.per_source), minus excluded items
   |
   v
attention scores on the pool only (ONNX, history padded to max_history, ids + 1)
   cold-item policy: popularity == 0  ->  pool minimum
   |
   v
per-request normalisation over the pool  (minmax | zscore | rank)
   |
   v
weighted fusion (weights from hybrid_config; unavailable/disabled models are dropped and the rest renormalised)
   |
   v
MMR over the top `candidate_depth` fused candidates: lambda * relevance - (1 - lambda) * max content-cosine to selected
   |
   v
top-k item indices + fused scores
```

Why normalise: popularity scores, cosine similarities, ALS dot products and neural logits live on incomparable scales; adding them raw lets one model dominate.

## 3. Fallbacks

| Condition | Behaviour |
|---|---|
| No positive history (new user, or only low ratings) | popularity ranking, `fallback = cold_start_popularity` |
| A model is unavailable, disabled, or fails to load | dropped; remaining weights renormalised per request |
| No scoring model left | popularity |
| Candidate pool smaller than `k` | pad with popularity items |
| Content model unavailable | MMR disabled |

The configured order of degradation is `hybrid -> als -> itemknn -> content -> popularity`. Disabling a model in configuration requires no retraining. BPR is excluded unless the manifest marks it `production_enabled`.

## 4. CPU and GPU

| Component | CPU | GPU |
|---|---|---|
| popularity | NumPy top-k | unnecessary |
| content | SciPy sparse | optional, rarely useful |
| ItemKNN | SciPy sparse product | optional |
| ALS / BPR | NumPy fold-in and scoring | optional batched scoring |
| attention | ONNX Runtime CPU | ONNX Runtime CUDA |
| hybrid | NumPy fusion and MMR | unnecessary |

GPU is optional and never assumed faster. For one user and a few hundred candidates, kernel launch and host-device transfer can dominate. The notebook benchmarks ONNX Runtime CPU/CUDA and PyTorch CPU/CUDA for batch sizes 1, 16, 128, candidate counts 100 and 400, and two history lengths, recording p50, p95, p99, throughput, memory, hardware and software versions, and the **active execution provider**. A backend counts as GPU only when `session.get_providers()[0] == "CUDAExecutionProvider"`; ONNX Runtime may silently fall back to CPU.

Operational guidance:
- Create the ONNX session once. Choose the provider from configuration, then confirm it at startup and log it.
- Batch concurrent requests for the GPU only if measured throughput justifies the added latency.
- Pin BLAS and ONNX Runtime thread counts to avoid oversubscription when several workers run on one host.

## 5. Determinism

Same history and same release give the same output: ties break by ascending item index; the BPR fold-in seed derives from the history; no wall-clock inputs (popularity uses a fixed cutoff). Exact bitwise reproducibility across CPU models, BLAS builds or CUDA kernels is not guaranteed.

## 6. Validation performed before a release is marked complete

Files exist; dtypes, shapes, finiteness; sparse validity; item-index alignment; attention config versus Safetensors shapes; ONNX graph check; ONNX versus PyTorch parity; ALS fold-in residual on an unseen user; content vector for a brand-new item; CPU inference with ablations (attention off, ALS off, ItemKNN and content off, only popularity), cold start, determinism; agreement between the batched evaluation pipeline and the serving code on real validation histories; GPU parity only when CUDA is genuinely active. The same suite runs again on the bundle after safe extraction and checksum verification.

## 7. Known limits

- The recommender serves only items in the release index (`model_artifacts.md`, section 8).
- Attention re-ranks the pool; if the target is not in the pool, it cannot be recovered.
- ItemKNN, ALS and attention carry no signal for items without training positives.
- Latency numbers depend on hardware; use the run's `metrics.json` for the machine that produced them and re-measure on production hardware.
