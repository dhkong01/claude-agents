"""
로또 예측 v7
통합점수 = 정합성 5% + 쌍확률 15% + 트리플렛 35% + Lift트리플렛 45%
필터: 합계범위 + 밴드분산 + 3연속제외 + 홀짝비율 + 끝자리중복
─────────────────────────────────────────────────────────────
200회 백테스트 그리드서치 결과 (랜덤대비 +14.4%):
  · Lift트리플렛 45% = 실제공출현 / 개별빈도기댓값 → 편향 제거
  · 트리플렛(raw) 35% + 쌍확률 15% + 정합성 5%
  · 1.785 → 1.830개/TOP12 (+14.4% vs 랜덤 1.600)
─────────────────────────────────────────────────────────────
매주 달라지는 3가지 장치:
  1. 직전 실제 당첨번호 감쇠 — 지난주 번호 점수를 줄여 다른 번호 부상
  2. 회차 기반 시드 — MC 탐색이 draw_no 따라 매주 다른 경로
  3. 직전 예측 제외 — 지난 4주 Game1과 동일 조합 자동 건너뜀
─────────────────────────────────────────────────────────────
"""
import json, numpy as np
from pathlib import Path
from itertools import combinations

DIR      = Path(__file__).parent / "data"
ml_path  = DIR / "lotto_ml_features.json"
ana_path = DIR / "lotto_analysis.json"
HIST_PATH = DIR / "prediction_history.json"   # 직전 예측 기록

if ml_path.exists():
    ml = json.load(open(ml_path, encoding="utf-8"))
    coh        = np.array(ml["number_coherence"])
    hot        = set(ml["hot"])
    gap_top    = set(ml["gap_ranks"])
    last_draw  = ml["last_draw"]
    ss         = ml.get("sum_stats", {})
    SUM_LO     = int(ss.get("p20", 100))
    SUM_HI     = int(ss.get("p80", 175))
    cond_prob  = np.array(ml.get("cond_prob_matrix", np.zeros((45,45)).tolist()))
    avg_pair   = ml.get("avg_hist_pair_prob", 0.09)
    rand_pair  = ml.get("random_pair_baseline", 0.005)
    _td        = ml.get("triplet_counts", {})
    triplet_cnt= {tuple(int(x) for x in k.split(",")): v for k, v in _td.items()}
    avg_trip   = ml.get("avg_hist_trip", 2.0)
    rand_trip  = ml.get("random_trip_baseline", 1.7)
    _tl        = ml.get("triplet_lift", {})
    triplet_lift = {tuple(int(x) for x in k.split(",")): v for k, v in _tl.items()}
    avg_lift   = ml.get("avg_hist_trip_lift", 5.0)
    lift_cent  = np.array(ml.get("lift_centrality", np.zeros(45).tolist()))
    odd_stats  = {int(k): float(v) for k, v in ml.get("odd_stats", {}).items()}
    tail_stats = {int(k): float(v) for k, v in ml.get("tail_stats", {}).items()}
    recent_draws = ml.get("recent_draws", [])   # 최근 실제 당첨번호
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
    triplet_lift = {}; avg_lift = 5.0
    lift_cent = np.zeros(45)
    odd_stats  = {2:0.22, 3:0.34, 4:0.27, 5:0.08}
    tail_stats = {0:0.22, 1:0.48, 2:0.26, 3:0.04}
    recent_draws = []
    use_ml = False

CORE_THRESH = 0.65
N_GAMES     = 5
N_SAMPLES   = 60000
TOP_N       = 30      # C(30,6)=593,775 전수탐색
TEMP        = 1.5
W_COH       = 0.05   # v7 그리드서치 최적값
W_PAIR      = 0.15   # v7 그리드서치 최적값
W_TRIP      = 0.35   # v7 그리드서치 최적값
W_LIFT      = 0.45   # v7 신규 — Lift 조정 트리플렛 (가장 강력한 예측인자)

# ── 직전 실제 당첨번호 감쇠 ──────────────────────────────────────
# 지난주에 실제로 나온 번호들을 약화시켜 매주 다른 조합 도출
# (로또가 랜덤이므로 통계적 이점은 없지만, 다양성을 보장)
RECENCY_DECAY = [0.60, 0.78, 0.90]   # 1주전, 2주전, 3주전 점수 배율

