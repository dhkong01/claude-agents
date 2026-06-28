"""
로또 예측 v8 — 5가지 다전략
통합점수 = Lift 45% + 트리플렛 35% + 쌍확률 15% + 정합성 5%
─────────────────────────────────────────────────────────────
[핵심 개선] 합계 필터 p20-p80 → p10-p90 (실제 당첨 제외 방지)
[핵심 개선] 5게임이 서로 다른 전략으로 더 넓은 확률 공간 커버

Game A: HOT    — Lift 전수탐색 (고정합성 최적)
Game B: HOT-MC — 핫넘버 MC 탐색
Game C: GAP    — 오래 안 나온 번호 우대 MC
Game D: COLD   — 저정합성 번호 우대 MC (비인기 번호 커버)
Game E: MIX    — 균등 가중 MC (완전 다양성)
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
    SUM_LO     = int(ss.get("p10", 95))   # v8: p20→p10 (합=112 같은 유효 당첨 차단 방지)
    SUM_HI     = int(ss.get("p90", 180))  # v8: p80→p90
    cond_prob  = np.array(ml.get("cond_prob_matrix", np.zeros((45,45)).tolist()))
    avg_pair   = ml.get("avg_hist_pair_prob", 0.09)
    rand_pair  = ml.get("random_pair_baseline", 0.005)
    _td        = ml.get("triplet_counts", {})
    triplet_cnt= {tuple(int(x) for x in k.split(",")): v for k, v in _td.items()}
    avg_trip   = ml.get("avg_hist_trip", 2.0)
    rand_trip  = ml.get("random_trip_baseline", 1.7)
    _tl        = ml.get("triplet_lift", {})
    triplet_lift = {tuple(int(x) for x in k.split(",")): v for k, v in _tl.items()}
    avg_lift   = ml.get("avg_hist_trip_lift", 0.92)
    lift_cent  = np.array(ml.get("lift_centrality", np.zeros(45).tolist()))
    gap_scores = np.array(ml.get("gap_scores", np.zeros(45).tolist()))  # v8: GAP 전략용
    odd_stats  = {int(k): float(v) for k, v in ml.get("odd_stats", {}).items()}
    tail_stats = {int(k): float(v) for k, v in ml.get("tail_stats", {}).items()}
    recent_draws = ml.get("recent_draws", [])
    use_ml     = True
else:
    ana  = json.load(open(ana_path, encoding="utf-8"))
    hist = json.load(open(DIR/"lotto_history.json", encoding="utf-8"))
    coh  = np.array([ana["weights"][str(i)] for i in range(1, 46)])
    hot, gap_top = set(ana["hot"]), set()
    last_draw = hist["last_draw"]
    SUM_LO, SUM_HI = 95, 180
    cond_prob = np.zeros((45, 45)); triplet_cnt = {}
    avg_pair, rand_pair = 0.09, 0.005
    avg_trip, rand_trip = 2.0, 1.7
    triplet_lift = {}; avg_lift = 0.92
    lift_cent = np.zeros(45)
    gap_scores = np.zeros(45)
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

# ── MC 공통 헬퍼 ─────────────────────────────────────────────────
def _mc_search(weights, game_idx, n_samples, exclude_combos, seed_offset=0):
    """weights로 샘플링 후 combined_score 최대 조합 반환"""
    draw_seed = (last_draw + 1) * 137 + game_idx + seed_offset
    rng     = np.random.default_rng(draw_seed)
    nums    = np.arange(1, 46)
    exclude = set(tuple(sorted(c)) for c in (exclude_combos or [])) | set(prev_combos)
    adj     = np.clip(weights, 1e-9, None) ** TEMP
    adj    /= adj.sum()
    best, best_s = None, -1
    for _ in range(n_samples):
        combo = tuple(sorted(int(x) for x in rng.choice(nums, 6, replace=False, p=adj)))
        if combo in exclude or not is_valid(combo): continue
        s = combined_score(combo)
        if s > best_s: best_s, best = s, combo
    if best is None:
        for _ in range(n_samples // 2):
            combo = tuple(sorted(int(x) for x in rng.choice(nums, 6, replace=False, p=adj)))
            if combo not in exclude and SUM_LO <= sum(combo) <= SUM_HI:
                s = combined_score(combo)
                if s > best_s: best_s, best = s, combo
    return list(best) if best else None

# ── 전략별 가중치 ─────────────────────────────────────────────────
# HOT-MC: 핫넘버(정합성+Lift 중심도) 위주
hot_weights   = score.copy()

# GAP: 오래 안 나온 번호 우대 (0=최근, 1=오래됨)
# 정합성 50% + 갭점수 50% 혼합
gap_weights   = 0.5 * (coh / (coh.max() + 1e-9)) + 0.5 * gap_scores
gap_weights   = np.clip(gap_weights, 1e-9, None)

# COLD: 정합성 하위 번호 우대 (비인기 번호 커버)
# 당첨번호 중 ~50%는 정합성 낮은 번호 → 이를 보완
cold_weights  = np.clip(coh.max() - coh + 0.01, 1e-9, None)

# MIX: 균등 (랜덤성 커버)
mix_weights   = np.ones(45)

# ── 5게임 생성 ────────────────────────────────────────────────────
target_draw = last_draw + 1
game_strategies = [
    ("HOT",    "전수탐색(Lift최적)"),
    ("HOT-MC", "핫넘버 MC"),
    ("GAP",    "오래안나온번호 MC"),
    ("COLD",   "저정합성번호 MC"),
    ("MIX",    "균등샘플 MC"),
]

print(f"[{target_draw}회 예측] 합계범위 {SUM_LO}~{SUM_HI}  직전감쇠 {int(RECENCY_DECAY[0]*100)}%")
if recent_draws:
    print(f"  직전 당첨({recent_draws[0]['draw']}회): {recent_draws[0]['numbers']}")

games, all_combos = [], []

# Game A: 전수탐색 (HOT)
print("Game A: 전수탐색 C(30,6)=593,775 [HOT+Lift 최적]...")
g1 = exhaustive_best()
if g1:
    all_combos.append(g1); games.append(g1)

# Game B: HOT-MC
print("Game B: HOT-MC 샘플링...")
g2 = _mc_search(hot_weights, 1, N_SAMPLES, all_combos, seed_offset=0)
if g2:
    all_combos.append(g2); games.append(g2)

# Game C: GAP
print("Game C: GAP 전략 (장기 미출현 번호 우대)...")
g3 = _mc_search(gap_weights, 2, N_SAMPLES, all_combos, seed_offset=200)
if g3:
    all_combos.append(g3); games.append(g3)

# Game D: COLD
print("Game D: COLD 전략 (저정합성 번호 우대)...")
g4 = _mc_search(cold_weights, 3, N_SAMPLES, all_combos, seed_offset=300)
if g4:
    all_combos.append(g4); games.append(g4)

# Game E: MIX
print("Game E: MIX 전략 (균등 샘플)...")
g5 = _mc_search(mix_weights, 4, N_SAMPLES, all_combos, seed_offset=400)
if g5:
    all_combos.append(g5); games.append(g5)

if not games:
    games = [sorted(range(1, 46), key=lambda i: -score[i-1])[:6]]

# ── 게임 메타데이터 ───────────────────────────────────────────────
game_results = []
for gi, combo in enumerate(games):
    combo    = sorted(combo)
    strategy = game_strategies[gi][0] if gi < len(game_strategies) else "?"
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
        "strategy":           strategy,
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
    "method":             f"Lift45%+Trip35%+Pair15%+Coh5%+5전략(HOT/GAP/COLD/MIX) ({ml.get('based_on',0)}회기반)" if use_ml else "통계+몬테카를로",
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
print(f" {'게임':4}  {'전략':7}  {'번호':28}  {'합':>4}  홀  {'정합성':>6}  {'Lift':>5}  {'통합':>6}")
print(f"{'─'*80}")
for g, gr in enumerate(game_results):
    marker = " <" if g == best_idx else ""
    print(f"  {chr(65+g):3}  {gr.get('strategy','?'):7}  {str(gr['numbers']):28}  {gr['sum']:>4} "
          f" {gr['odd_count']}홀  "
          f"{gr['overall_coherence']:>5.1f}%  "
          f"{gr.get('lift_score', 0):>4.1f}  "
          f"{gr['combined_score']:>5.1f}%{marker}")
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
print(f"{'─'*80}")
print(f" 정합성  : {best_game['overall_coherence']}%")
print(f" 쌍확률  : {best_game['pair_score']}%  (무작위대비 {best_game['pair_vs_random']}배)")
print(f" 트리플렛: {best_game['trip_score']}회  (무작위대비 {best_game['trip_vs_random']}배)")
print(f" Lift점수: {best_game.get('lift_score', 0):.2f}  (역사평균 {avg_lift:.2f})")
print(f" 통합점수: {best_game['combined_score']}%")
print(f" 합계    : {best_game['sum']}  (유효범위 {SUM_LO}~{SUM_HI})")
print(f"{'='*65}")
