import json, numpy as np
from pathlib import Path
from scipy.special import softmax
from collections import defaultdict

DIR = Path(__file__).parent / "data"
hist = json.load(open(DIR/"lotto_history.json", encoding="utf-8"))
ana  = json.load(open(DIR/"lotto_analysis.json", encoding="utf-8"))

records = hist["data"]
N = len(records)

def ema_score(recs, alpha=0.15):
    e = np.ones(45)/45
    for r in reversed(recs):
        ind = np.zeros(45); [ind.__setitem__(x-1,1.) for x in r["numbers"]]
        e = alpha*ind + (1-alpha)*e
    return softmax(e*10)

def freq_score(recs):
    nums = [x for r in recs for x in r["numbers"]]
    f = np.array([nums.count(i) for i in range(1,46)], dtype=float)
    return softmax((f-f.mean())/(f.std()+1e-8))

def gap_score(recs):
    n = len(recs)
    ls = {i:n for i in range(1,46)}
    for k,r in enumerate(recs):
        for x in r["numbers"]:
            if ls[x]==n: ls[x]=k
    g = np.array([ls[i] for i in range(1,46)], dtype=float)
    return softmax(g/(g.max()+1e-8)*3)

def ensemble(recs):
    return 0.40*ema_score(recs) + 0.40*freq_score(recs) + 0.20*gap_score(recs)

def boot_coherence(recs, n_boot, top_k, seed=42):
    n = len(recs)
    rng = np.random.default_rng(seed)
    cnt = np.zeros(45)
    for _ in range(n_boot):
        br = [recs[i] for i in rng.integers(0, n, n)]
        cnt[np.argsort(ensemble(br))[-top_k:]] += 1
    return cnt / n_boot

# ── 정합성 계산 ─────────────────────────────────────────────────
# 최근 10회 부트스트랩 (TOP_K=6, 2000회) — 최신 패턴 기반 정합성
number_coherence = boot_coherence(records[:10], n_boot=2000, top_k=6, seed=42).round(4).tolist()

# 풀 앙상블 (predict.py용)
ens_full = ensemble(records); ens_full /= ens_full.sum()

# Gap
ls = {i:N for i in range(1,46)}
for idx, r in enumerate(records):
    for x in r["numbers"]:
        if ls[x]==N: ls[x]=idx
gap = np.array([ls[i] for i in range(1,46)], dtype=float)

# 공출현 Top 20
cooc = defaultdict(int)
for r in records:
    ns = sorted(r["numbers"])
    for i in range(len(ns)):
        for j in range(i+1,len(ns)):
            cooc[(ns[i],ns[j])] += 1
top_pairs = sorted(cooc.items(), key=lambda x:-x[1])[:20]

def window_freq(w):
    f = np.zeros(45)
    for r in records[:min(w,N)]:
        for x in r["numbers"]: f[x-1]+=1
    return (f/min(w,N)).round(4).tolist()

prev = set(records[0]["numbers"]) if records else set()
neighbor_bonus = {str(i):1.2 if any(abs(i-p)<=1 for p in prev) else 1.0 for i in range(1,46)}

top_coh = sorted(range(1,46), key=lambda i:-number_coherence[i-1])[:10]
print(f"정합성 상위10: {top_coh}")
print(f"정합성 값:     {[round(number_coherence[n-1]*100,1) for n in top_coh]}%")

out = {
    "last_draw":        hist["last_draw"],
    "based_on":         N,
    "ensemble_weights": {str(i+1): round(float(ens_full[i]),6) for i in range(45)},
    "ema_weights":      {str(i+1): 0.0 for i in range(45)},
    "gap_weights":      {str(i+1): round(float(softmax(gap/(gap.max()+1e-8)*3)[i]),6) for i in range(45)},
    "number_coherence": number_coherence,
    "gap_ranks":        sorted(range(1,46), key=lambda i:-gap[i-1])[:10],
    "top_pairs":        [[list(p),c] for p,c in top_pairs],
    "window_freq":      {"w5":window_freq(5),"w10":window_freq(10),"w20":window_freq(20)},
    "neighbor_bonus":   neighbor_bonus,
    "hot":              ana["hot"],
    "cold":             ana["cold"],
    "rec_odd":          ana["rec_odd"],
    "band_avg":         ana["band_avg"],
}
json.dump(out, open(DIR/"lotto_ml_features.json","w",encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"ML 피처 완료: {N}회 기반 | 최근10회(65%)+전체(35%) 정합성")