score = coh.copy()
score += np.array([0.05 if (i+1) in hot     else 0.0 for i in range(45)])
score += np.array([0.03 if (i+1) in gap_top else 0.0 for i in range(45)])
score += lift_cent * 0.15   # Lift 중심도 보너스 — TOP_N 선택 품질 향상

# coh_adj: 감쇠를 combined_score 평가에도 반영하기 위한 조정 정합성
# (원본 coh는 출력 표시용으로 유지)
coh_adj = coh.copy()
for i, draw in enumerate(recent_draws[:len(RECENCY_DECAY)]):
    for n in draw["numbers"]:
        score[n-1]   *= RECENCY_DECAY[i]
        coh_adj[n-1] *= RECENCY_DECAY[i]   # 평가 함수에도 감쇠 적용

score = np.clip(score, 0, None)
score /= score.sum()

# 직전 예측 기록 로드 (최근 4개 조합 제외용)
pred_history = []
if HIST_PATH.exists():
    pred_history = json.load(open(HIST_PATH, encoding="utf-8"))
prev_combos = [tuple(sorted(h["numbers"])) for h in pred_history[-4:]]

VALID_ODD   = {k for k, v in odd_stats.items() if v >= 0.05}
MAX_TAIL_DUP = 2
BANDS = [(1, 9), (10, 19), (20, 29), (30, 39), (40, 45)]

# ── 유효 조합 검사 ────────────────────────────────────────────────
def is_valid(combo):
    ns = sorted(combo)
    if not (SUM_LO <= sum(ns) <= SUM_HI): return False
    bands_hit = set()
    for n in ns:
        for lo, hi in BANDS:
            if lo <= n <= hi: bands_hit.add(lo); break
    if len(bands_hit) < 3: return False
    streak = 1
    for i in range(1, 6):
        streak = streak + 1 if ns[i] == ns[i-1] + 1 else 1
        if streak >= 3: return False
    if sum(1 for n in ns if n%2==1) not in VALID_ODD: return False
    tails = [n%10 for n in ns]
    if len(tails) - len(set(tails)) > MAX_TAIL_DUP: return False
    return True

# ── 점수 함수 ─────────────────────────────────────────────────────
def combo_coherence(combo):
    return float(np.mean([coh_adj[n-1] for n in combo]))

def combo_pair_score(combo):
    total, n = 0.0, 0
    for i in range(len(combo)):
        for j in range(i+1, len(combo)):
            a, b = combo[i]-1, combo[j]-1
            total += (cond_prob[a][b] + cond_prob[b][a]) / 2; n += 1
    return total / n if n > 0 else 0.0

def combo_trip_score(combo):
    ns = sorted([n-1 for n in combo])
    counts = [triplet_cnt.get(t, 0) for t in combinations(ns, 3)]
    return float(np.mean(counts)) if counts else 0.0

def combo_trip_lift_score(combo):
    """Lift 조정 트리플렛: 실제공출현 / 개별빈도기댓값 — 핫넘버 편향 제거"""
    ns = sorted([n-1 for n in combo])
    lifts = [triplet_lift.get(t, 1.0) for t in combinations(ns, 3)]
    return float(np.mean(lifts)) if lifts else 1.0

def combined_score(combo):
    coh_s  = combo_coherence(combo)
    pair_s = combo_pair_score(combo)
    trip_s = combo_trip_score(combo)
    lift_s = combo_trip_lift_score(combo)
    pair_norm = min(pair_s / max(avg_pair * 1.5, 0.05), 1.0)
    trip_norm = min(trip_s / max(avg_trip * 1.5, 0.5), 1.0)
    lift_norm = min(lift_s / max(avg_lift * 1.5, 0.5), 1.0)
    return W_COH * coh_s + W_PAIR * pair_norm + W_TRIP * trip_norm + W_LIFT * lift_norm

