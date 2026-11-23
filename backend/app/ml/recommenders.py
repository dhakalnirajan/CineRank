"""
All recommendation algorithms in one place.
Designed for fast CPU inference and easy swapping.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import joblib
import torch
import torch.nn as nn
import torch.nn.functional as F

from app.core.config import settings


# ---------------------------------------------------------------------------
# Base interface
# ---------------------------------------------------------------------------
class BaseRecommender:
    name: str = "base"

    def fit(self, train_mat: csr_matrix, **kwargs):
        raise NotImplementedError

    def recommend(
        self,
        user_idx: int,
        k: int = 10,
        filter_seen: bool = True,
        seen: Optional[set] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return (item_indices, scores)"""
        raise NotImplementedError

    def save(self, path: Path):
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: Path):
        return joblib.load(path)


# ---------------------------------------------------------------------------
# 1. Popularity
# ---------------------------------------------------------------------------
class PopularityRecommender(BaseRecommender):
    name = "popularity"

    def __init__(self):
        self.scores: Optional[np.ndarray] = None
        self.ranking: Optional[np.ndarray] = None

    def fit(self, train_mat: csr_matrix, **kwargs):
        self.scores = np.asarray(train_mat.sum(axis=0)).ravel()
        self.ranking = np.argsort(-self.scores)
        return self

    def recommend(self, user_idx: int, k: int = 10, filter_seen: bool = True, seen=None):
        if seen is None:
            seen = set()
        recs, scores = [], []
        for i in self.ranking:
            if not filter_seen or i not in seen:
                recs.append(i)
                scores.append(float(self.scores[i]))
            if len(recs) >= k:
                break
        return np.array(recs), np.array(scores)


# ---------------------------------------------------------------------------
# 2. Content-based (TF-IDF on title + genres)
# ---------------------------------------------------------------------------
class ContentRecommender(BaseRecommender):
    name = "content"

    def __init__(self):
        self.tfidf: Optional[TfidfVectorizer] = None
        self.item_vectors = None
        self.n_items: int = 0

    def fit(self, train_mat: csr_matrix, movie_texts: List[str] = None, **kwargs):
        self.n_items = train_mat.shape[1]
        if movie_texts is None:
            movie_texts = [""] * self.n_items
        self.tfidf = TfidfVectorizer(max_features=4000, stop_words="english")
        self.item_vectors = self.tfidf.fit_transform(movie_texts)
        return self

    def recommend(self, user_idx: int, k: int = 10, filter_seen: bool = True, seen=None):
        if seen is None:
            seen = set()
        # For pure content we need history vectors – caller should pass profile
        # Fallback: return most similar to global average (cold-start safe)
        profile = np.asarray(self.item_vectors.mean(axis=0)).ravel()
        sims = cosine_similarity(profile.reshape(1, -1), self.item_vectors).ravel()
        ranking = np.argsort(-sims)
        recs, scores = [], []
        for i in ranking:
            if not filter_seen or i not in seen:
                recs.append(i)
                scores.append(float(sims[i]))
            if len(recs) >= k:
                break
        return np.array(recs), np.array(scores)

    def recommend_from_history(
        self, history_item_idxs: List[int], k: int = 10, filter_seen: bool = True
    ):
        if not history_item_idxs:
            return self.recommend(0, k=k, filter_seen=False)
        profile = self.item_vectors[history_item_idxs].mean(axis=0)
        sims = cosine_similarity(profile, self.item_vectors).ravel()
        ranking = np.argsort(-sims)
        seen = set(history_item_idxs)
        recs, scores = [], []
        for i in ranking:
            if not filter_seen or i not in seen:
                recs.append(i)
                scores.append(float(sims[i]))
            if len(recs) >= k:
                break
        return np.array(recs), np.array(scores)


# ---------------------------------------------------------------------------
# 3. Item-Item kNN (simple cosine on implicit matrix)
# ---------------------------------------------------------------------------
class ItemKNNRecommender(BaseRecommender):
    name = "itemknn"

    def __init__(self, k_neighbors: int = 50):
        self.k_neighbors = k_neighbors
        self.sim_matrix: Optional[csr_matrix] = None
        self.train_mat: Optional[csr_matrix] = None

    def fit(self, train_mat: csr_matrix, **kwargs):
        self.train_mat = train_mat
        # Item-item cosine (items as columns)
        item_mat = train_mat.T.tocsr()
        # Normalize
        norms = np.sqrt(item_mat.multiply(item_mat).sum(axis=1)).A1
        norms[norms == 0] = 1.0
        item_mat = item_mat.multiply(1.0 / norms[:, None])
        self.sim_matrix = (item_mat @ item_mat.T).tocsr()
        return self

    def recommend(self, user_idx: int, k: int = 10, filter_seen: bool = True, seen=None):
        if seen is None:
            seen = set(self.train_mat[user_idx].indices)
        user_items = self.train_mat[user_idx].indices
        if len(user_items) == 0:
            # fallback popularity-like
            scores = np.asarray(self.train_mat.sum(axis=0)).ravel()
            ranking = np.argsort(-scores)
        else:
            scores = np.asarray(self.sim_matrix[user_items].sum(axis=0)).ravel()
            ranking = np.argsort(-scores)
        recs, scs = [], []
        for i in ranking:
            if not filter_seen or i not in seen:
                recs.append(i)
                scs.append(float(scores[i]))
            if len(recs) >= k:
                break
        return np.array(recs), np.array(scs)


