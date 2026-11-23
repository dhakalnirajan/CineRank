"""CineRank reference inference (NumPy / SciPy; onnxruntime is optional).

This file is the single source of truth for the inference contract. The training
notebook embeds it verbatim, executes it, and tests the release artifacts with it.
The backend may copy it or re-implement it; any re-implementation must match
the behaviour documented in backend/docs/ml/model_artifacts.md.

Rules:
  * No pickle, no joblib. np.load is always called with allow_pickle=False.
  * Item indices are positions in item_provider_ids.npy. The backend maps
    provider ids to permanent CineRank title ids through its own database.
  * All functions are deterministic for identical inputs.
"""
import hashlib
import json
import math
import re
import time
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import scipy.sparse as sp

SCHEMA_VERSION = 1

MODEL_FILES = {
    "popularity": ["popularity_scores.npy", "popularity_config.json"],
    "content": ["content_item_vectors.npz", "content_idf.npy", "content_config.json"],
    "itemknn": ["itemknn_topk.npz", "itemknn_config.json"],
    "als": ["als_item_factors.npy", "als_config.json"],
    "bpr": ["bpr_item_factors.npy", "bpr_config.json"],
    "attention": ["attention.safetensors", "attention.onnx", "attention_config.json"],
    "hybrid": ["hybrid_config.json"],
}
ITEM_ID_FILE = "item_provider_ids.npy"
ALWAYS_PRESENT = ["manifest.json", "SHA256SUMS", ITEM_ID_FILE]


# --------------------------------------------------------------------------
# Feedback semantics
# --------------------------------------------------------------------------
def rating_to_relevance(rating):
    """Map an explicit rating in [0.5, 5.0] to a strength in [0, 1]."""
    r = np.asarray(rating, dtype=np.float32)
    return np.clip((r - 0.5) / 4.5, 0.0, 1.0).astype(np.float32)


# --------------------------------------------------------------------------
# Deterministic ranking helpers
# --------------------------------------------------------------------------
def topk_indices(scores, k, exclude=None):
    """Top-k indices of a 1-D score vector.

    Order: descending score, ties broken by ascending index. Excluded and
    non-finite entries are never returned. May return fewer than k indices.
    """
    s = np.array(scores, dtype=np.float32, copy=True).ravel()
    s[~np.isfinite(s)] = -np.inf
    if exclude is not None and len(exclude):
        s[np.asarray(exclude, dtype=np.int64)] = -np.inf
    k = int(min(k, s.size))
    if k <= 0:
        return np.zeros(0, dtype=np.int64)
    kth = np.partition(s, s.size - k)[s.size - k]
    greater = np.flatnonzero(s > kth)
    ties = np.flatnonzero(s == kth)[: k - greater.size]
    cand = np.concatenate([greater, ties])
    cand = cand[np.isfinite(s[cand])]
    order = np.lexsort((cand, -s[cand]))
    return cand[order].astype(np.int64)


