# CineRank model artifacts and inference contract

Status: produced by `train_all_models.ipynb`. Every statement here describes what the notebook writes and what `reference_inference.py` (shipped in each training run) reads. It contains no evaluation numbers; those are generated per run (see `model_evaluation.md`).

## 1. Ownership boundary

- The notebook is an offline training environment. It does not import the backend, connect to the production database, or touch schemas or migrations.
- The backend database is authoritative for users, titles, ratings, interactions and watchlists.
- A release contains model parameters only. It does **not** contain raw MovieLens ratings, MovieLens user ids, training-user factors, a catalogue CSV, holdout rows, training matrices, or database content.
- `item_provider_ids.npy` is a model alignment contract, not a catalogue. The backend resolves each provider id to its permanent `title_<UUIDv7>` through its own database.
- ItemKNN similarities and popularity scores are aggregate statistics derived from MovieLens interactions. They are not individual records.

## 2. Directory layout

```
backend/artifacts/
  models/releases/<release_id>/        production inference release (immutable)
  training-runs/<run_id>/              diagnostics and reproducibility (not for inference)
```

`<release_id>` is `cinerank-<UTC timestamp>-<8 hex>`; `<run_id>` is `run-<same stamp>-<same suffix>`. A release is never overwritten. Training data lives outside this tree (`cinerank_data/`).

### Release files (flat)

| File | Model | Format | dtype / shape | Required when |
|---|---|---|---|---|
| `manifest.json` | all | JSON | | always |
| `SHA256SUMS` | all | text, `sha256sum` format | | always |
| `item_provider_ids.npy` | all | NumPy | int64 `[N]` | always |
| `popularity_scores.npy` | popularity | NumPy | float32 `[N]` | always |
| `popularity_config.json` | popularity | JSON | | always |
| `content_item_vectors.npz` | content | SciPy CSR | float32 `[N, V]`, int32 indices | content available |
| `content_idf.npy` | content | NumPy | float32 `[V]` | content available |
| `content_config.json` | content | JSON (vocabulary, weights, tokenizer) | | content available |
| `itemknn_topk.npz` | ItemKNN | SciPy CSR | float32 `[N, N]` | ItemKNN available |
| `itemknn_config.json` | ItemKNN | JSON | | ItemKNN available |
| `als_item_factors.npy` | ALS | NumPy | float32 `[N, F]` | ALS available |
| `als_config.json` | ALS | JSON | | ALS available |
| `bpr_item_factors.npy` | BPR | NumPy | float32 `[N, F+1]` | BPR available |
| `bpr_config.json` | BPR | JSON | | BPR available |
| `attention.safetensors` | attention | Safetensors | float32 | always |
| `attention.onnx` | attention | ONNX, opset 17 | | always |
| `attention_config.json` | attention | JSON | | always |
| `hybrid_config.json` | hybrid | JSON | | always |

`N` is the number of catalogue items in the training index; `V` the content vocabulary size; `F` the ALS or BPR factor count. Only files a model needs are written. A model that is unavailable has `status: "unavailable"` in the manifest and no files.

### Training-run files (diagnostic)

`training-config.json`, `environment.json`, `metrics.json`, `evaluation.json`, `evaluation_report.md`, `attention_training.json`, `attention_final.safetensors` (final-step weights), `reference_inference.py`, `SHA256SUMS`.

## 3. Loading rules

- `np.load(path, allow_pickle=False)` always. `scipy.sparse.load_npz` for sparse files (no pickle).
- No pickle, joblib or `torch.load` of untrusted files. Neural weights are Safetensors/ONNX.
- Load a release **once per process** and keep arrays and the ONNX session in memory.
- Refuse any release whose manifest `status` is not `complete`.
- Verify `SHA256SUMS` (every listed file matches, no unlisted file exists). Checksums detect corruption only; they do not authenticate the publisher (see `model_deployment.md`).
- `reference_inference.load_release` performs: existence, dtype, shape, finiteness, CSR validity (indices in range, `indptr` monotone), no self-similarity and at most `k` neighbours per ItemKNN row, unique provider ids, hybrid weights summing to 1 and referencing only enabled models.

## 4. Manifest (`manifest.json`)

