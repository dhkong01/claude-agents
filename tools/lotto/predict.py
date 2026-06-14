"""
로또 예측 v4
통합점수 = 정합성 50% + 쌍조건부확률 25% + 트리플렛공출현 25%
필터: 합계범위 + 밴드분산 + 3연속제외 + 홀짝비율 + 끝자리중복
Game 1: C(25,6)=177,100 전수탐색 → 수학적 최적 보장
Game 2~5: 온도 스케일링 몬테카를로
"""
import json, numpy as np
from pathlib import Path
from itertools import combinations

DIR     = Path(__file__).parent / "data"
ml_path = DIR / "lotto_ml_features.json"
ana_path= DIR / "lotto_analysis.json"

if ml_path.exists():
    ml = json.load(open(ml_path, encoding="utf-8"))
    coh        = np.array(ml["number_coherence"])
    hot        = set(ml["hot"])
    gap_top    = set(ml["gap_ranks"])
    last_draw  = ml["last_draw"]
    ss         = ml.get("sum_stats", {})
    SUM_LO     = int(ss.get("p20", 100))
    SUM_HI     = int(ss.get("p80", 175))
    # 쌍 조건부 확률
    cond_prob  = np.array(ml.get("cond_prob_matrix", np.zeros((45,45)).tolist()))
    avg_pair   = ml.get("avg_hist_pair_prob", 0.09)
    rand_pair  = ml.get("random_pair_baseline", 0.005)
    # 트리플렛 공출현
    _td        = ml.get("triplet_counts", {})
    triplet_cnt= {tuple(int(x) for x in k.split(",")): v for k, v in _td.items()}
    avg_trip   = ml.get("avg_hist_trip", 2.0)
    rand_trip  = ml.get("random_trip_baseline", 1.7)
    # 패턴 분포
    odd_stats  = {int(k): float(v) for k, v in ml.get("odd_stats", {}).items()}
    tail_stats = {int(k): float(v) for k, v in ml.get("tail_stats", {}).items()}
    use_ml     = True
else:
    ana  = json.load(open(ana_path, encoding="utf-8"))
    hist = json.load(open(DIR/"lotto_history.json", encoding="utf-8"))
    coh  = np.array([ana["weights"][str(i)] for i in range(1, 46)])
    hot, gap_top = set(ana["hot"]), set()
    last_draw = hist["last_draw"]
    SUM_LO, SUM_HI = 100, 175
    cond_prob = np.zeros((45, 45)); triplet_cnt = {}
    avg_pair, rand_pair = 0.09, 0.005
    avg_trip, rand_trip = 2.0, 1.7
    odd_stats = {2: 0.245, 3: 0.275, 4: 0.325}
    tail_stats = {0: 0.245, 1: 0.455, 2: 0.25, 3: 0.05}
    use_ml = False

CORE_THRESH = 0.65
N_GAMES     = 5
N_SAMPLES   = 60000
TOP_N       = 25     # C(25,6)=177,100 전수탐색
TEMP        = 1.5
W_COH       = 0.50   # 정합성 가중치
W_PAIR      = 0.25   # 쌍 조건부확률 가중치
W_TRIP      = 0.25   # 트리플렛 공출현 가중치

# 역사적으로 의미있는 홀수 개수 (비율 >= 5%)
VALID_ODD = {k for k, v in odd_stats.items() if v >= 0.05}  # {2,3,4,5}
# 끝자리 중복 허용 최대치 (전체 역사의 95% 이하 커버)
MAX_TAIL_DUP = 2  # 3개 이상 끝자리 중복은 5% → 제외

# ── 개별 점수 벡터 ────────────────────────────────────────────────
score = coh.copy()
score += np.array([0.05 if (i+1) in hot     else 0.0 for i in range(45)])
score += np.array([0.03 if (i+1) in gap_top else 0.0 for i in range(45)])
score = np.clip(score, 0, None)
score /= score.sum()

BANDS = [(1, 9), (10, 19), (20, 29), (30, 39), (40, 45)]

# ── 유효 조합 검사 (강화됨) ──────────────────────────────────────
def is_valid(combo):
    ns = sorted(combo)
    # 1. 합계 범위
    s = sum(ns)
    if not (SUM_LO <= s <= SUM_HI):
        return False
    # 2. 밴드 다양성 (최소 3개 구간)
    bands_hit = set()
    for n in ns:
        for lo, hi in BANDS:
            if lo <= n <= hi: bands_hit.add(lo); break
    if len(bands_hit) < 3:
        return False
    # 3. 3연속 번호 제외
    streak = 1
    for i in range(1, 6):
        streak = streak + 1 if ns[i] == ns[i-1] + 1 else 1
        if streak >= 3: return False
    # 4. 홀짝 비율 필터 (역사 5% 이상 비율만 허용)
    odd_cnt = sum(1 for n in ns if n % 2 == 1)
    if odd_cnt not in VALID_ODD:
        return False
    # 5. 끝자리 중복 제한 (3개 이상 동일 끝자리 = 5% 확률 → 제외)
    tails = [n % 10 for n in ns]
    tail_dups = len(tails) - len(set(tails))
    if tail_dups > MAX_TAIL_DUP:
        return False
    return True

