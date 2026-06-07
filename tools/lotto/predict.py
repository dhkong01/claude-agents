"""
로또 예측 v3 — 정합성(65%) + 6번호 쌍 조건부 확률(35%) 통합 점수
Game 1: C(25,6)=177,100 전수탐색 → 수학적 최적 보장
Game 2~5: 온도 스케일링 몬테카를로 (다양성)
"""
import json, numpy as np
from pathlib import Path
from itertools import combinations

DIR = Path(__file__).parent / "data"
ml_path  = DIR / "lotto_ml_features.json"
ana_path = DIR / "lotto_analysis.json"

if ml_path.exists():
    ml = json.load(open(ml_path, encoding="utf-8"))
    coh       = np.array(ml["number_coherence"])
    hot       = set(ml["hot"])
    gap_top   = set(ml["gap_ranks"])
    last_draw = ml["last_draw"]
    ss        = ml.get("sum_stats", {})
    SUM_LO    = int(ss.get("p20", 100))
    SUM_HI    = int(ss.get("p80", 175))
    # 조건부 확률 행렬 로드
    cond_prob = np.array(ml.get("cond_prob_matrix", np.zeros((45, 45)).tolist()))
    avg_pair  = ml.get("avg_hist_pair_prob", 0.12)   # 역사적 평균
    rand_pair = ml.get("random_pair_baseline", 0.025) # 무작위 기댓값
    use_ml    = True
else:
    ana  = json.load(open(ana_path, encoding="utf-8"))
    hist = json.load(open(DIR/"lotto_history.json", encoding="utf-8"))
    coh  = np.array([ana["weights"][str(i)] for i in range(1, 46)])
    hot, gap_top = set(ana["hot"]), set()
    last_draw = hist["last_draw"]
    SUM_LO, SUM_HI = 100, 175
    cond_prob = np.zeros((45, 45))
    avg_pair, rand_pair = 0.12, 0.025
    use_ml = False

CORE_THRESH  = 0.65   # 핵심 번호 임계값
N_GAMES      = 5      # 게임 수
N_SAMPLES    = 50000  # 몬테카를로 샘플 수 (Game 2~5)
TOP_N        = 25     # 전수탐색 풀 (C(25,6)=177,100)
TEMP         = 1.5    # 온도 스케일링 지수
COH_WEIGHT   = 0.65   # 정합성 가중치
PAIR_WEIGHT  = 0.35   # 쌍 조건부 확률 가중치

# ── 종합 점수 ──────────────────────────────────────────────────────
score = coh.copy()
score += np.array([0.05 if (i+1) in hot     else 0.0 for i in range(45)])
score += np.array([0.03 if (i+1) in gap_top else 0.0 for i in range(45)])
score = np.clip(score, 0, None)
score /= score.sum()

BANDS = [(1, 9), (10, 19), (20, 29), (30, 39), (40, 45)]

def is_valid(combo):
    s = sum(combo)
    if not (SUM_LO <= s <= SUM_HI):
        return False
    bands_hit = set()
    for n in combo:
        for lo, hi in BANDS:
            if lo <= n <= hi:
                bands_hit.add(lo); break
    if len(bands_hit) < 3:
        return False
    ns = sorted(combo)
    streak = 1
    for i in range(1, len(ns)):
        streak = streak + 1 if ns[i] == ns[i-1] + 1 else 1
        if streak >= 3:
            return False
    return True

def combo_pair_score(combo):
    """6개 번호 조합의 평균 쌍 조건부 확률 P(j|i) — 15쌍 평균"""
    total, n = 0.0, 0
    for i in range(len(combo)):
        for j in range(i+1, len(combo)):
            a, b = combo[i]-1, combo[j]-1
            total += (cond_prob[a][b] + cond_prob[b][a]) / 2
            n += 1
    return total / n if n > 0 else 0.0

def combo_coherence(combo):
    return float(np.mean([coh[n-1] for n in combo]))

