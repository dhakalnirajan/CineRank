# Standalone Google Colab Training

## Purpose and dependency boundary

`training/train_all_models.ipynb` is the canonical offline training implementation. It deliberately does not import `app/`, connect to the CineRank SQL database, use TMDB, or invoke either crawler. It downloads MovieLens data, preprocesses a bounded training cohort, trains supported recommenders, validates the artifacts, and exports a portable bundle.

## Dataset selection and sampling

- Source: GroupLens `ml-latest.zip`, the largest standard MovieLens snapshot in the `ratings.csv` / `movies.csv` format used by this pipeline.
- The notebook does not use `ml-20mx16x32.tar`; that archive is not the raw standard ratings/movies input expected here.
- Default `TARGET_USERS=10000`: sample real MovieLens users with a deterministic seed. Set to `None` to retain all users; memory and runtime can increase substantially.
- Default `MIN_MOVIE_RATINGS=20`: filter the sampled ratings to movies with at least this many ratings. Raising the threshold reduces the item universe; lowering it retains more long-tail items and increases model cost.
- Relevance: `(rating - 0.5) / 4.5`, clipped to `[0, 1]`. No synthetic users or synthetic rating noise are added.
- The notebook extracts release year from the MovieLens title string where available.

The sampled-user limit is applied before movie-frequency filtering. Therefore the frequency threshold is evaluated inside the sampled cohort, not against the full 33-million-rating source.

## Temporal holdout and evaluation

For eligible users, the notebook withholds a latest interaction for offline evaluation and trains model weights on the remaining history. `holdout_sample.csv` is included in the bundle for daily Pass@K-style evaluation and 60-day challenger comparison. Users with insufficient history to form both train and holdout examples are not treated as valid holdout cases. Evaluation results must report the actual evaluated user count; an empty/undersized holdout is not evidence of model quality.

## Model families

The notebook trains the model families represented by the portable serving registry: popularity, content/TF-IDF, ItemKNN, implicit ALS, BPR, and attention. The hybrid configuration is stored as model metadata/weights configuration and uses the serving ranker to combine available architecture scores. Exact hyperparameters, feature preparation, matrix orientation, and artifact names are recorded in notebook cells and `manifest.json`.

## Portable artifact contract

The output bundle contains, at minimum:

| Artifact | Purpose |
|---|---|
| `manifest.json` | Format version, dataset/training metadata, bundle identity |
| `SHA256SUMS` | Integrity checks for exported files |
| `id-maps-v1.json` | Model-index mappings to source MovieLens IDs |
| `catalogue.csv` | Training catalogue and source identifiers |
| `ratings_sample.csv` | Sampled real ratings used by the training/import workflow |
| `holdout_sample.csv` | Temporal holdout records for offline evaluation |
| `train-mat-v1.npz` | Sparse training matrix |
| `relevance-mat-v1.npz` | Sparse relevance matrix |
| `rec-pop-v1.npz` | Popularity model data |
| `rec-content-v1.npz`, `rec-content-v1-meta.json` | Content model vectors and vectorizer metadata |
| `rec-itemknn-v1.npz` | Item-neighborhood model data |
| `rec-als-v1.npz` | ALS factors and metadata |
| `rec-bpr-v1.npz` | BPR factors and metadata |
| `rec-attn-v1.pt` | Attention model state |
| `rec-hybrid-v1.json` | Hybrid weighting/configuration |

The importer verifies required files, manifest format, and checksums before importing catalogue/user/rating rows and activating the bundle. The backend creates permanent `title_<UUIDv7>` IDs for catalogue records; model source IDs remain in the model mapping and are not database primary keys.

## Running in Colab

1. Open `training/train_all_models.ipynb` in Google Colab.
2. Select a runtime appropriate for the chosen cohort. GPU acceleration helps the attention model; CPU and RAM requirements still depend on matrix/model sizes.
3. Run cells from top to bottom. Configure `TARGET_USERS`, `MIN_MOVIE_RATINGS`, seed, and output destination in the configuration cell before starting.
4. Wait for the final validation/export cell. Do not interrupt while the ZIP is being written.
5. Download the generated bundle ZIP using the notebook's download cell, or save it to mounted Google Drive if configured.
6. Transfer the ZIP to the backend host and import it using `python scripts/import_colab_bundle.py --bundle path/to/bundle.zip`.

## Local execution

The local runner executes the same notebook with environment overrides and verifies the resulting archive:

```bash
python scripts/prepare_and_train.py --no-import --target-users 10000 --min-movie-ratings 20
```

The runner controls output/data paths through `CINERANK_TRAIN_OUTPUT_DIR`, `CINERANK_TRAIN_DATA_DIR`, and related variables. The notebook remains the canonical implementation; avoid duplicating training logic in `app/`.

## Tuning guidance

- Faster/smaller: `TARGET_USERS=5000`, `MIN_MOVIE_RATINGS=50`.
- Larger cohort: `TARGET_USERS=25000` after confirming RAM and runtime.
- Full MovieLens user population: `TARGET_USERS=None`; expect significantly longer training and larger memory use.
- Long-tail exploration: `MIN_MOVIE_RATINGS=5`; expect a much larger item matrix and higher ItemKNN cost.

Do not assume “under ten minutes” on every Colab tier or hardware. Runtime depends on runtime type, library versions, sampled matrix density, and model hyperparameters.
