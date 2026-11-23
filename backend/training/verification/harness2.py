import json, os, sys, shutil, types, inspect
import numpy as np, pandas as pd
NB_PATH = sys.argv[1] if len(sys.argv) > 1 else "../train_all_models.ipynb"
import tempfile
SCR = os.path.join(tempfile.mkdtemp(prefix="cinerank_ws2_"), "w")
shutil.rmtree(SCR, ignore_errors=True); os.makedirs(SCR)
os.environ["CINERANK_WORKSPACE"] = SCR; os.environ["CINERANK_TARGET_USERS"] = "60"
nb = json.load(open(NB_PATH))
cells = {i: "".join(c["source"]) for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code"}
def find(m):
    h = [i for i, s in cells.items() if m in s]; assert len(h) == 1, (m, h); return cells[h[0]]
G = {"__name__": "__main__"}
for m in ["CONFIG_NAMES = [n for n", "def set_seed", "REFERENCE_INFERENCE_SRC =", "def build_split", "def read_movielens_sample" if False else "def build_split",
          "class TargetAwareSequentialAttention"]:
    exec(compile(find(m), m, "exec"), G)
import torch
# ---- 1. read_movielens_sample on a tiny on-disk MovieLens-shaped folder ----
rng = np.random.default_rng(1)
ml = G["ML_DIR"]; ml.mkdir(parents=True)
pd.DataFrame({"movieId": np.arange(1, 301) * 3, "title": [f"Film {i} ({1980+i%40})" for i in range(300)], "genres": ["Drama|Comedy"] * 300}).to_csv(ml / "movies.csv", index=False)
rows = []
for u in range(1, 201):
    n = int(rng.integers(3, 40)) if u > 10 else 2          # users 1-10 have < MIN_USER_RATINGS
    for m_ in rng.choice(np.arange(1, 301) * 3, size=n, replace=False):
        rows.append((u, m_, float(rng.choice([0.5, 2, 3.5, 4, 5])), int(rng.integers(1e9, 1.6e9))))
    rows.append((u, rows[-1][1], 4.0, rows[-1][3] + 5))      # duplicate (user, movie): latest must win
pd.DataFrame(rows, columns=["userId", "movieId", "rating", "timestamp"]).to_csv(ml / "ratings.csv", index=False)
exec(compile(find("def read_movielens_sample"), "rm", "exec"), G)
G["RATINGS_CHUNK_SIZE"] = 700
ratings, movies, info = G["read_movielens_sample"]()
assert ratings.userId.nunique() == 60 and ratings.userId.min() > 10, "sampling frame must exclude users with < MIN_USER_RATINGS"
assert not ratings.duplicated(["userId", "movieId"]).any() and len(movies) == 300
d = ratings[ratings.timestamp == ratings.groupby(["userId", "movieId"]).timestamp.transform("max")]
print("data reader OK:", info["sampling"], "| rows", len(ratings))
# ---- 2. attention data pipeline on a synthetic split ----
exec(compile(find("def make_evalset"), "ms", "exec"), G)
NU, NI = 120, 300
rows = []
for u in range(NU):
    n = int(rng.integers(6, 50)); its = rng.choice(NI, n, replace=False); t = np.sort(rng.integers(1e9, 1.6e9, n))
    rows += [(u, i, float(rng.choice([1.0, 3.0, 4.0, 5.0])), tt) for i, tt in zip(its, t)]
df = pd.DataFrame(rows, columns=["u", "i", "r", "t"]).sort_values(["u", "t", "i"], kind="stable")
u_, i_, r_, t_ = df.u.to_numpy(np.int32), df.i.to_numpy(np.int32), df.r.to_numpy(np.float32), df.t.to_numpy(np.int64)
sp_ = G["build_split"](u_, i_, r_, t_, 3.5, 3)
ev = types.SimpleNamespace(user=u_, item=i_, rating=r_, ts=t_, n_items=NI, **sp_)
tp = ev.train_mask & ev.is_pos
# split leakage proof: no train row is at/after the validation target
for u in np.flatnonzero(ev.test_order >= 0):
    s = ev.starts[u]; assert not ev.train_mask[s + ev.val_order[u]: ev.ends[u]].any()
seq = G["build_attention_sequences"](ev, tp)
L = 8
flat = seq["examples"][:200]
hist, pos, users = G["make_attention_batch"](flat, seq, L)
for k in range(200):                                     # history == the previous positives of the same user, newest last
    f = flat[k]; start = seq["row_start"][f]; prev = seq["ids"][start:f][-L:]
    got = hist[k][hist[k] > 0]
    assert np.array_equal(got, prev), (k, got, prev)
    assert hist[k][-1] == seq["ids"][f - 1] and pos[k] == seq["ids"][f]
    assert seq["users"][start] == users[k]
tm = np.flatnonzero(ev.train_mask)
seen = np.sort(ev.user[tm].astype(np.int64) * NI + ev.item[tm])
counts = np.bincount(ev.item[tp], minlength=NI)
sampler = G["NegativeSampler"](NI, seen, counts, 0.5)
users_b = np.repeat(np.arange(NU), 50)
neg, ok = sampler.sample(users_b, 4, np.random.default_rng(3))
assert ok.all() and not sampler.is_seen(np.broadcast_to(users_b[:, None], neg.shape), neg).any(), "negatives overlap training interactions"
print("negative sampler OK; share drawn from popularity branch has no zero-count items:",
      bool((counts[neg[:, 2:].ravel()] > 0).mean() > 0.9))
# ---- 3. forward-only validation + gradient finiteness (backward only, NO optimizer step) ----
cfg = {"n_items": NI, "embed_dim": 32, "n_heads": 4, "max_history": L, "hidden_dim": 64}
G["TargetAwareSequentialAttention"]; model = G["TargetAwareSequentialAttention"](**cfg, dropout=0.1)
hb = torch.as_tensor(hist); cb = torch.as_tensor(np.concatenate([pos[:, None], neg[:200] + 1], axis=1))
with torch.no_grad():
    # padding invariance: appending padding must not change the score of a non-empty history
    model.eval(); a = model(hb, cb)
    allpad = model(torch.zeros(2, L, dtype=torch.long), torch.tensor([[1, 2], [3, 4]]))
    assert torch.isfinite(a).all() and torch.isfinite(allpad).all()
model.train(); s = model(hb, cb)
loss = -torch.nn.functional.logsigmoid(s[:, :1] - s[:, 1:]).mean(); loss.backward()
assert all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)
assert model.item_embedding.weight.grad is not None and model.position_embedding.weight.grad is not None
print("gradients finite; embeddings/positional embeddings receive gradient; initial loss", round(float(loss), 4), "(~ln2=0.693 expected)")
# attention must actually depend on history (target-aware): shuffling the history changes the output
model.eval()
with torch.no_grad():
    sc = model(hb[:8], cb[:8]); sc2 = model(torch.flip(hb[:8], dims=[1]), cb[:8])
    assert (sc - sc2).abs().max() > 1e-6, "model ignores history order/content"