Key fields: `schema_version` (1), `release_id`, `training_run_id`, `status` (`draft` while being written, `complete` only after all validation passed), `created_at_utc`, `provider` (`movielens`), `item_id_file`, `n_items`, `models` (per model: `status`, `files`, `production_enabled`, optional `reason`), `files` (sha256, bytes, dtype, shape/nnz), `dataset` (URL and archive SHA-256), `training_cohort`, `feedback_semantics`, `attention_training`, `signature` (`unsigned`), `runtime_requirements`.

`production_enabled` is false for BPR unless its validation gate passed (section 7).

## 5. Index alignment

Row *i* of every item-indexed artifact (popularity, content vectors, ItemKNN rows and columns, ALS/BPR factors, attention embeddings with the +1 offset) corresponds to `item_provider_ids[i]`. Provider ids are MovieLens `movieId` values, sorted ascending and unique.

The backend maps `provider id -> title UUID` from its own database and builds `title UUID -> item index`. Titles that exist in the database but not in `item_provider_ids` have no index and cannot be scored by index-based models (see section 8).

## 6. Feedback semantics (all models)

| Concept | Definition | Use |
|---|---|---|
| Explicit rating | 0.5 to 5.0 | exclusion sets, popularity quality term, diagnostics |
| Positive implicit interaction | rating >= `positive_rating_threshold` (3.5, configurable) | ALS, BPR, ItemKNN, content profile, attention history |
| Negative feedback | rating <= 2.5 | counted in the popularity denominator; never positive |
| Neutral | between the thresholds | not positive; counted as an exposure |
| Missing | no rating | **not** a dislike. BPR/attention "negatives" are unobserved items sampled without verification of dislike |

`relevance = clip((rating - 0.5) / 4.5, 0, 1)`. For non-rating signals (watchlist, likes), the backend must define an explicit rating-equivalent before calling the models; the thresholds above then apply unchanged.

A request supplies a **history**: `(item_index, rating)` pairs, oldest to newest. Items are de-duplicated (latest wins). Every history item, positive or not, is excluded from the output.

## 7. Per-model contracts

### Popularity
- Input: none. Output: `popularity_scores[i]` in `[0, 1]`.
- Score: `D_i * q_i / max`, `D_i` = time-decayed sum of positive relevance with a fixed cutoff `t_cut` (never wall-clock), `q_i` = Bayesian-smoothed share of exposures that were positive.
- Items with no positive observation score exactly 0 and are treated as "no collaborative signal" (cold-item policy).
- Deterministic: sort by descending score then ascending index.
- CPU only (NumPy). GPU unnecessary.
- Limitation: a global ranking; ignores the user.

### Content (TF-IDF)
- Input: positive-history item indices. Output: cosine of the L2-normalised sum of history vectors with all item vectors, `float32 [N]`.
- Features: title words (`t:`), title bigrams (`tb:`), genres (`g:`), release decade (`d:`); binary tf; `idf = ln((1+N)/(1+df)) + 1`; block weights from config; L2 normalisation.
- **New catalogue items:** tokenise `title` and `genres` with `content_tokens`, drop tokens absent from `vocabulary`, weight by `block_weight * idf`, L2-normalise (`content_vectors`). The notebook tests that vectors rebuilt from the JSON vocabulary and `content_idf.npy` reproduce the stored rows, and that a brand-new item yields a valid vector and genre-consistent neighbours.
- CPU: SciPy sparse. GPU: optional, rarely beneficial.
- Limitation: MovieLens offers only titles and genres. Richer metadata needs a licensed source and an identifier mapping. Tokens unseen at fit time are ignored; an item with no known tokens has an all-zero vector.

### ItemKNN
- Input: positive-history item indices. Output: `score_i = sum_j S[j, i]` over history items `j`, `float32 [N]`.
- `S` is CSR `[N, N]`, top-`k` neighbours per row, cosine over positive interactions (optionally user-down-weighted) with shrinkage `n_ij / (n_ij + s)`. Values are non-negative, no self-similarity, finite. No dense matrix exists at any stage.
- CPU: SciPy sparse matrix product. GPU: optional.
- Limitation: rows of items with fewer than `min_item_support` training positives are empty.