# ---------------------------------------------------------------------------
# 4. ALS (via implicit library – fast)
# ---------------------------------------------------------------------------
class ALSRecommender(BaseRecommender):
    name = "als"

    def __init__(self, factors: int = 32, iterations: int = 15, reg: float = 0.01):
        self.factors = factors
        self.iterations = iterations
        self.reg = reg
        self.model = None
        self.train_mat = None

    def fit(self, train_mat: csr_matrix, **kwargs):
        from implicit.als import AlternatingLeastSquares
        self.train_mat = train_mat
        self.model = AlternatingLeastSquares(
            factors=self.factors,
            regularization=self.reg,
            iterations=self.iterations,
            random_state=42,
            use_gpu=False,  # CPU for portability
        )
        self.model.fit(train_mat.T)
        return self

    def recommend(self, user_idx: int, k: int = 10, filter_seen: bool = True, seen=None):
        ids, scores = self.model.recommend(
            user_idx,
            self.train_mat[user_idx],
            N=k,
            filter_already_liked_items=filter_seen,
        )
        return np.array(ids), np.array(scores)


# ---------------------------------------------------------------------------
# 5. BPR
# ---------------------------------------------------------------------------
class BPRRecommender(BaseRecommender):
    name = "bpr"

    def __init__(self, factors: int = 32, iterations: int = 40, lr: float = 0.01):
        self.factors = factors
        self.iterations = iterations
        self.lr = lr
        self.model = None
        self.train_mat = None

    def fit(self, train_mat: csr_matrix, **kwargs):
        from implicit.bpr import BayesianPersonalizedRanking
        self.train_mat = train_mat
        self.model = BayesianPersonalizedRanking(
            factors=self.factors,
            learning_rate=self.lr,
            iterations=self.iterations,
            random_state=42,
            use_gpu=False,
        )
        self.model.fit(train_mat.T)
        return self

    def recommend(self, user_idx: int, k: int = 10, filter_seen: bool = True, seen=None):
        ids, scores = self.model.recommend(
            user_idx,
            self.train_mat[user_idx],
            N=k,
            filter_already_liked_items=filter_seen,
        )
        return np.array(ids), np.array(scores)