# ── 점수 함수 ─────────────────────────────────────────────────────
def combo_coherence(combo):
    return float(np.mean([coh[n-1] for n in combo]))

def combo_pair_score(combo):
    """15쌍 평균 조건부 확률"""
    total, n = 0.0, 0
    for i in range(len(combo)):
        for j in range(i+1, len(combo)):
            a, b = combo[i]-1, combo[j]-1
            total += (cond_prob[a][b] + cond_prob[b][a]) / 2
            n += 1
    return total / n if n > 0 else 0.0

def combo_trip_score(combo):
    """20 트리플렛 평균 공출현 횟수"""
    ns = sorted([n-1 for n in combo])  # 0-44 인덱스
    counts = [triplet_cnt.get(t, 0) for t in combinations(ns, 3)]
    return float(np.mean(counts)) if counts else 0.0

def combined_score(combo):
    """정합성50% + 쌍확률25% + 트리플렛25% 통합 점수"""
    coh_s  = combo_coherence(combo)
    pair_s = combo_pair_score(combo)
    trip_s = combo_trip_score(combo)
    # 정규화
    pair_norm = min(pair_s / max(avg_pair * 1.5, 0.05), 1.0)
    trip_norm = min(trip_s / max(avg_trip * 1.5, 0.5), 1.0)
    return W_COH * coh_s + W_PAIR * pair_norm + W_TRIP * trip_norm

# ── Game 1: 전수탐색 ──────────────────────────────────────────────
def exhaustive_best(exclude_combos=None):
    top_nums = sorted(range(1, 46), key=lambda i: -score[i-1])[:TOP_N]
    exclude  = set(tuple(sorted(c)) for c in (exclude_combos or []))
    best, best_s = None, -1
    for combo in combinations(top_nums, 6):
        key = tuple(sorted(combo))
        if key in exclude or not is_valid(combo): continue
        s = combined_score(combo)
        if s > best_s: best_s, best = s, list(combo)
    return sorted(best) if best else None

# ── Game 2~5: 온도 스케일링 몬테카를로 ───────────────────────────
def monte_carlo_best(n_samples, seed, exclude_combos=None, prev_used=None, diversity=0.35):
    rng     = np.random.default_rng(seed)
    nums    = np.arange(1, 46)
    exclude = set(tuple(sorted(c)) for c in (exclude_combos or []))
    adj     = score.copy()
    if prev_used:
        for n, cnt in prev_used.items():
            adj[n-1] *= (1 - diversity) ** cnt
    adj = np.clip(adj, 1e-6, None) ** TEMP
    adj /= adj.sum()
    best, best_s = None, -1
    for _ in range(n_samples):
        combo = tuple(sorted(int(x) for x in rng.choice(nums, 6, replace=False, p=adj)))
        if combo in exclude or not is_valid(combo): continue
        s = combined_score(combo)
        if s > best_s: best_s, best = s, combo
    # 폴백: 홀짝/끝자리 필터 완화
    if best is None:
        for _ in range(n_samples):
            combo = tuple(sorted(int(x) for x in rng.choice(nums, 6, replace=False, p=adj)))
            if combo in exclude: continue
            if SUM_LO <= sum(combo) <= SUM_HI:
                s = combined_score(combo)
                if s > best_s: best_s, best = s, combo
    return list(best) if best else None

# ── 5게임 생성 ────────────────────────────────────────────────────
print("Game 1: 전수탐색 C(25,6)=177,100 [정합성+쌍확률+트리플렛]...")
games, all_combos, used_count = [], [], {}

g1 = exhaustive_best()
if g1:
    all_combos.append(g1); games.append(g1)
    for n in g1: used_count[n] = used_count.get(n, 0) + 1

print(f"Game 2~{N_GAMES}: 온도스케일링 몬테카를로...")
for g in range(1, N_GAMES):
    combo = monte_carlo_best(N_SAMPLES, seed=g*137,
                             exclude_combos=all_combos, prev_used=used_count)
    if combo:
        all_combos.append(combo); games.append(combo)
        for n in combo: used_count[n] = used_count.get(n, 0) + 1

if not games:
    ranked = sorted(range(1, 46), key=lambda i: -score[i-1])
    games  = [sorted(ranked[:6])]

