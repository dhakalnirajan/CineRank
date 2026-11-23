# CineRank model training and release workflow

## Notebooks

- `train_all_models.ipynb` is the current offline training, temporal evaluation and model-release workflow. Run it top to bottom in a controlled training environment with the required MovieLens data and pinned dependencies.
- `CineRank Training v1.ipynb` and `CineRank Training v2.ipynb` are earlier experiment notebooks retained for historical comparison. They are not the production serving implementation.

Notebook outputs were cleared in this source handoff to avoid stale run logs and to keep the notebooks reproducible. They do not constitute current model evaluation evidence.

## Shipped inference release

The immutable serving release is in `../artifacts/models/releases/`. Its `manifest.json` identifies the release and `SHA256SUMS` verifies every artifact. The package includes the model release and the sanitized catalogue seed, but excludes local production databases and private training-run directories.

The production inference implementation is `../app/ml/cinerank_inference/` and the service adapter is `../app/ml/release_registry.py`. It loads a release once per API process, checks hashes and shapes, maps MovieLens provider item IDs to database titles, and never queries the database itself.

## Verification helpers

`verification/` contains notebook structure and inference-parity helpers. For example:

```bash
cd backend/training/verification
python harness.py ../train_all_models.ipynb
python verify_fast_inference.py ../../artifacts/models/releases
```

The full ONNX runtime parity check requires the pinned runtime dependencies. A successful source-level or unit test run is not a substitute for running the real release on the deployment runtime.

## Release discipline

Do not overwrite the active release in place. Train to a new candidate directory, evaluate against a temporal holdout, verify checksums and model parity, compare with the active release, then activate the immutable candidate through the documented deployment procedure. The scheduled application worker does not train or promote models.
