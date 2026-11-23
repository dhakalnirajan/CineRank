import sys, numpy as np, scipy.sparse as sp, tempfile, zipfile, os
from pathlib import Path
sys.path.insert(0, ".")
import reference_inference as R

rng = np.random.default_rng(0)
# topk determinism and exclusion
s = np.array([1,3,3,3,2,0,-np.inf,np.nan], dtype=np.float32)
assert R.topk_indices(s,2).tolist()==[1,2], R.topk_indices(s,2)
assert R.topk_indices(s,3,exclude=[1]).tolist()==[2,3,4]
assert R.topk_indices(s,20).tolist()==[1,2,3,4,0,5]

# content tokens / vectorisation round trip
t = R.content_tokens("Matrix, The (1999)", "Action|Sci-Fi")
assert "g:sci_fi" in t and "d:1990s" in t and "t:matrix" in t and "t:the" not in t, t
docs = [R.content_tokens("Toy Story (1995)","Animation|Children"), R.content_tokens("Toy Story 2 (1999)","Animation|Children"),
        R.content_tokens("Heat (1995)","Action|Crime"), R.content_tokens("Alien (1979)","Horror|Sci-Fi")]
vocab, idf = R.fit_content_vocabulary(docs, {"t":1,"tb":1,"g":1,"d":1}, 1000)
bw = {"t":1.0,"tb":0.7,"g":1.5,"d":0.5}
V = R.content_vectors(docs, vocab, idf, bw)
norms = np.sqrt(np.asarray(V.multiply(V).sum(1)).ravel()); assert np.allclose(norms,1,atol=1e-5)
new = R.content_vectors([R.content_tokens("Toy Story 3 (2010)","Animation|Children")], vocab, idf, bw)
sim = (new @ V.T).toarray()[0]; assert sim.argmax() in (0,1), sim
unk = R.content_vectors([R.content_tokens("zzz qqq", "")], vocab, idf, bw); assert unk.nnz==0

# ALS fold-in solves the normal equations
Y = rng.normal(size=(50,8)).astype(np.float32); G = R.als_gram(Y)
idx = np.array([3,7,9,20]); rel = np.array([.9,.6,1,.7],dtype=np.float32); a,reg=40.0,0.1
x = R.als_fold_in(Y,G,idx,rel,a,reg).astype(np.float64)
# brute force with full dense Cu
c = np.ones(50); c[idx] = 1+a*rel; p = np.zeros(50); p[idx]=1
Yd = Y.astype(np.float64); xb = np.linalg.solve(Yd.T@np.diag(c)@Yd + reg*np.eye(8), Yd.T@np.diag(c)@p)
assert np.allclose(x,xb,atol=1e-4), (x,xb)
assert np.all(R.als_fold_in(Y,G,[],[],a,reg)==0)

# BPR fold-in: deterministic, finite, prefers positives, negatives never positives
F = rng.normal(size=(200,9)).astype(np.float32)
pos = np.arange(10,30)
F[pos,:-1] += 1.0   # make positives share a direction
u1,d1 = R.bpr_fold_in(F,pos,pos,seed=1,return_diagnostics=True); u2 = R.bpr_fold_in(F,pos,pos,seed=1)
assert np.array_equal(u1,u2) and np.isfinite(u1).all() and d1["loss_end"]<d1["loss_start"], d1
sc = R.bpr_scores(F,u1)[0]; assert sc[pos].mean() > sc[100:].mean()

# normalisation
S = np.array([[1,2,3,99],[5,5,5,5]],dtype=np.float32); Vd = np.array([[1,1,1,0],[1,1,1,1]],bool)
mm = R.normalize_scores(S,Vd,"minmax"); assert np.allclose(mm[0],[0,.5,1,0],atol=1e-6) and np.isfinite(mm).all()
rk = R.normalize_scores(S,Vd,"rank"); assert rk[0,2]>rk[0,1]>rk[0,0] and rk[0,3]==0
z = R.normalize_scores(S,Vd,"zscore"); assert np.isfinite(z).all()
rr = R.normalize_scores(S,Vd,"rrf"); assert rr[0,2]>rr[0,0]
# fusion with per-row availability
fused = R.fuse_scores({"a":np.array([[1.,0.]]),"b":np.array([[0.,1.]])},{"a":.5,"b":.5},{"b":np.array([False])})
assert np.allclose(fused,[[1.,0.]]), fused
# MMR: duplicate-ish items get pushed down
Vm = sp.csr_matrix(np.array([[1,0],[1,0.001],[0,1],[.7,.7]],dtype=np.float32))
Vm = R._row_normalize(Vm)
order = R.mmr_rerank(np.array([1.0,.95,.5,.4]), np.arange(4), Vm, 3, 0.5, depth=4)
assert order[0]==0 and order[1]!=1, order
assert R.mmr_rerank(np.array([1.0,.95,.5,.4]), np.arange(4), Vm, 3, 1.0, depth=4).tolist()==[0,1,2]

# pad_histories
ph = R.pad_histories([[4,5],[],[1,2,3,4,5,6]],4)
assert ph.tolist()==[[0,0,5,6],[0,0,0,0],[4,5,6,7]], ph

# checksums + safe extract
with tempfile.TemporaryDirectory() as td:
    d = Path(td)/"rel"; d.mkdir(); (d/"a.json").write_text("{}"); (d/"b.npy").write_bytes(b"123")
    R.write_sha256sums(d); assert R.verify_sha256sums(d)==2
    (d/"a.json").write_text("{ }")
    try: R.verify_sha256sums(d); raise SystemExit("tamper undetected")
    except ValueError: pass
    (d/"a.json").write_text("{}"); (d/"extra").write_text("x")
    try: R.verify_sha256sums(d); raise SystemExit("extra undetected")
    except ValueError: pass
    z = Path(td)/"bad.zip"
    with zipfile.ZipFile(z,"w") as zf: zf.writestr("../evil.txt","x")
    try: R.safe_extract_zip(z, Path(td)/"o"); raise SystemExit("traversal undetected")
    except ValueError: pass
    z2 = Path(td)/"ok.zip"
    with zipfile.ZipFile(z2,"w") as zf: zf.writestr("backend/artifacts/x.json","{}")
    R.safe_extract_zip(z2, Path(td)/"o2"); assert (Path(td)/"o2/backend/artifacts/x.json").is_file()
print("reference_inference unit checks passed")