def combined_score(combo):
    """정합성(65%) + 6번호 쌍 조건부 확률(35%) 통합 점수"""
    coh_s  = combo_coherence(combo)
    pair_s = combo_pair_score(combo)
    # 쌍 확률 정규화: 역사적 평균의 1.5배를 만점 기준으로
    pair_norm = min(pair_s / max(avg_pair * 1.5, 0.10), 1.0)
    return COH_WEIGHT * coh_s + PAIR_WEIGHT * pair_norm

# ── Game 1: 전수탐색 C(25,6)=177,100 ────────────────────────────
def exhaustive_best(exclude_combos=None):
    """정합성 + 쌍 조건부 확률 통합 점수 기준 전수탐색"""
    top_nums = sorted(range(1, 46), key=lambda i: -score[i-1])[:TOP_N]
    exclude  = set(tuple(sorted(c)) for c in (exclude_combos or []))
    best, best_s = None, -1

    for combo in combinations(top_nums, 6):
        key = tuple(sorted(combo))
        if key in exclude:
            continue
        if not is_valid(combo):
            continue
        s = combined_score(combo)
        if s > best_s:
            best_s, best = s, list(combo)

    return sorted(best) if best else None

# ── Game 2~5: 온도 스케일링 몬테카를로 ───────────────────────────
def monte_carlo_best(n_samples, seed, exclude_combos=None, prev_used=None, diversity=0.35):
    rng     = np.random.default_rng(seed)
    nums    = np.arange(1, 46)
    exclude = set(tuple(sorted(c)) for c in (exclude_combos or []))

    adj_score = score.copy()
    if prev_used:
        for n, cnt in prev_used.items():
            adj_score[n-1] *= (1 - diversity) ** cnt
    adj_score = np.clip(adj_score, 1e-6, None)
    adj_score = adj_score ** TEMP
    adj_score /= adj_score.sum()

    best, best_s = None, -1
    for _ in range(n_samples):
        combo = tuple(sorted(int(x) for x in rng.choice(nums, size=6, replace=False, p=adj_score)))
        if combo in exclude or not is_valid(combo):
            continue
        s = combined_score(combo)
        if s > best_s:
            best_s, best = s, combo

    if best is None:
        for _ in range(n_samples):
            combo = tuple(sorted(int(x) for x in rng.choice(nums, size=6, replace=False, p=adj_score)))
            if combo in exclude:
                continue
            if SUM_LO <= sum(combo) <= SUM_HI:
                s = combined_score(combo)
                if s > best_s:
                    best_s, best = s, combo

    return list(best) if best else None

# ── 5게임 생성 ────────────────────────────────────────────────────
print("Game 1: 전수탐색 C(25,6)=177,100 [정합성+쌍확률 통합]...")
games, all_combos, used_count = [], [], {}

g1 = exhaustive_best()
if g1:
    all_combos.append(g1)
    games.append(g1)
    for n in g1: used_count[n] = used_count.get(n, 0) + 1

print(f"Game 2~{N_GAMES}: 온도스케일링 몬테카를로...")
for g in range(1, N_GAMES):
    combo = monte_carlo_best(N_SAMPLES, seed=g * 137,
                             exclude_combos=all_combos, prev_used=used_count)
    if combo:
        all_combos.append(combo)
        games.append(combo)
        for n in combo: used_count[n] = used_count.get(n, 0) + 1

if not games:
    ranked = sorted(range(1, 46), key=lambda i: -score[i-1])
    games  = [sorted(ranked[:6])]