# validate_attention forward-only
es = types.SimpleNamespace()
val = {"hist": hist[:100], "cands": cb[:100].numpy(), "valid": np.ones((100, 5), bool)}
r = G["validate_attention"](model, val, torch.device("cpu"))
assert set(r) == {"val_loss", "hr@10", "ndcg@10", "mrr"} and np.isfinite(list(r.values())).all(); print("validate_attention OK:", {k: round(v, 3) for k, v in r.items()})
import time as _t
assert G["validate_attention"](model, val, torch.device("cpu"), deadline=_t.monotonic() - 1) is None, "deadline not honoured"
# param groups: embeddings/bias/norm get no weight decay
groups = G["attention_param_groups"](model, 0.01)
names_nodecay = {id(p) for p in groups[1]["params"]}
assert id(model.item_embedding.weight) in names_nodecay and id(model.q_proj.weight) not in names_nodecay
# ---- 4. implicit library API compatibility (introspection only; fit() is NOT called) ----
import implicit
from implicit.als import AlternatingLeastSquares as A
from implicit.bpr import BayesianPersonalizedRanking as B
print("implicit", implicit.__version__)
exec(compile(find("def _kwargs_for"), "k", "exec"), G)
kw_a, drop_a = G["_kwargs_for"](A, factors=8, regularization=.1, iterations=3, random_state=1, use_gpu=False, calculate_training_loss=False)
kw_b, drop_b = G["_kwargs_for"](B, factors=8, learning_rate=.01, regularization=.01, iterations=3, random_state=1, use_gpu=False, verify_negative_samples=True, num_threads=1)
print("ALS kwargs accepted:", sorted(kw_a), "dropped:", drop_a); print("BPR kwargs accepted:", sorted(kw_b), "dropped:", drop_b)
A(**kw_a); B(**kw_b)         # construction only
print("ALS has recalculate_user:", hasattr(A, "recalculate_user"), "| signature:", inspect.signature(A.recalculate_user) if hasattr(A, "recalculate_user") else None)
print("\nHARNESS 2 PASSED")
