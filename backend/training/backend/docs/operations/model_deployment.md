# Model release deployment

Applies to bundles produced by `train_all_models.ipynb`. The backend is not modified by the notebook.

## 1. Compatibility finding (read first)

The previous notebook exported a flat bundle (`rec-*-v1.npz`, `id-maps-v1.json`, `catalogue.csv`, `ratings_sample.csv`, `holdout_sample.csv`, user and item factors) and its text refers to `scripts/import_colab_bundle.py`. The backend repository was not available while this notebook was revised, so that importer was not inspected.

**Expected incompatibility:** an importer written for the old bundle cannot read the new release, by design. The new release has no catalogue CSV, no ratings, no user ids and no user factors, and the layout is `backend/artifacts/models/releases/<release_id>/` with a manifest.

**Smallest compatible correction (proposal, not applied):** add a release loader that (a) reads `manifest.json` and `item_provider_ids.npy`, (b) resolves each provider id to the existing `title_<UUIDv7>` through the database, (c) fails if any indexed provider id has no title, and (d) loads the model files as described in `model_artifacts.md`. No database schema change is needed because the database already owns titles and provider mappings. If the backend previously relied on the importer to create titles from `catalogue.csv`, title import must become a separate step, outside the model release.

## 2. Release contents and trust

A release directory is immutable. `manifest.json` has `status: "complete"` only after the notebook validated every artifact. SHA-256 sums detect corruption; they **do not authenticate who produced the files**.

Required for any release that crosses a machine or storage boundary: publish a detached signature over `manifest.json` (for example minisign, cosign or GPG), distribute the public key through a channel independent of the bundle, and verify the signature before anything else. The manifest hashes every model file and `SHA256SUMS` covers the manifest, so a verified manifest signature plus verified checksums covers the whole release. The notebook writes `signature.status = "unsigned"`; signing is an operational step outside the notebook.

## 3. Activation procedure

1. **Receive** the bundle into a quarantine directory (not the live tree).
2. **Verify signature** of `manifest.json`. Stop on failure.
3. **Safe extract** (no absolute paths, `..`, symlinks, or oversized expansion; `reference_inference.safe_extract_zip`).
4. **Verify checksums** (`reference_inference.verify_sha256sums`): every listed file matches, no unlisted file.
5. **Check completeness:** manifest `status == "complete"`; every model the configuration needs is `available`.
6. **Load with the production loader** (`load_release`): this validates dtypes, shapes, finiteness, sparse structure, index alignment and hybrid weights, using `allow_pickle=False`.
7. **Resolve provider ids** through the database; fail on unmapped indexed ids.
8. **Smoke test** in a separate process: unseen-user recommendation, cold-start fallback, ablations, determinism, and the active ONNX execution provider.
9. **Place** the verified directory under `models/releases/<release_id>/`. Never overwrite an existing release directory.
10. **Activate atomically:** switch a pointer (for example a symlink `models/current -> releases/<release_id>` replaced with `rename`, or a database row) in one operation. Keep the previous pointer value as `last_known_good`.
11. **Reload** workers one at a time, load once per process, and watch error rate and latency.
12. **Never activate** a `draft` release, a release that failed any step above, or a release whose models are partially unavailable unless the configuration explicitly allows that.

## 4. Rollback

Rollback is a pointer swap back to `last_known_good`, followed by worker reload. Retain at least the last known good release and the active one. Do not delete a release that a running process may still have mapped.

## 5. Runtime configuration

- Load each artifact once per process; do not load models per request.
- Select CPU or CUDA for the ONNX session by configuration. After creating the session, log `session.get_providers()[0]`; CUDA counts only when it is `CUDAExecutionProvider`.
- GPU is optional. Re-run the benchmark on production hardware before choosing it; small requests can be faster on CPU.
- Pin BLAS/ONNX thread counts per worker to avoid oversubscription.
- BPR is served only if the manifest marks it `production_enabled`.
- Disabling a model is a configuration change; the hybrid renormalises weights.

## 6. Failure handling

| Failure | Action |
|---|---|
| signature, checksum or loader validation fails | reject the release; keep the current one |
| model file missing or `status: unavailable` | follow the configured fallback chain, or reject if the model is required |
| ONNX session fails or falls back to CPU unexpectedly | log, continue on CPU if acceptable, alert if GPU was required |
| unmapped provider ids | reject the release |
| elevated errors after activation | roll back |

## 7. What the training pipeline refuses to ship

Raw MovieLens ratings, MovieLens user ids, training-user factors, holdout rows, training matrices, a full catalogue CSV, and any database content. The bundle builder scans file names and types before packaging and again after extraction.

## 8. Retraining notes

- Each run creates a new `release_id` and `run_id`; previous releases are untouched.
- The attention model trains for a 600-second wall-clock budget (validation and logging included). The budget is a compute limit; read `evaluation_report.md` for quality.
- Training was designed around MovieLens data. Retraining on CineRank data would need a new data pipeline and a privacy review; this notebook does not read the database.