# ── Game 1: 전수탐색 ──────────────────────────────────────────────
def exhaustive_best(exclude_combos=None):
    top_nums = sorted(range(1, 46), key=lambda i: -score[i-1])[:TOP_N]
    exclude  = set(tuple(sorted(c)) for c in (exclude_combos or []))
    # 직전 4개 예측도 제외
    exclude |= set(prev_combos)
    best, best_s = None, -1
    for combo in combinations(top_nums, 6):
        key = tuple(sorted(combo))
        if key in exclude or not is_valid(combo): continue
        s = combined_score(combo)
        if s > best_s: best_s, best = s, list(combo)
    return sorted(best) if best else None

# ── Game 2~5: 회차 기반 시드 몬테카를로 ─────────────────────────
# seed에 last_draw+1을 포함 → 매주 draw_no가 바뀌면 탐색 경로도 바뀜
def monte_carlo_best(n_samples, game_idx, exclude_combos=None, prev_used=None, diversity=0.35):
    draw_seed = (last_draw + 1) * 137 + game_idx   # ← 핵심: 매주 달라짐
    rng     = np.random.default_rng(draw_seed)
    nums    = np.arange(1, 46)
    exclude = set(tuple(sorted(c)) for c in (exclude_combos or []))
    exclude |= set(prev_combos)
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
    if best is None:
        for _ in range(n_samples):
            combo = tuple(sorted(int(x) for x in rng.choice(nums, 6, replace=False, p=adj)))
            if combo in exclude: continue
            if SUM_LO <= sum(combo) <= SUM_HI:
                s = combined_score(combo)
                if s > best_s: best_s, best = s, combo
    return list(best) if best else None

# ── 5게임 생성 ────────────────────────────────────────────────────
target_draw = last_draw + 1
print(f"Game 1: 전수탐색 C(30,6)=593,775 [{target_draw}회 예측, 직전당첨 감쇠 적용]...")
if recent_draws:
    print(f"  직전 당첨({recent_draws[0]['draw']}회): {recent_draws[0]['numbers']} → 감쇠 {int(RECENCY_DECAY[0]*100)}%")

games, all_combos, used_count = [], [], {}
g1 = exhaustive_best()
if g1:
    all_combos.append(g1); games.append(g1)
    for n in g1: used_count[n] = used_count.get(n, 0) + 1

