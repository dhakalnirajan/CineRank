# Recommendation Models and Release Lifecycle

## Active serving contract

The currently wired API loader serves the immutable v2 release in `artifacts/models/releases/` through `app/ml/release_registry.py` and `app/ml/cinerank_inference/`. The bundle uses a manifest, provider item ID array, model configuration and numerical artifacts. It includes popularity, content, ItemKNN, ALS, BPR and target-aware attention components. Attention is served through ONNX; the associated tensor weights use safetensors. `SHA256SUMS` is verified before the loader accepts the release.

The v2 engine expects MovieLens provider item IDs, not database row offsets and not CineRank `title_id` strings. The recommendation service builds history from current user ratings, watchlist entries and recent interaction signals, calls the model using MovieLens IDs, maps output provider IDs back to `Movie` rows, and returns canonical CineRank IDs with database-owned metadata.

A missing or invalid release makes recommendation readiness fail. The service does not silently load a legacy v1 bundle.

## Model families

| Component | Role | Limitation |
|---|---|---|
| Popularity | Robust non-personalized fallback | Not personalized |
| Content / TF-IDF | Metadata similarity and user preference signal | Only the fitted vocabulary/IDF may be used without retraining |
| ItemKNN | Item neighborhood signal | Requires the item mapping represented by the release |
| ALS | Collaborative latent factor signal | New users require a supported fold-in; new items need factors |
| BPR | Pairwise ranking signal | New users require a supported fold-in; new items need factors |
| Attention | Target/history interaction signal | Candidates must be represented by the release's item index |
| Hybrid rank fusion | Combines model scores and catalogue fallback candidates | Score fusion is a ranking policy, not a probability calibration |

## Runtime candidate and data flow

1. The API reads the user's ratings, watchlist and recent non-impression events from the database.
2. History is converted to MovieLens provider item IDs and preference values. Seen canonical title IDs and provider IDs are separately tracked.
3. The loaded v2 engine scores the available provider-ID candidate space and excludes the user's seen provider IDs.
4. The API maps returned provider IDs to current database `Movie` rows. Unmapped provider IDs are discarded.
5. Current CineRank catalogue popularity candidates are scored from the database's popularity, vote average, vote count and recency fields.
6. The production ranker combines candidate sources, applies seen-item filtering and diversity/ranking rules, then hydrates response metadata from the database.
7. Rating, watchlist and meaningful interaction writes invalidate the user's short-lived recommendation-row cache.

The home response also exposes `popular`, `recently_added` and genre rows. With no history, the model's declared cold-start popularity fallback is used for `for_you`; the separate catalogue rows provide a sensible initial feed. Recent interaction history changes the next request's preference context. The API does not randomly rotate a first item merely to create the appearance of personalization.

New catalogue records without MovieLens mappings cannot be assigned to latent-factor embeddings by inventing an index. They can appear in the live catalogue popularity and recent rows. Treating them as content-ranked candidates requires an explicit, tested implementation that applies the exact release's frozen text transformation and IDF. The current architecture does not claim that arbitrary new rows are already scored by all trained models.

## Release and promotion process

The old v1 trainer/importer and the active v2 release are different artifact contracts. Do not let the old worker promote a v1 bundle into the v2 serving directory. Automatic model refresh in the worker is deliberately disabled.

A release change must be performed offline:

- Train using a pinned and recorded environment.
- Create temporal train/validation/test splits and prevent holdout leakage.
- Evaluate all candidates using common users, candidate sets and seen-item rules.
- Report ranking metrics alongside coverage, diversity, novelty and long-tail exposure.
- Verify unique provider IDs, matrix/tensor shapes, finite values, manifest schema and all hashes.
- Run the exact production loader and test provider-ID to canonical-title mapping.
- Check attention inference and CPU/GPU parity where relevant.
- Stage a new immutable release and activate it only after an explicit decision. Keep the previous release available for rollback.

The daily worker only synchronizes catalogue metadata and rebuilds the catalogue sort index. It does not change model weights. Database leases and heartbeats prevent multiple workers from running the same scheduled job concurrently.


## Serving rank fusion and explicit preferences

The immutable v2 model release performs its own configured hybrid fusion across the enabled model sources. The API then combines the release's candidate list with a current-catalogue popularity list using weighted Reciprocal Rank Fusion:

`RRF(title) = sum_source weight(source) / (rrf_constant + source_rank(title))`

This outer fusion does not compare raw scores from unrelated systems. The fused relevance is normalized within the current candidate pool and passed to genre-aware MMR. The current serving implementation's default RRF constant is 60; source weights are tunable ranking policy, not a claim of optimality.

Explicit user preferences are applied before final ranking: excluded genres, adult-content policy, minimum release year and maximum runtime are hard eligibility constraints when the relevant metadata exists; preferred genres receive a modest within-source score boost. Unknown year/runtime metadata is not silently treated as a positive match when the user has set a corresponding constraint. Preference version is included in the recommendation cache key.