# --------------------------------------------------------------------------
# Content-based TF-IDF (own tokenizer; no sklearn needed at inference)
# --------------------------------------------------------------------------
CONTENT_STOPWORDS = frozenset(
    "a an and are as at be by for from has he her his in is it its of on or that the "
    "their there this to was were will with".split()
)
_YEAR_RE = re.compile(r"\((\d{4})\)\s*$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_text(text):
    text = unicodedata.normalize("NFKD", str(text if text is not None else ""))
    return text.encode("ascii", "ignore").decode("ascii").lower()


def split_title_year(title):
    title = str(title if title is not None else "").strip()
    m = _YEAR_RE.search(title)
    if m:
        return title[: m.start()].strip(), int(m.group(1))
    return title, None


def content_tokens(title, genres, year=None):
    """Tokens for one catalogue item. Prefixes: t: title word, tb: title bigram,
    g: genre, d: decade. Output is a sorted list of unique tokens."""
    clean_title, parsed_year = split_title_year(title)
    if year is None:
        year = parsed_year
    words = [w for w in _NON_ALNUM.split(normalize_text(clean_title))
             if w and w not in CONTENT_STOPWORDS and (len(w) > 1 or w.isdigit())]
    tokens = {"t:" + w for w in words}
    tokens.update("tb:" + a + "_" + b for a, b in zip(words, words[1:]))
    if isinstance(genres, str):
        genre_list = genres.split("|")
    else:
        genre_list = list(genres) if genres is not None else []
    for g in genre_list:
        g = _NON_ALNUM.sub("_", normalize_text(g)).strip("_")
        if g and g != "no_genres_listed":
            tokens.add("g:" + g)
    if year is not None and 1800 <= int(year) <= 2100:
        tokens.add("d:%ds" % (int(year) // 10 * 10))
    return sorted(tokens)


def fit_content_vocabulary(token_lists, min_df_by_prefix, max_features):
    df = {}
    for toks in token_lists:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    kept = [(t, c) for t, c in df.items() if c >= min_df_by_prefix.get(t.split(":", 1)[0], 1)]
    kept.sort(key=lambda x: (-x[1], x[0]))
    kept = kept[: int(max_features)]
    kept.sort(key=lambda x: x[0])
    vocabulary = {t: i for i, (t, _) in enumerate(kept)}
    n = len(token_lists)
    idf = np.asarray([math.log((1.0 + n) / (1.0 + c)) + 1.0 for _, c in kept], dtype=np.float32)
    return vocabulary, idf


def content_vectors(token_lists, vocabulary, idf, block_weights):
    """L2-normalised sparse TF-IDF rows (binary tf). Same code path for training
    items and for new catalogue items at inference time."""
    indptr = [0]
    indices = []
    data = []
    for toks in token_lists:
        row = {}
        for t in set(toks):
            j = vocabulary.get(t)
            if j is None:
                continue
            row[j] = float(block_weights.get(t.split(":", 1)[0], 1.0)) * float(idf[j])
        cols = sorted(row)
        vals = np.asarray([row[c] for c in cols], dtype=np.float64)
        norm = float(np.linalg.norm(vals)) if vals.size else 0.0
        if norm > 0.0:
            vals = vals / norm
        indices.extend(cols)
        data.extend(vals.tolist())
        indptr.append(len(indices))
    return sp.csr_matrix(
        (np.asarray(data, dtype=np.float32), np.asarray(indices, dtype=np.int32),
         np.asarray(indptr, dtype=np.int64)),
        shape=(len(token_lists), len(vocabulary)),
    )


def history_matrix(histories, weights, n_items):
    """Sparse [B x n_items] matrix; row b holds weights[b] at histories[b]."""
    rows, cols, vals = [], [], []
    for b, (items, w) in enumerate(zip(histories, weights)):
        items = np.asarray(items, dtype=np.int64)
        if items.size == 0:
            continue
        w = np.ones(items.size, dtype=np.float32) if w is None else np.asarray(w, dtype=np.float32)
        rows.append(np.full(items.size, b, dtype=np.int64))
        cols.append(items)
        vals.append(w)
    if not rows:
        return sp.csr_matrix((len(histories), n_items), dtype=np.float32)
    return sp.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(len(histories), n_items), dtype=np.float32,
    )


def _row_normalize(m):
    m = m.tocsr().astype(np.float32)
    norms = np.sqrt(np.asarray(m.multiply(m).sum(axis=1)).ravel())
    inv = np.divide(1.0, norms, out=np.zeros_like(norms), where=norms > 0).astype(np.float32)
    return sp.diags(inv) @ m


def content_scores(item_vectors, hist_matrix):
    """Cosine between each user profile (sum of positive-history item vectors) and all items."""
    profile = _row_normalize(hist_matrix @ item_vectors)
    return np.asarray((profile @ item_vectors.T).todense(), dtype=np.float32)


def itemknn_scores(topk_similarity, hist_matrix):
    return np.asarray((hist_matrix @ topk_similarity).todense(), dtype=np.float32)


# --------------------------------------------------------------------------
# ALS fold-in (regularised least squares with fixed item factors)
# --------------------------------------------------------------------------
def als_gram(item_factors):
    y = np.asarray(item_factors, dtype=np.float64)
    return y.T @ y


def als_fold_in(item_factors, gram, item_indices, relevance, alpha, reg):
    """x_u = (Y^T Y + sum_i (c_ui - 1) y_i y_i^T + reg I)^-1 sum_i c_ui y_i ,
    with c_ui = 1 + alpha * relevance_ui over the user's positive items."""
    idx = np.asarray(item_indices, dtype=np.int64)
    f = item_factors.shape[1]
    if idx.size == 0:
        return np.zeros(f, dtype=np.float32)
    y = np.asarray(item_factors[idx], dtype=np.float64)
    c = 1.0 + float(alpha) * np.asarray(relevance, dtype=np.float64)
    a = gram + (y.T * (c - 1.0)) @ y + float(reg) * np.eye(f)
    b = y.T @ c
    return np.linalg.solve(a, b).astype(np.float32)


# --------------------------------------------------------------------------
# BPR fold-in (item factors fixed; only the user vector is optimised)
# item_factors layout (implicit library): [:, :-1] latent factors, [:, -1] item bias.
# --------------------------------------------------------------------------
def bpr_fold_in(item_factors, positive_items, seen_items, n_iterations=100, learning_rate=0.05,
                reg=0.01, negatives_per_positive=3, seed=0, max_positives=100,
                return_diagnostics=False):
    v = item_factors[:, :-1]
    bias = item_factors[:, -1]
    n_items, f = v.shape
    pos = np.unique(np.asarray(positive_items, dtype=np.int64))
    if pos.size > max_positives:
        pos = pos[-max_positives:]
    if pos.size == 0:
        u0 = np.zeros(f, dtype=np.float32)
        return (u0, {"loss_start": None, "loss_end": None}) if return_diagnostics else u0
    seen = np.unique(np.asarray(seen_items, dtype=np.int64))
    rng = np.random.default_rng(int(seed))
    u = rng.normal(0.0, 0.01, f)
    m = np.zeros(f)
    s = np.zeros(f)
    pos_rep = np.repeat(pos, int(negatives_per_positive))
    vp = np.asarray(v[pos_rep], dtype=np.float64)
    bp = np.asarray(bias[pos_rep], dtype=np.float64)
    losses = []
    for t in range(1, int(n_iterations) + 1):
        neg = rng.integers(0, n_items, size=pos_rep.size)
        for _ in range(10):
            hit = np.isin(neg, seen)
            if not hit.any():
                break
            neg[hit] = rng.integers(0, n_items, size=int(hit.sum()))
        keep = ~np.isin(neg, seen)
        if not keep.any():
            break
        dv = vp[keep] - np.asarray(v[neg[keep]], dtype=np.float64)
        db = bp[keep] - np.asarray(bias[neg[keep]], dtype=np.float64)
        x = dv @ u + db
        losses.append(float(np.mean(np.logaddexp(0.0, -x)) + 0.5 * reg * float(u @ u)))
        g = -1.0 / (1.0 + np.exp(np.clip(x, -50.0, 50.0)))
        grad = (g[:, None] * dv).mean(axis=0) + reg * u
        m = 0.9 * m + 0.1 * grad
        s = 0.999 * s + 0.001 * grad * grad
        u = u - learning_rate * (m / (1 - 0.9 ** t)) / (np.sqrt(s / (1 - 0.999 ** t)) + 1e-8)
    u32 = u.astype(np.float32)
    if return_diagnostics:
        head = float(np.mean(losses[:5])) if losses else None
        tail = float(np.mean(losses[-5:])) if losses else None
        return u32, {"loss_start": head, "loss_end": tail}
    return u32


def bpr_seed(base_seed, positive_items):
    """Deterministic per-history seed so identical histories always fold in identically."""
    return int(base_seed) + int(np.sum(np.asarray(positive_items, dtype=np.int64)) % 1000003)


def bpr_scores(item_factors, user_vectors):
    u = np.atleast_2d(np.asarray(user_vectors, dtype=np.float32))
    return (u @ item_factors[:, :-1].T + item_factors[:, -1][None, :]).astype(np.float32)


# --------------------------------------------------------------------------
# Score normalisation, fusion, diversity
# --------------------------------------------------------------------------
def normalize_scores(scores, valid, method="minmax", rrf_k=60.0, eps=1e-9):
    """Row-wise normalisation of [B x C] scores. Invalid entries map to the row
    minimum of the normalised range. Methods: minmax, zscore, rank, rrf."""
    s = np.asarray(scores, dtype=np.float64)
    valid = np.asarray(valid, dtype=bool)
    s = np.where(valid, s, 0.0)
    has = valid.any(axis=1, keepdims=True)
    if method == "minmax":
        lo = np.where(valid, s, np.inf).min(axis=1, keepdims=True)
        hi = np.where(valid, s, -np.inf).max(axis=1, keepdims=True)
        lo = np.where(has, lo, 0.0)
        hi = np.where(has, hi, 0.0)
        out = (s - lo) / (hi - lo + eps)
        return np.where(valid, out, 0.0).astype(np.float32)
    if method == "zscore":
        n = np.maximum(valid.sum(axis=1, keepdims=True), 1)
        mean = np.where(valid, s, 0.0).sum(axis=1, keepdims=True) / n
        var = np.where(valid, (s - mean) ** 2, 0.0).sum(axis=1, keepdims=True) / n
        z = (s - mean) / np.sqrt(var + eps)
        zmin = np.where(valid, z, np.inf).min(axis=1, keepdims=True)
        zmin = np.where(has, zmin, 0.0)
        return np.where(valid, z, zmin).astype(np.float32)
    if method in ("rank", "rrf"):
        key = np.where(valid, -s, np.inf)
        order = np.argsort(key, axis=1, kind="stable")
        ranks = np.empty_like(order)
        np.put_along_axis(ranks, order, np.arange(s.shape[1])[None, :].repeat(s.shape[0], 0), axis=1)
        if method == "rank":
            nvalid = np.maximum(valid.sum(axis=1, keepdims=True), 1)
            out = 1.0 - ranks / nvalid
        else:
            out = 1.0 / (rrf_k + ranks + 1.0)
        return np.where(valid, out, 0.0).astype(np.float32)
    raise ValueError("unknown normalisation method: %r" % (method,))


def fuse_scores(normalized, weights, row_available=None):
    """Weighted sum of normalised score matrices. A model unavailable for a row
    is dropped for that row and the remaining weights are renormalised."""
    num = None
    den = None
    for name, w in weights.items():
        if name not in normalized or float(w) <= 0.0:
            continue
        mat = np.asarray(normalized[name], dtype=np.float64)
        if row_available is not None and name in row_available:
            a = np.asarray(row_available[name], dtype=np.float64).reshape(-1, 1)
        else:
            a = np.ones((mat.shape[0], 1))
        num = float(w) * a * mat if num is None else num + float(w) * a * mat
        den = float(w) * a if den is None else den + float(w) * a
    if num is None:
        raise ValueError("no model with a positive weight is available for fusion")
    out = np.zeros_like(num)
    np.divide(num, np.broadcast_to(den, num.shape), out=out, where=np.broadcast_to(den > 0, num.shape))
    return out.astype(np.float32)


def mmr_rerank(scores, candidate_items, item_vectors, k, lam, depth=50):
    """Maximal Marginal Relevance over the top `depth` candidates.

    Returns positions into `scores`. lam=1 keeps the relevance order.
    Similarity is content cosine (item_vectors rows are L2-normalised)."""
    scores = np.asarray(scores, dtype=np.float64)
    candidate_items = np.asarray(candidate_items, dtype=np.int64)
    depth = int(min(depth, scores.size))
    top = topk_indices(scores, depth)
    if lam >= 1.0 or item_vectors is None or top.size <= 1:
        return top[:k]
    s = scores[top]
    rel = (s - s.min()) / (s.max() - s.min() + 1e-9)
    vec = item_vectors[candidate_items[top]]
    sim = np.asarray((vec @ vec.T).todense(), dtype=np.float64)
    selected = [0]
    remaining = list(range(1, top.size))
    max_sim = sim[0].copy()
    while len(selected) < min(k, top.size):
        cand = np.asarray(remaining)
        value = lam * rel[cand] - (1.0 - lam) * max_sim[cand]
        j = int(cand[int(np.argmax(value))])
        selected.append(j)
        remaining.remove(j)
        max_sim = np.maximum(max_sim, sim[j])
    return top[np.asarray(selected, dtype=np.int64)]


# --------------------------------------------------------------------------
# Attention helpers (ONNX Runtime)
# --------------------------------------------------------------------------
def pad_histories(histories, max_history):
    """Right-aligned, left-padded int64 [B x max_history]. Ids are item_index + 1; 0 is padding."""
    out = np.zeros((len(histories), max_history), dtype=np.int64)
    for i, h in enumerate(histories):
        h = np.asarray(h, dtype=np.int64)[-max_history:]
        if h.size:
            out[i, max_history - h.size:] = h + 1
    return out


def make_ort_session(onnx_path, use_gpu=False):
    import onnxruntime as ort
    available = ort.get_available_providers()
    if use_gpu and "CUDAExecutionProvider" in available:
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    else:
        providers = ["CPUExecutionProvider"]
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(onnx_path), sess_options=options, providers=providers)


def attention_scores_onnx(session, history_ids, candidate_ids):
    out = session.run(["scores"], {
        "history": np.ascontiguousarray(history_ids, dtype=np.int64),
        "candidates": np.ascontiguousarray(candidate_ids, dtype=np.int64),
    })
    return out[0]


# --------------------------------------------------------------------------
# Release integrity and safe loading
# --------------------------------------------------------------------------
def file_sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def write_sha256sums(directory):
    directory = Path(directory)
    lines = []
    for p in sorted(directory.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS":
            lines.append("%s  %s" % (file_sha256(p), p.relative_to(directory).as_posix()))
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def verify_sha256sums(directory):
    """Raise ValueError if any listed file is missing/modified or any file is unlisted."""
    directory = Path(directory)
    sums = directory / "SHA256SUMS"
    if not sums.is_file():
        raise ValueError("SHA256SUMS is missing")
    listed = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        listed[name] = digest
    problems = []
    for name, digest in listed.items():
        p = directory / name
        if not p.is_file():
            problems.append("missing file: " + name)
        elif file_sha256(p) != digest:
            problems.append("checksum mismatch: " + name)
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*")
              if p.is_file() and p.name != "SHA256SUMS"}
    for extra in sorted(actual - set(listed)):
        problems.append("unlisted file: " + extra)
    if problems:
        raise ValueError("; ".join(problems))
    return len(listed)


def safe_extract_zip(archive, destination, max_total_bytes=8 * 1024 ** 3, max_files=10000):
    """Extract a ZIP without path traversal, absolute paths, symlinks or zip bombs."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > max_files:
            raise ValueError("archive has too many members")
        if sum(i.file_size for i in infos) > max_total_bytes:
            raise ValueError("archive expands beyond the permitted size")
        for info in infos:
            name = info.filename
            if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name) or ".." in Path(name).parts:
                raise ValueError("unsafe ZIP member path: " + name)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("symlink in archive: " + name)
            target = (destination / name).resolve()
            if target != root and root not in target.parents:
                raise ValueError("unsafe ZIP member path: " + name)
        for info in infos:
            target = (destination / info.filename).resolve()
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                while True:
                    block = src.read(1 << 20)
                    if not block:
                        break
                    dst.write(block)


def _check_finite(name, arr):
    if not np.all(np.isfinite(arr)):
        raise ValueError("%s contains NaN or infinity" % name)


def _check_csr(name, m, shape, dtype=np.float32):
    if not sp.isspmatrix_csr(m):
        raise ValueError("%s is not CSR" % name)
    if m.shape != tuple(shape):
        raise ValueError("%s has shape %s, expected %s" % (name, m.shape, tuple(shape)))
    if m.dtype != dtype:
        raise ValueError("%s has dtype %s, expected %s" % (name, m.dtype, np.dtype(dtype)))
    _check_finite(name, m.data)
    if m.nnz:
        if m.indices.min() < 0 or m.indices.max() >= shape[1]:
            raise ValueError("%s has out-of-range column indices" % name)
    if np.any(np.diff(m.indptr) < 0) or m.indptr[0] != 0 or m.indptr[-1] != m.nnz:
        raise ValueError("%s has an invalid indptr" % name)


class Release:
    """A loaded, validated model release. Arrays are loaded once and kept in memory."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        self.item_provider_ids = np.load(self.directory / ITEM_ID_FILE, allow_pickle=False)
        self.n_items = int(self.item_provider_ids.shape[0])
        self.models = {}
        self.configs = {}
        self.arrays = {}

    def model_available(self, name):
        return self.manifest["models"].get(name, {}).get("status") == "available"

    def model_enabled(self, name):
        entry = self.manifest["models"].get(name, {})
        return entry.get("status") == "available" and bool(entry.get("production_enabled", False))


def load_release(directory, verify_checksums=True, require_complete=True):
    """Load and validate a release directory. Raises ValueError on any problem.
    Production callers use the defaults; the training notebook relaxes both only for a draft release."""
    directory = Path(directory)
    if verify_checksums:
        verify_sha256sums(directory)
    rel = Release(directory)
    man = rel.manifest
    if require_complete and man.get("status") != "complete":
        raise ValueError("release is not marked complete")
    if int(man.get("schema_version", -1)) != SCHEMA_VERSION:
        raise ValueError("unsupported manifest schema_version")
    ids = rel.item_provider_ids
    if ids.ndim != 1 or ids.dtype != np.int64:
        raise ValueError("item_provider_ids must be a 1-D int64 array")
    if np.unique(ids).size != ids.size:
        raise ValueError("item_provider_ids contains duplicates")
    n = rel.n_items
    for name, entry in man["models"].items():
        if entry.get("status") != "available":
            continue
        for fname in MODEL_FILES[name]:
            if not (directory / fname).is_file():
                raise ValueError("%s: missing file %s" % (name, fname))
        if name == "popularity":
            arr = np.load(directory / "popularity_scores.npy", allow_pickle=False)
            if arr.shape != (n,) or arr.dtype != np.float32:
                raise ValueError("popularity_scores shape/dtype mismatch")
            _check_finite("popularity_scores", arr)
            rel.arrays["popularity"] = arr
        elif name == "content":
            cfg = json.loads((directory / "content_config.json").read_text(encoding="utf-8"))
            idf = np.load(directory / "content_idf.npy", allow_pickle=False)
            vec = sp.load_npz(directory / "content_item_vectors.npz").tocsr()
            v = len(cfg["vocabulary"])
            if idf.shape != (v,) or idf.dtype != np.float32:
                raise ValueError("content idf shape/dtype mismatch")
            _check_finite("content_idf", idf)
            _check_csr("content_item_vectors", vec, (n, v))
            rel.arrays["content"] = vec
            rel.arrays["content_idf"] = idf
            rel.configs["content"] = cfg
        elif name == "itemknn":
            cfg = json.loads((directory / "itemknn_config.json").read_text(encoding="utf-8"))
            m = sp.load_npz(directory / "itemknn_topk.npz").tocsr()
            _check_csr("itemknn_topk", m, (n, n))
            if np.any(m.data < 0):
                raise ValueError("itemknn_topk has negative similarities")
            if m.nnz and int(np.diff(m.indptr).max()) > int(cfg["k"]):
                raise ValueError("itemknn_topk has more than k neighbours in a row")
            if m.nnz and np.any(m.indices == np.repeat(np.arange(n), np.diff(m.indptr))):
                raise ValueError("itemknn_topk contains self-similarities")
            rel.arrays["itemknn"] = m
            rel.configs["itemknn"] = cfg
        elif name in ("als", "bpr"):
            cfg = json.loads((directory / (name + "_config.json")).read_text(encoding="utf-8"))
            arr = np.load(directory / (name + "_item_factors.npy"), allow_pickle=False)
            expected = (n, int(cfg["item_factor_columns"]))
            if arr.shape != expected or arr.dtype != np.float32:
                raise ValueError("%s item factors shape/dtype mismatch: %s" % (name, arr.shape))
            _check_finite(name + "_item_factors", arr)
            rel.arrays[name] = arr
            rel.configs[name] = cfg
            if name == "als":
                rel.arrays["als_gram"] = als_gram(arr)
        elif name == "attention":
            cfg = json.loads((directory / "attention_config.json").read_text(encoding="utf-8"))
            if int(cfg["n_items"]) != n:
                raise ValueError("attention n_items does not match item_provider_ids")
            rel.configs["attention"] = cfg
        elif name == "hybrid":
            rel.configs["hybrid"] = json.loads((directory / "hybrid_config.json").read_text(encoding="utf-8"))
    if "hybrid" in rel.configs:
        hc = rel.configs["hybrid"]
        w = hc["weights"]
        if abs(sum(w.values()) - 1.0) > 1e-6:
            raise ValueError("hybrid weights do not sum to 1")
        for m in w:
            if not rel.model_enabled(m):
                raise ValueError("hybrid weights reference unavailable or disabled model: " + m)
    return rel


class CineRankRecommender:
    """Loads a release once and serves recommendations for one user at a time.

    history: sequence of (item_index, rating) ordered oldest -> newest.
    Items are release item indices (positions in item_provider_ids.npy).
    """

    def __init__(self, release_dir, use_gpu=False, disabled_models=(), verify_checksums=True, require_complete=True):
        self.release = load_release(release_dir, verify_checksums=verify_checksums, require_complete=require_complete)
        rel = self.release
        self.hybrid = rel.configs["hybrid"]
        self.disabled = set(disabled_models)
        self.n_items = rel.n_items
        self.popularity = rel.arrays["popularity"]
        self.cold_mask = self.popularity <= 0.0
        self.threshold = float(self.hybrid["feedback"]["positive_rating_threshold"])
        self.session = None
        self.attention_cfg = rel.configs.get("attention")
        if rel.model_enabled("attention") and "attention" not in self.disabled:
            self.session = make_ort_session(rel.directory / "attention.onnx", use_gpu=use_gpu)
        self.attention_provider = self.session.get_providers()[0] if self.session else None

    def _active(self, name):
        return self.release.model_enabled(name) and name not in self.disabled and (
            name != "attention" or self.session is not None)

    def _dense_scores(self, name, pos_items, pos_rel, seen):
        rel = self.release
        n = self.n_items
        if name == "popularity":
            return self.popularity.astype(np.float32)
        if name == "content":
            h = history_matrix([pos_items], [None], n)
            return content_scores(rel.arrays["content"], h)[0]
        if name == "itemknn":
            h = history_matrix([pos_items], [None], n)
            return itemknn_scores(rel.arrays["itemknn"], h)[0]
        if name == "als":
            cfg = rel.configs["als"]
            x = als_fold_in(rel.arrays["als"], rel.arrays["als_gram"], pos_items, pos_rel,
                            cfg["confidence_alpha"], cfg["regularization"])
            return (rel.arrays["als"] @ x).astype(np.float32)
        if name == "bpr":
            cfg = rel.configs["bpr"]
            fi = cfg["fold_in"]
            u = bpr_fold_in(rel.arrays["bpr"], pos_items, seen, fi["iterations"], fi["learning_rate"],
                            fi["regularization"], fi["negatives_per_positive"],
                            bpr_seed(fi["seed"], pos_items), fi["max_positives"])
            return bpr_scores(rel.arrays["bpr"], u)[0]
        raise KeyError(name)

    def recommend(self, history, k=20, exclude=None, return_timings=False):
        t_all = time.perf_counter()
        timings = {}
        n = self.n_items
        items = np.asarray([h[0] for h in history], dtype=np.int64)
        ratings = np.asarray([h[1] for h in history], dtype=np.float32)
        if items.size and (items.min() < 0 or items.max() >= n):
            raise ValueError("history item index out of range")
        # de-duplicate keeping the latest occurrence, preserve chronological order
        if items.size:
            _, last_rev = np.unique(items[::-1], return_index=True)
            keep = np.sort(items.size - 1 - last_rev)
            items, ratings = items[keep], ratings[keep]
        pos_mask = ratings >= self.threshold
        pos_items = items[pos_mask]
        pos_rel = rating_to_relevance(ratings[pos_mask])
        excluded = np.unique(np.concatenate([items, np.asarray(exclude if exclude is not None else [],
                                                                  dtype=np.int64)]))
        used, fallback = [], None

        def finish(idx, scores, tag):
            timings["total_ms"] = (time.perf_counter() - t_all) * 1000.0
            res = {"items": np.asarray(idx, dtype=np.int64), "scores": np.asarray(scores, dtype=np.float32),
                   "models_used": tag, "fallback": fallback}
            if return_timings:
                res["timings_ms"] = timings
            return res

        if pos_items.size == 0:
            fallback = "cold_start_popularity"
            idx = topk_indices(self.popularity, k, excluded)
            return finish(idx, self.popularity[idx], ["popularity"])

        gen_cfg = self.hybrid["candidate_generation"]
        score_models = [m for m in self.hybrid["scoring_models"] if self._active(m)]
        generators = [m for m in gen_cfg["sources"] if self._active(m)]
        if not generators or not score_models:
            fallback = "popularity_only"
            idx = topk_indices(self.popularity, k, excluded)
            return finish(idx, self.popularity[idx], ["popularity"])
        dense = {}
        for name in set(score_models) | set(generators):
            if name == "attention":
                continue
            t0 = time.perf_counter()
            dense[name] = self._dense_scores(name, pos_items, pos_rel, items)
            timings[name + "_ms"] = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        pool = np.unique(np.concatenate(
            [topk_indices(dense[g], int(gen_cfg["per_source"]), excluded) for g in generators]))
        timings["pool_ms"] = (time.perf_counter() - t0) * 1000.0
        if pool.size == 0:
            fallback = "empty_pool_popularity"
            idx = topk_indices(self.popularity, k, excluded)
            return finish(idx, self.popularity[idx], ["popularity"])
        pool_scores = {}
        for name in score_models:
            if name == "attention":
                t0 = time.perf_counter()
                hist = pad_histories([pos_items], self.attention_cfg["max_history"])
                s = attention_scores_onnx(self.session, hist, (pool + 1)[None, :])[0].astype(np.float64)
                cold = self.cold_mask[pool]
                if cold.any() and (~cold).any():
                    s[cold] = s[~cold].min()
                pool_scores[name] = s
                timings["attention_ms"] = (time.perf_counter() - t0) * 1000.0
            else:
                pool_scores[name] = dense[name][pool].astype(np.float64)
        t0 = time.perf_counter()
        valid = np.ones((1, pool.size), dtype=bool)
        normed = {m: normalize_scores(pool_scores[m][None, :], valid, self.hybrid["normalization"])
                  for m in score_models}
        fused = fuse_scores(normed, self.hybrid["weights"])[0]
        mmr = self.hybrid["mmr"]
        vectors = self.release.arrays.get("content") if mmr["enabled"] and self._active("content") else None
        pos = mmr_rerank(fused, pool, vectors, k, float(mmr["lambda"]), int(mmr["candidate_depth"]))
        timings["fusion_mmr_ms"] = (time.perf_counter() - t0) * 1000.0
        out_items = pool[pos]
        if out_items.size < k:
            fallback = "pool_smaller_than_k"
            extra = topk_indices(self.popularity, k + out_items.size, np.concatenate([excluded, out_items]))
            out_items = np.concatenate([out_items, extra])[:k]
            return finish(out_items, np.zeros(out_items.size), score_models)
        return finish(out_items, fused[pos], score_models)