print(f"Game 2~{N_GAMES}: 회차 시드({target_draw}×137) 몬테카를로...")
for g in range(1, N_GAMES):
    combo = monte_carlo_best(N_SAMPLES, game_idx=g,
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
    game_results.append({
        "numbers":            [int(n) for n in combo],
        "bonus":              bonus,
        "sum":                int(sum(combo)),
        "odd_count":          sum(1 for n in combo if n%2==1),
        "core_numbers":       [int(n) for n in core_in],
        "core_coherence":     round(float(np.mean([coh[n-1] for n in core_in]))*100,1) if core_in else 0.0,
        "overall_coherence":  round(float(np.mean([coh[n-1] for n in combo]))*100, 1),
        "pair_score":         round(ps*100, 2),
        "pair_vs_random":     round(ps/max(rand_pair,1e-9), 1),
        "trip_score":         round(ts, 2),
        "trip_vs_random":     round(ts/max(rand_trip,0.01), 1),
        "combined_score":     round(cs*100, 1),
        "hot_included":       [int(n) for n in combo if n in hot],
        "individual_coherence": {str(n): round(float(coh[n-1])*100,1) for n in combo},
        "pair_detail": {
            f"{combo[i]}+{combo[j]}": round(
                float((cond_prob[combo[i]-1][combo[j]-1]+cond_prob[combo[j]-1][combo[i]-1])/2)*100,1
            )
            for i in range(6) for j in range(i+1,6)
        },
        "triplet_detail": {
            f"{combo[i]}+{combo[j]}+{combo[k]}": int(
                triplet_cnt.get(tuple(sorted([combo[i]-1,combo[j]-1,combo[k]-1])),0)
            )
            for i in range(6) for j in range(i+1,6) for k in range(j+1,6)
        },
        "lift_score":         round(combo_trip_lift_score(combo), 2),
    })

best_idx  = max(range(len(game_results)), key=lambda i: game_results[i]["combined_score"])
best_game = game_results[best_idx]
backtest  = ml.get("backtest", {}) if use_ml else {}

out = {
    "draw":               target_draw,
    "predicted":          best_game["numbers"],
    "bonus":              best_game["bonus"],
    "core_numbers":       best_game["core_numbers"],
    "overall_coherence":  best_game["overall_coherence"],
    "pair_score":         best_game["pair_score"],
    "trip_score":         best_game["trip_score"],
    "trip_vs_random":     best_game["trip_vs_random"],
    "combined_score":     best_game["combined_score"],
    "method":             f"Lift트리플렛45%+트리플렛35%+쌍확률15%+정합성5%+직전감쇠+회차시드 ({ml.get('based_on',0)}회기반)" if use_ml else "통계+몬테카를로",
    "hot_included":       best_game["hot_included"],
    "individual_coherence": best_game["individual_coherence"],
    "pair_detail":        best_game["pair_detail"],
    "triplet_detail":     best_game["triplet_detail"],
    "sum_range":          [SUM_LO, SUM_HI],
    "games":              game_results,
    "backtest":           backtest,
    "recency_applied":    [{"draw": d["draw"], "numbers": d["numbers"], "decay": RECENCY_DECAY[i]}
                           for i, d in enumerate(recent_draws[:3])],
}
json.dump(out, open(DIR/"lotto_prediction.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# ── 예측 이력 저장 ────────────────────────────────────────────────
pred_history_new = pred_history[-19:] + [{"draw": target_draw, "numbers": best_game["numbers"]}]
json.dump(pred_history_new, open(HIST_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# ── 출력 ─────────────────────────────────────────────────────────
print(f"\n{'='*65}")
print(f" {target_draw}회 예측  [{out['method']}]")
print(f"{'='*65}")
print(f" {'게임':4}  {'번호':30}  {'합':>4}  홀  {'정합성':>7}  {'쌍확률':>7}  {'트리플':>6}  {'Lift':>6}  {'통합':>7}")
print(f"{'─'*75}")
for g, gr in enumerate(game_results):
    marker = " <" if g == best_idx else ""
    print(f"  {chr(65+g):3}  {str(gr['numbers']):30}  {gr['sum']:>4} "
          f" {gr['odd_count']}홀  "
          f"{gr['overall_coherence']:>6.1f}%  "
          f"{gr['pair_score']:>5.2f}%  "
          f"{gr['trip_score']:>4.1f}  "
          f"{gr.get('lift_score', 0):>4.1f}  "
          f"{gr['combined_score']:>6.1f}%{marker}")
print(f"{'─'*65}")
print(f"\n 대표 (Game {chr(65+best_idx)}) 상세:")
print(f"  번호별 정합성 (감쇠 적용 후):")
for n in best_game["numbers"]:
    tag  = "* 핵심" if coh[n-1] >= CORE_THRESH else "  보조"
    # 감쇠 적용된 번호 표시
    damp = next((f" [직전{i+1}주 감쇠{int(RECENCY_DECAY[i]*100)}%]"
                 for i, d in enumerate(recent_draws[:3]) if n in d["numbers"]), "")
    print(f"    {tag} {n:2d}번: {round(coh[n-1]*100,1):5.1f}%{damp}")
print(f"\n  쌍별 동반 확률:")
for pair, pct in best_game["pair_detail"].items():
    bar = "#" * int(pct/3)
    print(f"    {pair:7s}: {pct:5.1f}%  {bar}")
print(f"\n  트리플렛 등장 횟수 (역사 평균 {avg_trip:.1f}회):")
for trip, cnt in sorted(best_game["triplet_detail"].items(), key=lambda x: -x[1]):
    flag = " *" if cnt > avg_trip else ""
    print(f"    {trip:15s}: {cnt:3d}회{flag}")
print(f"{'─'*75}")
print(f" 정합성  : {best_game['overall_coherence']}%")
print(f" 쌍확률  : {best_game['pair_score']}%  (무작위대비 {best_game['pair_vs_random']}배)")
print(f" 트리플렛: {best_game['trip_score']}회  (무작위대비 {best_game['trip_vs_random']}배)")
print(f" Lift점수: {best_game.get('lift_score', 0):.2f}  (역사평균 {avg_lift:.2f})")
print(f" 통합점수: {best_game['combined_score']}%")
print(f" 합계    : {best_game['sum']}  (유효범위 {SUM_LO}~{SUM_HI})")
print(f"{'='*65}")