### ALS
- Input: positive history with relevance. Output: `Y @ x_u`, `float32 [N]`.
- User representation by **fold-in** with fixed item factors: `x_u = (Y^T Y + sum_i (c_ui - 1) y_i y_i^T + lambda I)^-1 sum_i c_ui y_i`, `c_ui = 1 + alpha * relevance_ui`. `alpha`, `lambda` are in `als_config.json`.
- Only item factors are exported. MovieLens user factors are never exported or used.
- Dimensions: `[N, F]`, `F = item_factor_columns`. Fold-in cost is one `F x F` solve.
- CPU: NumPy. GPU: optional batched scoring (`U @ Y.T`) with resident factors.
- Limitation: a user with no positives has `x_u = 0`; the recommender falls back to popularity.

### BPR (production-gated)
- Item factors `[N, F+1]`: columns `[:, :-1]` latent, column `[:, -1]` item bias. Score `u . v_i + b_i`.
- User vector by fold-in: Adam on the pairwise BPR loss with item factors frozen; negatives uniform and never from the history; deterministic seed `seed + sum(positive indices) mod 1000003`. Averaging item factors is **not** BPR inference and is not used.
- `production_enabled` is true only if fold-in validation NDCG@10 reached the configured fraction of popularity and the fold-in loss decreased. Otherwise BPR is exported for diagnostics but excluded from the hybrid.
- Limitation: fold-in is approximate and iterative (about 100 Adam steps on at most 100 positives).

### Attention
- Inputs: `history` int64 `[batch, max_history]`, `candidates` int64 `[batch, num_candidates]`. Ids are `item_index + 1`; `0` is padding. History is the last `max_history` **positive** items, chronological, right-aligned, left-padded.
- Output: `scores` float32 `[batch, num_candidates]`. Unnormalised logits; comparable only within one request.
- Architecture `target_aware_sequential_attention_v2`: item and positional embeddings, candidate-conditioned multi-head attention, gated fusion, GELU MLP head, per-item bias. Dimensions in `attention_config.json`.
- Canonical weights: `attention.safetensors` (best sampled-validation checkpoint). Inference graph: `attention.onnx`; batch and candidate axes are dynamic, history length is fixed at `max_history`.
- Parity: PyTorch vs ONNX Runtime max absolute difference is tested on padded, partially padded, full and empty histories; tolerances are `1e-4` (CPU) and `2e-3` (CUDA) in fp32.
- Cold-item policy: scores of items with `popularity_scores == 0` are replaced by the candidate-pool minimum.
- CPU: ONNX Runtime CPU. GPU: ONNX Runtime CUDA (verify the active provider; do not assume).
- Limitation: it is a re-ranker. It scores the candidate pool, not the full catalogue.

### Hybrid
- `hybrid_config.json` (versioned): feedback thresholds, candidate sources and pool size, scoring models, normalisation (`minmax`, `zscore` or `rank`), weights (sum to 1), cold-item policy, MMR (`lambda`, depth), fallbacks.
- Procedure: see `inference_architecture.md`.
- Weights are the result of a validation-set random search. They are not described as optimal.

## 8. Items outside the index

Items added to the database after training have no row in any index-based artifact. They can receive a content vector (section 7) but the reference recommender serves only indexed items. Serving new items before the next retrain is a backend decision (for example, a content-only candidate source built with the new-item procedure). Do not extrapolate collaborative scores for them.

## 9. Compatibility

| Component | CPU | GPU |
|---|---|---|
| popularity, content, ItemKNN | NumPy / SciPy | not needed |
| ALS, BPR | NumPy fold-in and scoring | optional batched scoring |
| attention | ONNX Runtime CPU | ONNX Runtime CUDA (optional) |
| hybrid | NumPy fusion and MMR | not needed |

GPU is optional. The notebook records the actual execution provider and benchmarks CPU against GPU; for small requests CPU may be faster.

## 10. Security

- No unsafe deserialization of model files.
- Extract archives only with a safe extractor (no absolute paths, `..`, symlinks, or oversized expansion). `reference_inference.safe_extract_zip` does this.
- SHA-256 detects accidental corruption only. A trusted signature over `manifest.json` must be verified before activation (`model_deployment.md`).
