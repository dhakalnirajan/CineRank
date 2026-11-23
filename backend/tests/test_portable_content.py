import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.sparse import save_npz
from sklearn.feature_extraction.text import TfidfVectorizer

from app.ml.portable_models import PortableModelRegistry


def _write_checksums(directory: Path):
    lines = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (directory / "SHA256SUMS").write_text("".join(lines))


def test_saved_tfidf_vocabulary_scores_new_titles(tmp_path):
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), dtype=np.float32)
    training_texts = ["batman crime action", "space science fiction", "crime mystery thriller"]
    matrix = vectorizer.fit_transform(training_texts).tocsr().astype(np.float32)
    save_npz(tmp_path / "rec-content-v1.npz", matrix)
    (tmp_path / "rec-content-v1-meta.json").write_text(json.dumps({
        "schema_version": 1,
        "vocabulary": vectorizer.vocabulary_,
        "idf": vectorizer.idf_.astype(float).tolist(),
        "ngram_range": [1, 2], "stop_words": "english", "norm": "l2",
    }))
    (tmp_path / "manifest.json").write_text(json.dumps({
        "bundle_format": "cinerank-portable-v1", "bundle_id": "testbundle",
        "created_at_utc": "test", "n_items": 3, "n_users": 1,
    }))
    (tmp_path / "id-maps-v1.json").write_text(json.dumps({
        "schema_version": 2, "matrix_orientation": "users_by_items",
        "idx_to_source_user_id": [1], "idx_to_movielens_movie_id": [10, 20, 30],
        "source_user_id_to_idx": {"1": 0},
        "movielens_movie_id_to_idx": {"10": 0, "20": 1, "30": 2},
    }))
    _write_checksums(tmp_path)

    registry = PortableModelRegistry(tmp_path)
    registry.load()
    scores = registry.score_cold_start(
        history_indices=[0], history_texts=[],
        candidate_texts=["new batman crime action", "new romance musical"],
    )
    assert scores.shape == (2,)
    assert scores[0] > scores[1]