# ---------------------------------------------------------------------------
# 6. Tiny Attention Sequential Model (trains ≤10 min)
# ---------------------------------------------------------------------------
class TinyAttentionModel(nn.Module):
    """
    Lightweight target-aware attention over user history (DIN-style).
    Designed to train in a few minutes on CPU / free Colab GPU.
    """

    def __init__(self, n_items: int, emb_dim: int = 32, max_hist: int = 20):
        super().__init__()
        self.item_emb = nn.Embedding(n_items + 1, emb_dim, padding_idx=0)
        self.attn = nn.Sequential(
            nn.Linear(emb_dim * 2, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )
        self.out = nn.Linear(emb_dim, 1)
        self.max_hist = max_hist
        self.emb_dim = emb_dim

    def forward(self, hist: torch.Tensor, target: torch.Tensor):
        # hist: [B, L], target: [B]
        h = self.item_emb(hist)                     # [B, L, D]
        t = self.item_emb(target).unsqueeze(1)      # [B, 1, D]
        t_exp = t.expand_as(h)
        attn_in = torch.cat([h, t_exp], dim=-1)
        scores = self.attn(attn_in).squeeze(-1)     # [B, L]
        mask = (hist != 0).float()
        scores = scores.masked_fill(mask == 0, -1e9)
        alpha = torch.softmax(scores, dim=-1)
        ctx = torch.bmm(alpha.unsqueeze(1), h).squeeze(1)
        return self.out(ctx).squeeze(-1)


class AttentionRecommender(BaseRecommender):
    name = "attention"

    def __init__(self, emb_dim: int = 32, max_hist: int = 20):
        self.emb_dim = emb_dim
        self.max_hist = max_hist
        self.model: Optional[TinyAttentionModel] = None
        self.n_items: int = 0
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.user_histories: Dict[int, List[int]] = {}

    def fit(self, train_mat: csr_matrix, epochs: int = 8, batch_size: int = 256, lr: float = 1e-3, **kwargs):
        self.n_items = train_mat.shape[1]
        self.model = TinyAttentionModel(self.n_items, self.emb_dim, self.max_hist).to(self.device)
        opt = torch.optim.Adam(self.model.parameters(), lr=lr)

        # Build user histories (most recent first, limited length)
        coo = train_mat.tocoo()
        user_items: Dict[int, List[int]] = {}
        for u, i in zip(coo.row, coo.col):
            user_items.setdefault(int(u), []).append(int(i))
        for u, items in user_items.items():
            self.user_histories[u] = items[-self.max_hist:]

        # Simple BPR-style training on positives + random negatives
        pos_pairs = list(zip(coo.row, coo.col))
        n_pos = len(pos_pairs)

        self.model.train()
        for epoch in range(epochs):
            np.random.shuffle(pos_pairs)
            total_loss = 0.0
            n_batches = 0
            for start in range(0, n_pos, batch_size):
                batch = pos_pairs[start : start + batch_size]
                if len(batch) < 8:
                    continue
                users = [p[0] for p in batch]
                pos_items = [p[1] for p in batch]
                neg_items = np.random.randint(1, self.n_items + 1, size=len(batch)).tolist()

                # Build padded histories
                hist_list = []
                for u in users:
                    h = self.user_histories.get(u, [])
                    # remove the positive if present (simple leave-one-out style)
                    h = [x for x in h if x != pos_items[users.index(u)]][: self.max_hist]
                    pad = [0] * (self.max_hist - len(h))
                    hist_list.append(pad + h)

                hist_t = torch.tensor(hist_list, dtype=torch.long, device=self.device)
                pos_t = torch.tensor(pos_items, dtype=torch.long, device=self.device)
                neg_t = torch.tensor(neg_items, dtype=torch.long, device=self.device)

                pos_score = self.model(hist_t, pos_t)
                neg_score = self.model(hist_t, neg_t)
                loss = -F.logsigmoid(pos_score - neg_score).mean()

                opt.zero_grad()
                loss.backward()
                opt.step()
                total_loss += loss.item()
                n_batches += 1

            avg = total_loss / max(n_batches, 1)
            print(f"[Attention] Epoch {epoch+1}/{epochs}  loss={avg:.4f}")

        self.model.eval()
        return self

    def recommend(self, user_idx: int, k: int = 10, filter_seen: bool = True, seen=None):
        if self.model is None:
            return np.array([]), np.array([])
        hist = self.user_histories.get(user_idx, [])
        if seen is None:
            seen = set(hist)
        # Score a candidate pool (top popular + random for diversity)
        # For speed we score a limited set; in production use ANN
        n_cand = min(2000, self.n_items)
        candidates = list(range(1, n_cand + 1))
        if filter_seen:
            candidates = [c for c in candidates if c not in seen][:1500]

        hist_pad = ([0] * (self.max_hist - len(hist)) + hist[-self.max_hist :])
        hist_t = torch.tensor([hist_pad] * len(candidates), dtype=torch.long, device=self.device)
        cand_t = torch.tensor(candidates, dtype=torch.long, device=self.device)

        with torch.no_grad():
            scores = self.model(hist_t, cand_t).cpu().numpy()

        top_idx = np.argsort(-scores)[:k]
        return np.array([candidates[i] for i in top_idx]), scores[top_idx]

    def save(self, path: Path):
        path = Path(path)
        torch.save(
            {
                "state_dict": self.model.state_dict(),
                "n_items": self.n_items,
                "emb_dim": self.emb_dim,
                "max_hist": self.max_hist,
                "user_histories": self.user_histories,
            },
            path,
        )

    @classmethod
    def load(cls, path: Path):
        data = torch.load(path, map_location="cpu", weights_only=False)
        obj = cls(emb_dim=data["emb_dim"], max_hist=data["max_hist"])
        obj.n_items = data["n_items"]
        obj.user_histories = data["user_histories"]
        obj.model = TinyAttentionModel(obj.n_items, obj.emb_dim, obj.max_hist)
        obj.model.load_state_dict(data["state_dict"])
        obj.model.eval()
        obj.device = torch.device("cpu")
        return obj


# ---------------------------------------------------------------------------
# 7. Hybrid
# ---------------------------------------------------------------------------
class HybridRecommender(BaseRecommender):
    name = "hybrid"

    def __init__(self, models: List[BaseRecommender], weights: Optional[List[float]] = None):
        self.models = models
        self.weights = weights or [1.0 / len(models)] * len(models)

    def fit(self, train_mat: csr_matrix, **kwargs):
        for m in self.models:
            if not hasattr(m, "scores") and not hasattr(m, "model"):
                m.fit(train_mat, **kwargs)
        return self

    def recommend(self, user_idx: int, k: int = 10, filter_seen: bool = True, seen=None):
        score_dict: Dict[int, float] = {}
        for model, w in zip(self.models, self.weights):
            try:
                ids, scores = model.recommend(user_idx, k=100, filter_seen=filter_seen, seen=seen)
                for i, s in zip(ids, scores):
                    score_dict[int(i)] = score_dict.get(int(i), 0.0) + w * float(s)
            except Exception:
                continue
        ranked = sorted(score_dict.items(), key=lambda x: -x[1])[:k]
        if not ranked:
            return np.array([]), np.array([])
        return np.array([r[0] for r in ranked]), np.array([r[1] for r in ranked])
