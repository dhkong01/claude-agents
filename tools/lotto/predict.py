import json, numpy as np
from pathlib import Path

DIR = Path(__file__).parent / "data"
ml_path  = DIR / "lotto_ml_features.json"
ana_path = DIR / "lotto_analysis.json"

if ml_path.exists():
    ml = json.load(open(ml_path, encoding="utf-8"))
    coh      = np.array(ml["number_coherence"])
    nb       = np.array([float(ml["neighbor_bonus"][str(i)]) for i in range(1,46)])
    hot      = set(ml["hot"])
    gap_top  = set(ml["gap_ranks"])
    rec_odd  = ml["rec_odd"]
    top_pairs = {(min(p[0],p[1]), max(p[0],p[1])): c for p,c in ml["top_pairs"]}
    last_draw = ml["last_draw"]
    use_ml   = True
else:
    ana  = json.load(open(ana_path, encoding="utf-8"))
    hist = json.load(open(DIR/"lotto_history.json", encoding="utf-8"))
    coh  = np.array([ana["weights"][str(i)] for i in range(1,46)])
    nb   = np.ones(45)
    hot, gap_top, rec_odd, top_pairs = set(ana["hot"]), set(), ana["rec_odd"], {}
    last_draw = hist["last_draw"]
    use_ml   = False

CORE_THRESH = 0.70

# 종합 점수
score = coh * nb
score += np.array([0.05 if (i+1) in hot     else 0.0 for i in range(45)])
score += np.array([0.03 if (i+1) in gap_top else 0.0 for i in range(45)])
score /= score.sum()

ranked = sorted(range(1,46), key=lambda i: -score[i-1])
core   = [n for n in ranked if coh[n-1] >= CORE_THRESH]   # 고신뢰 핵심
supp   = [n for n in ranked if coh[n-1] <  CORE_THRESH]   # 보조
pool   = (core + supp)[:20]

# 홀짝 제약 만족 최적 6개
best, best_s = None, -1
for ot in [rec_odd, rec_odd-1, rec_odd+1]:
    if not (0 <= ot <= 6): continue
    odds  = [n for n in pool if n%2==1]
    evens = [n for n in pool if n%2==0]
    if len(odds) < ot or len(evens) < (6-ot): continue
    combo = sorted(odds[:ot] + evens[:6-ot])
    s = sum(score[n-1] for n in combo)
    ns = sorted(combo)
    for i in range(len(ns)):
        for j in range(i+1, len(ns)):
            if (ns[i], ns[j]) in top_pairs: s += 0.01 * top_pairs[(ns[i], ns[j])]
    if s > best_s: best_s, best = s, combo

if best is None:
    best = sorted(pool[:6])

bonus = int(max((i for i in range(1,46) if i not in best),
                key=lambda i: float(score[i-1])))

core_in  = [n for n in best if coh[n-1] >= CORE_THRESH]
supp_in  = [n for n in best if coh[n-1] <  CORE_THRESH]
core_coh = float(np.mean([coh[n-1] for n in core_in])) * 100 if core_in else 0.0
all_coh  = float(np.mean([coh[n-1] for n in best])) * 100

out = {
    "draw":             int(last_draw) + 1,
    "predicted":        [int(n) for n in best],
    "bonus":            bonus,
    "core_numbers":     [int(n) for n in core_in],
    "core_coherence":   round(core_coh, 1),
    "overall_coherence": round(all_coh, 1),
    "method":           "ML앙상블+부트스트랩" if use_ml else "통계",
    "hot_included":     [int(n) for n in best if n in hot],
    "gap_included":     [int(n) for n in best if n in gap_top],
    "individual_coherence": {str(n): round(float(coh[n-1])*100, 1) for n in best},
}
json.dump(out, open(DIR/"lotto_prediction.json","w",encoding="utf-8"),
          ensure_ascii=False, indent=2)

label = lambda n: f"{n}({round(coh[n-1]*100,1)}%)" + (" ★" if coh[n-1]>=CORE_THRESH else "")
print(f"\n{'='*48}")
print(f" {out['draw']}회 예측  [{out['method']}]")
print(f"{'='*48}")
print(f" 예측 번호 : {[int(n) for n in best]}")
print(f" 보너스    : {bonus}")
print(f"{'─'*48}")
print(f" 핵심 번호 ({len(core_in)}개, 정합성 {core_coh:.1f}%) : {[int(n) for n in core_in]}")
print(f" 보조 번호 ({len(supp_in)}개)          : {[int(n) for n in supp_in]}")
print(f" 전체 정합성                 : {all_coh:.1f}%")
print(f"{'─'*48}")
for n in best:
    tag = "★ 핵심" if coh[n-1] >= CORE_THRESH else "  보조"
    print(f"  {tag} {n:2d}번 : {round(coh[n-1]*100,1):5.1f}%")
print(f"{'─'*48}")
print(f" 핫포함  : {out['hot_included']}")
print(f" Gap포함 : {out['gap_included']}")
print(f"{'='*48}")