# ── 게임 메타데이터 ───────────────────────────────────────────────
game_results = []
for combo in games:
    combo    = sorted(combo)
    core_in  = [n for n in combo if coh[n-1] >= CORE_THRESH]
    bonus    = int(max((i for i in range(1,46) if i not in combo), key=lambda i: float(score[i-1])))
    ps       = combo_pair_score(combo)
    ts       = combo_trip_score(combo)
    cs       = combined_score(combo)
    ns_idx   = sorted([n-1 for n in combo])
    game_results.append({
        "numbers":            [int(n) for n in combo],
        "bonus":              bonus,
        "sum":                int(sum(combo)),
        "odd_count":          sum(1 for n in combo if n%2==1),
        "core_numbers":       [int(n) for n in core_in],
        "core_coherence":     round(float(np.mean([coh[n-1] for n in core_in]))*100, 1) if core_in else 0.0,
        "overall_coherence":  round(combo_coherence(combo)*100, 1),
        "pair_score":         round(ps*100, 2),
        "pair_vs_random":     round(ps/max(rand_pair,1e-9), 1),
        "trip_score":         round(ts, 2),
        "trip_vs_random":     round(ts/max(rand_trip,0.01), 1),
        "combined_score":     round(cs*100, 1),
        "hot_included":       [int(n) for n in combo if n in hot],
        "individual_coherence": {str(n): round(float(coh[n-1])*100, 1) for n in combo},
        "pair_detail": {
            f"{combo[i]}+{combo[j]}": round(
                float((cond_prob[combo[i]-1][combo[j]-1]+cond_prob[combo[j]-1][combo[i]-1])/2)*100, 1
            )
            for i in range(6) for j in range(i+1, 6)
        },
        "triplet_detail": {
            f"{combo[i]+0},{combo[j]+0},{combo[k]+0}".replace(
                f"{combo[i]+0},{combo[j]+0},{combo[k]+0}",
                f"{combo[i]}+{combo[j]}+{combo[k]}"
            ): int(triplet_cnt.get(tuple(sorted([combo[i]-1,combo[j]-1,combo[k]-1])), 0))
            for i in range(6) for j in range(i+1,6) for k in range(j+1,6)
        },
    })

best_idx  = max(range(len(game_results)), key=lambda i: game_results[i]["combined_score"])
best_game = game_results[best_idx]
backtest  = ml.get("backtest", {}) if use_ml else {}

out = {
    "draw":               int(last_draw) + 1,
    "predicted":          best_game["numbers"],
    "bonus":              best_game["bonus"],
    "core_numbers":       best_game["core_numbers"],
    "overall_coherence":  best_game["overall_coherence"],
    "pair_score":         best_game["pair_score"],
    "trip_score":         best_game["trip_score"],
    "trip_vs_random":     best_game["trip_vs_random"],
    "combined_score":     best_game["combined_score"],
    "method":             f"정합성50%+쌍확률25%+트리플렛25%+전수탐색 ({ml.get('based_on',0)}회기반)" if use_ml else "통계+몬테카를로",
    "hot_included":       best_game["hot_included"],
    "individual_coherence": best_game["individual_coherence"],
    "pair_detail":        best_game["pair_detail"],
    "triplet_detail":     best_game["triplet_detail"],
    "sum_range":          [SUM_LO, SUM_HI],
    "games":              game_results,
    "backtest":           backtest,
}
json.dump(out, open(DIR/"lotto_prediction.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# ── 출력 ─────────────────────────────────────────────────────────
based_n = ml.get("based_on", 0) if use_ml else 0
print(f"\n{'='*65}")
print(f" {out['draw']}회 예측  [{out['method']}]")
print(f"{'='*65}")
print(f" {'게임':4}  {'번호':30}  {'합':>4}  홀  {'정합성':>7}  {'쌍확률':>7}  {'트리플':>7}  {'통합':>7}")
print(f"{'─'*65}")
for g, gr in enumerate(game_results):
    marker = " <" if g == best_idx else ""
    print(f"  {chr(65+g):3}  {str(gr['numbers']):30}  {gr['sum']:>4} "
          f" {gr['odd_count']}홀  "
          f"{gr['overall_coherence']:>6.1f}%  "
          f"{gr['pair_score']:>5.2f}%  "
          f"{gr['trip_score']:>5.1f}  "
          f"{gr['combined_score']:>6.1f}%{marker}")
print(f"{'─'*65}")
print(f"\n 대표 (Game {chr(65+best_idx)}) 상세:")
print(f"  번호별 정합성:")
for n in best_game["numbers"]:
    tag = "* 핵심" if coh[n-1] >= CORE_THRESH else "  보조"
    print(f"    {tag} {n:2d}번: {round(coh[n-1]*100,1):5.1f}%")
print(f"\n  쌍별 동반 확률:")
for pair, pct in best_game["pair_detail"].items():
    bar = "#" * int(pct/3)
    print(f"    {pair:7s}: {pct:5.1f}%  {bar}")
print(f"\n  트리플렛 등장 횟수 (역사 평균 {avg_trip:.1f}회):")
for trip, cnt in sorted(best_game["triplet_detail"].items(), key=lambda x: -x[1]):
    flag = " *" if cnt > avg_trip else ""
    print(f"    {trip:13s}: {cnt:3d}회{flag}")
print(f"{'─'*65}")
print(f" 정합성  : {best_game['overall_coherence']}%")
print(f" 쌍확률  : {best_game['pair_score']}%  (무작위대비 {best_game['pair_vs_random']}배)")
print(f" 트리플렛: {best_game['trip_score']}회  (무작위대비 {best_game['trip_vs_random']}배)")
print(f" 통합점수: {best_game['combined_score']}%")
print(f" 합계    : {best_game['sum']}  (유효범위 {SUM_LO}~{SUM_HI})")
print(f"{'='*65}")