# ── 게임 메타데이터 ───────────────────────────────────────────────
game_results = []
for combo in games:
    combo   = sorted(combo)
    core_in = [n for n in combo if coh[n-1] >= CORE_THRESH]
    bonus   = int(max(
        (i for i in range(1, 46) if i not in combo),
        key=lambda i: float(score[i-1])
    ))
    ps = combo_pair_score(combo)
    game_results.append({
        "numbers":           [int(n) for n in combo],
        "bonus":             bonus,
        "sum":               int(sum(combo)),
        "odd_count":         sum(1 for n in combo if n % 2 == 1),
        "core_numbers":      [int(n) for n in core_in],
        "core_coherence":    round(float(np.mean([coh[n-1] for n in core_in])) * 100, 1) if core_in else 0.0,
        "overall_coherence": round(combo_coherence(combo) * 100, 1),
        "pair_score":        round(ps * 100, 2),
        "pair_vs_random":    round(ps / rand_pair, 1),
        "combined_score":    round(combined_score(combo) * 100, 1),
        "hot_included":      [int(n) for n in combo if n in hot],
        "gap_included":      [int(n) for n in combo if n in gap_top],
        "individual_coherence": {str(n): round(float(coh[n-1]) * 100, 1) for n in combo},
        "pair_detail": {
            f"{combo[i]}+{combo[j]}": round(
                float((cond_prob[combo[i]-1][combo[j]-1] + cond_prob[combo[j]-1][combo[i]-1]) / 2) * 100, 1
            )
            for i in range(len(combo)) for j in range(i+1, len(combo))
        },
    })

best_idx  = max(range(len(game_results)), key=lambda i: game_results[i]["combined_score"])
best_game = game_results[best_idx]
backtest  = ml.get("backtest", {}) if use_ml else {}

out = {
    "draw":              int(last_draw) + 1,
    "predicted":         best_game["numbers"],
    "bonus":             best_game["bonus"],
    "core_numbers":      best_game["core_numbers"],
    "core_coherence":    best_game["core_coherence"],
    "overall_coherence": best_game["overall_coherence"],
    "pair_score":        best_game["pair_score"],
    "pair_vs_random":    best_game["pair_vs_random"],
    "combined_score":    best_game["combined_score"],
    "method":            "정합성65%+쌍조건부확률35%+전수탐색" if use_ml else "통계+몬테카를로",
    "hot_included":      best_game["hot_included"],
    "individual_coherence": best_game["individual_coherence"],
    "pair_detail":       best_game["pair_detail"],
    "sum_range":         [SUM_LO, SUM_HI],
    "games":             game_results,
    "backtest":          backtest,
}
json.dump(out, open(DIR/"lotto_prediction.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# ── 출력 ─────────────────────────────────────────────────────────
print(f"\n{'='*62}")
print(f" {out['draw']}회 예측  [{out['method']}]")
print(f"{'='*62}")
print(f" {'게임':4}  {'번호':30}  {'합':>4}  {'정합성':>7}  {'쌍확률':>7}  {'통합':>7}")
print(f"{'─'*62}")
for g, gr in enumerate(game_results):
    marker = " ◀" if g == best_idx else ""
    print(f"  {chr(65+g):3}  {str(gr['numbers']):30}  {gr['sum']:>4}  "
          f"{gr['overall_coherence']:>6.1f}%  "
          f"{gr['pair_score']:>5.2f}%  "
          f"{gr['combined_score']:>6.1f}%{marker}")
print(f"{'─'*62}")
print(f"\n 대표 (Game {chr(65+best_idx)}) 상세:")
print(f"  번호별 정합성:")
for n in best_game["numbers"]:
    tag = "★ 핵심" if coh[n-1] >= CORE_THRESH else "  보조"
    print(f"    {tag} {n:2d}번: {round(coh[n-1]*100,1):5.1f}%")
print(f"\n  쌍별 동반 확률 (무작위 기댓값 {rand_pair*100:.1f}%):")
for pair, pct in best_game["pair_detail"].items():
    bar = "#" * int(pct / 3)
    flag = " *" if pct > rand_pair * 100 * 3 else ""
    print(f"    {pair:7s}: {pct:5.1f}%  {bar}{flag}")
print(f"{'─'*62}")
print(f" 정합성  : {best_game['overall_coherence']}%")
print(f" 쌍확률  : {best_game['pair_score']}%  (무작위 대비 {best_game['pair_vs_random']}배)")
print(f" 통합점수: {best_game['combined_score']}%")
print(f" 합계    : {best_game['sum']}  (유효범위 {SUM_LO}~{SUM_HI})")
print(f"{'='*62}")
