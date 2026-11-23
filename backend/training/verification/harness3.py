# Library-equivalence check WITHOUT calling fit(): inject random item factors into the real implicit CPU ALS class
import numpy as np, scipy.sparse as sp, json, types, sys
sys.path.insert(0,".")
import importlib; R = importlib.import_module("reference_inference")
from implicit.cpu.als import AlternatingLeastSquares as ALS
rng = np.random.default_rng(0); n_items, f, alpha, reg = 400, 16, 40.0, 0.05
Y = rng.normal(0, .3, (n_items, f)).astype(np.float32)
m = ALS(factors=f, regularization=reg, iterations=1, random_state=0, alpha=1.0, calculate_training_loss=False)
m.item_factors = Y; m.user_factors = np.zeros((3, f), np.float32)
cos=[]
for trial in range(20):
    idx = rng.choice(n_items, size=int(rng.integers(1, 60)), replace=False); rel = R.rating_to_relevance(rng.choice([3.5,4,4.5,5], size=idx.size))
    row = sp.csr_matrix(((1 + alpha*rel).astype(np.float32), (np.zeros(idx.size, int), idx)), shape=(1, n_items))
    lib = np.asarray(m.recalculate_user(0, row)).ravel()
    mine = R.als_fold_in(Y, R.als_gram(Y), idx, rel, alpha, reg)
    cos.append(float(lib @ mine / (np.linalg.norm(lib)*np.linalg.norm(mine)))); 
    assert np.allclose(lib, mine, rtol=1e-3, atol=1e-4), (trial, np.abs(lib-mine).max())
print("fold-in == implicit recalculate_user: min cosine", min(cos), "| max abs diff within 1e-4 on all trials")
