"""Exercises real notebook cells on tiny SYNTHETIC data. No ALS/BPR fit, no attention optimizer step."""
import json, os, sys, time, shutil, types, traceback
import numpy as np, pandas as pd
NB_PATH = sys.argv[1] if len(sys.argv) > 1 else "../train_all_models.ipynb"
import tempfile
SCR = os.environ.get("CINERANK_HARNESS_WS") or os.path.join(tempfile.mkdtemp(prefix="cinerank_ws_"), "w")
shutil.rmtree(SCR, ignore_errors=True); os.makedirs(SCR)
os.environ["CINERANK_WORKSPACE"] = SCR
nb = json.load(open(NB_PATH))
cells = {i: "".join(c["source"]) for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code"}
def find(marker):
    hits = [i for i, s in cells.items() if marker in s]
    assert len(hits) == 1, (marker, hits)
    return cells[hits[0]]
G = {"__name__": "__main__"}
def run(marker):
    t = time.time()
    try:
        exec(compile(find(marker), f"<cell:{marker[:30]}>", "exec"), G)
    except Exception:
        print("FAILED cell:", marker); traceback.print_exc(); sys.exit(1)
    print(f"ok  {marker[:48]:50s} {time.time()-t:5.1f}s", flush=True)

for m in ["CONFIG_NAMES = [n for n", "def set_seed", "REFERENCE_INFERENCE_SRC =", "Refusing to overwrite existing directory"]:
    run(m)
# keep tests quick
G["HYBRID_WEIGHT_TRIALS"] = 60
for m in ["def build_split", "def make_evalset", "def accuracy_metrics", "def fit_popularity", "def build_itemknn",
          "def _kwargs_for", "def fit_bpr", "class TargetAwareSequentialAttention", "def train_attention"]:
    run(m)

# ---------------- synthetic MovieLens-like data ----------------
rng = np.random.default_rng(0)
NU, NI = 400, 500
ids = (np.arange(NI) * 10 + 7).astype(np.int64)
genres_all = ["Action", "Comedy", "Drama", "Sci-Fi", "Crime", "Romance", "Horror", "Animation"]
words = ["night", "star", "love", "city", "dark", "run", "lost", "king", "road", "dream", "war", "last"]
movies_df = pd.DataFrame({"movieId": ids,
    "title": [f"{words[i%12].title()} {words[(i*7)%12].title()} {i//12} ({1950 + i % 70})" for i in range(NI)],
    "genres": ["|".join(rng.choice(genres_all, size=rng.integers(1, 4), replace=False)) for _ in range(NI)]})
U_f = rng.normal(size=(NU, 6)); I_f = rng.normal(size=(NI, 6)); pop = rng.pareto(1.5, NI) + 1
rows = []
for u in range(NU):
    n = int(rng.integers(8, 90))
    p = np.exp(U_f[u] @ I_f.T) * pop; p /= p.sum()
    its = rng.choice(NI, size=n, replace=False, p=p)
    aff = U_f[u] @ I_f[its].T
    r = np.clip(np.round((3 + aff * 0.8 + rng.normal(0, .7, n)) * 2) / 2, 0.5, 5)
    t = np.sort(rng.integers(1_000_000_000, 1_600_000_000, n))
    rows += [(u, i, rr, tt) for i, rr, tt in zip(its, r, t)]
df = pd.DataFrame(rows, columns=["u", "i", "r", "t"]).sort_values(["u", "t", "i"], kind="stable")
_u, _i, _r, _t = (df.u.to_numpy(np.int32), df.i.to_numpy(np.int32), df.r.to_numpy(np.float32), df.t.to_numpy(np.int64))
G.update(source_movie_ids=ids, n_items=NI)
split = G["build_split"](_u, _i, _r, _t, G["POSITIVE_RATING_THRESHOLD"], G["MIN_POSITIVES_FOR_EVAL"])
G["ev"] = types.SimpleNamespace(user=_u, item=_i, rating=_r, ts=_t, n_items=NI, **split)
ev = G["ev"]
G["train_pos_mask"] = ev.train_mask & ev.is_pos
G["item_pos_count"] = np.bincount(ev.item[G["train_pos_mask"]], minlength=NI).astype(np.int64)
G["eval_user_ids"] = np.flatnonzero(ev.test_order >= 0)
G["SAMPLING_INFO"] = {"sampling": "synthetic harness"}
G["DATA_SUMMARY"] = {"n_users": NU, "synthetic": True}
G["DATASET_INFO"] = {"name": "SYNTHETIC", "url": "n/a", "directory": "n/a", "archive_sha256": "n/a"}
G["movies_df"] = movies_df
G["ENVIRONMENT"] = G["ENVIRONMENT"]
print("eval users:", len(G["eval_user_ids"]))
run("positive-only matrices:")
run("MODELS = types.SimpleNamespace")
run('with model_stage("content")')
# stand-ins for fitted models (NOT trained): ItemKNN via the real builder on the tiny matrix, random factors
S, _ = G["build_itemknn"](G["train_bin"], "user_idf", 50, 10.0, 256, 2)
G["itemknn_topk"] = G["truncate_topk_rows"](S, 20); G["MODELS"].knn = G["itemknn_topk"]
G["SELECTED"]["itemknn"] = {"weighting": "user_idf", "shrinkage": 10.0, "k": 20, "ndcg@10": 0.0}
G["STAGES"]["itemknn"] = {"status": "available"}
Y = rng.normal(0, .3, (NI, 16)).astype(np.float32); R = G["ref"]
G["MODELS"].als_Y, G["MODELS"].als_gram, G["MODELS"].als_reg = Y, R.als_gram(Y), 0.05
G["SELECTED"]["als"] = {"factors": 16, "iterations": 15, "ndcg@10": 0.0}; G["STAGES"]["als"] = {"status": "available"}
G["TRAINING_RECORDS"]["als_foldin_check"] = {"synthetic": True}
Yb = rng.normal(0, .3, (NI, 17)).astype(np.float32)
G["MODELS"].bpr_Y = Yb; G["MODELS"].bpr_fold = {**G["BPR_FOLDIN_FIXED"], "learning_rate": 0.05, "iterations": 30}
G["STAGES"]["bpr"] = {"status": "available"}; G["BPR_PRODUCTION_ENABLED"] = True
G["TRAINING_RECORDS"]["bpr_gate"] = {"synthetic": True}
# random-init attention weights; NO optimizer step
import torch
torch.manual_seed(0)
cfg = {"n_items": NI, "embed_dim": 32, "n_heads": 4, "max_history": 16, "hidden_dim": 64}
model = G["TargetAwareSequentialAttention"](**cfg, dropout=0.1).eval()
G["attention_model"] = model; G["DEVICE"] = torch.device("cpu")
G["attn_best_state"] = {k: v.detach().clone() for k, v in model.state_dict().items()}
G["attn_final_state"] = {k: v.detach().clone() for k, v in model.state_dict().items()}
G["STAGES"]["attention"] = {"status": "available"}
G["ATTENTION_TRAINING"] = {"model_config": cfg, "time_budget_sec": 600.0, "elapsed_wall_clock_sec": -1.0, "budget_respected": True,
    "budget_overrun_sec": 0.0, "optimizer_steps": 0, "examples_processed": 0, "training_examples_available": 0, "epochs_completed_fraction": 0.0,
    "precision": "none (synthetic stand-in)", "device": "cpu", "stop_reason": "synthetic",
    "best_checkpoint": {"step": 0, "ndcg@10": 0.0, "hr@10": 0.0, "val_loss": 0.0}, "untrained_baseline_validation": {"ndcg@10": 0.0}}
for m in ["FULL_MODELS =", "def fast_ndcg10", "_TEST_EVALUATED", "def describe_file", 'with model_stage("export"',
          'with model_stage("artifact_validation"', 'BENCHMARKS = {"environment"', "def df_to_md", 'with model_stage("package"', "report_lines ="]:
    run(m)
print("\nALL SYNTHETIC-HARNESS CELLS PASSED")
