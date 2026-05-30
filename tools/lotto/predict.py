import json, numpy as np
from pathlib import Path

DIR = Path(__file__).parent / "data"
ml_path  = DIR / "lotto_ml_features.json"
ana_path = DIR / "lotto_analysis.json"

if ml_path.exists():
    ml = json.load(open(ml_path, encoding="utf-8"))
    coh       = np.array(ml["number_coherence"])
    hot       = set(ml["hot"])
    gap_top   = set(ml["gap_ranks"])
    rec_odd   = ml["rec_odd"]
    top_pairs = {(min(p[0], p[1]), max(p[0], p[1])): c for p, c in ml["top_pairs"]}
    last_draw = ml["last_draw"]
    ss        = ml.get("sum_stats", {})
    SUM_LO    = int(ss.get("p20", 100))
    SUM_HI    = int(ss.get("p80", 175))
    use_ml    = True
else:
    ana  = json.load(open(ana_path, encoding="utf-8"))
    hist = json.load(open(DIR/"lotto_history.json", encoding="utf-8"))
    coh  = np.array([ana["weights"][str(i)] for i in range(1, 46)])
    hot, gap_top, rec_odd, top_pairs = set(ana["hot"]), set(), ana["rec_odd"], {}
    last_draw = hist["last_draw"]
    SUM_LO, SUM_HI = 100, 175
    use_ml = False

CORE_THRESH = 0.70   # 다중 모델 정합성 기준 핵심 번호 (70%+)
N_GAMES     = 5      # 게임 수
N_SAMPLES   = 40000  # 몬테카를로 샘플 수

# ── 종합 점수 ──────────────────────────────────────────────────────
score = coh.copy()
score += np.array([0.05 if (i+1) in hot     else 0.0 for i in range(45)])
score += np.array([0.03 if (i+1) in gap_top else 0.0 for i in range(45)])
score = np.clip(score, 0, None)
score /= score.sum()

BANDS = [(1, 9), (10, 19), (20, 29), (30, 39), (40, 45)]

def is_valid(combo):
    """통계 기반 유효성 검증"""
    s = sum(combo)
    if not (SUM_LO <= s <= SUM_HI):
        return False
    # 밴드 다양성: 최소 3개 밴드
    bands_hit = set()
    for n in combo:
        for lo, hi in BANDS:
            if lo <= n <= hi:
                bands_hit.add(lo)
                break
    if len(bands_hit) < 3:
        return False
    # 3개 이상 연속 번호 방지
    ns = sorted(combo)
    streak = 1
    for i in range(1, len(ns)):
        streak = streak + 1 if ns[i] == ns[i-1] + 1 else 1
        if streak >= 3:
            return False
    return True

def combo_score(combo):
    s = sum(score[n-1] for n in combo)
    ns = sorted(combo)
    for i in range(len(ns)):
        for j in range(i+1, len(ns)):
            k = (ns[i], ns[j])
            if k in top_pairs:
                s += 0.005 * top_pairs[k]
    return s

def monte_carlo_best(n_samples, seed, exclude_combos=None, prev_used=None, diversity=0.4):
    """몬테카를로 샘플링으로 제약 만족 최적 조합 탐색
    diversity: 이전 게임 사용 번호 점수 감쇠 비율 (0~1, 높을수록 다양성 강조)
    """
    rng = np.random.default_rng(seed)
    nums = np.arange(1, 46)
    exclude = set(tuple(sorted(c)) for c in (exclude_combos or []))

    # 이전 게임에서 많이 쓴 번호 감쇠
    adj_score = score.copy()
    if prev_used:
        for n, cnt in prev_used.items():
            adj_score[n-1] *= (1 - diversity) ** cnt
    adj_score = np.clip(adj_score, 1e-6, None)
    adj_score /= adj_score.sum()

    best, best_s = None, -1
    for _ in range(n_samples):
        combo = tuple(sorted(int(x) for x in rng.choice(nums, size=6, replace=False, p=adj_score)))
        if combo in exclude:
            continue
        if not is_valid(combo):
            continue
        s = combo_score(combo)
        if s > best_s:
            best_s, best = s, combo

    if best is None:
        for _ in range(n_samples):
            combo = tuple(sorted(int(x) for x in rng.choice(nums, size=6, replace=False, p=adj_score)))
            if combo in exclude:
                continue
            if SUM_LO <= sum(combo) <= SUM_HI:
                s = combo_score(combo)
                if s > best_s:
                    best_s, best = s, combo
    return list(best) if best else None

# ── 5게임 생성 ────────────────────────────────────────────────────
print("조합 탐색 중 (몬테카를로)...")
games      = []
all_combos = []
used_count = {}  # 번호별 사용 횟수 추적

for g in range(N_GAMES):
    combo = monte_carlo_best(N_SAMPLES, seed=g * 137,
                             exclude_combos=all_combos, prev_used=used_count)
    if combo:
        all_combos.append(combo)
        games.append(combo)
        for n in combo:
            used_count[n] = used_count.get(n, 0) + 1

if not games:
    ranked = sorted(range(1, 46), key=lambda i: -score[i-1])
    games  = [sorted(ranked[:6])]

# ── 게임 메타데이터 ───────────────────────────────────────────────
game_results = []
for combo in games:
    combo = sorted(combo)
    core_in = [n for n in combo if coh[n-1] >= CORE_THRESH]
    bonus = int(max(
        (i for i in range(1, 46) if i not in combo),
        key=lambda i: float(score[i-1])
    ))
    game_results.append({
        "numbers":           [int(n) for n in combo],
        "bonus":             bonus,
        "sum":               int(sum(combo)),
        "odd_count":         sum(1 for n in combo if n % 2 == 1),
        "core_numbers":      [int(n) for n in core_in],
        "core_coherence":    round(float(np.mean([coh[n-1] for n in core_in])) * 100, 1) if core_in else 0.0,
        "overall_coherence": round(float(np.mean([coh[n-1] for n in combo])) * 100, 1),
        "hot_included":      [int(n) for n in combo if n in hot],
        "gap_included":      [int(n) for n in combo if n in gap_top],
        "individual_coherence": {str(n): round(float(coh[n-1]) * 100, 1) for n in combo},
    })

# 대표 게임: 정합성 최고
best_idx  = max(range(len(game_results)), key=lambda i: game_results[i]["overall_coherence"])
best_game = game_results[best_idx]

out = {
    "draw":              int(last_draw) + 1,
    "predicted":         best_game["numbers"],
    "bonus":             best_game["bonus"],
    "core_numbers":      best_game["core_numbers"],
    "core_coherence":    best_game["core_coherence"],
    "overall_coherence": best_game["overall_coherence"],
    "method":            "5모델합의정합성+몬테카를로" if use_ml else "통계+몬테카를로",
    "hot_included":      best_game["hot_included"],
    "gap_included":      best_game["gap_included"],
    "individual_coherence": best_game["individual_coherence"],
    "sum_range":         [SUM_LO, SUM_HI],
    "games":             game_results,
}
json.dump(out, open(DIR/"lotto_prediction.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# ── 출력 ─────────────────────────────────────────────────────────
print(f"\n{'='*54}")
print(f" {out['draw']}회 예측  [{out['method']}]")
print(f"{'='*54}")
print(f" {'게임':4}  {'번호':32}  {'합':>5}  {'홀짝':>5}  {'정합성':>8}")
print(f"{'─'*54}")
for g, gr in enumerate(game_results):
    marker = " ◀ 대표" if g == best_idx else ""
    print(f"  {chr(65+g):3}  {str(gr['numbers']):32}  {gr['sum']:>5}  "
          f"{gr['odd_count']}홀{6-gr['odd_count']}짝  {gr['overall_coherence']:>6.1f}%{marker}")
print(f"{'─'*54}")
print(f"\n 대표 (Game {chr(65+best_idx)}) 상세:")
for n in best_game["numbers"]:
    tag = "★ 핵심" if coh[n-1] >= CORE_THRESH else "  보조"
    print(f"  {tag} {n:2d}번 : {round(coh[n-1]*100, 1):5.1f}%")
print(f"{'─'*54}")
print(f" 핵심({len(best_game['core_numbers'])}개): {best_game['core_numbers']}")
print(f" 전체 정합성 : {best_game['overall_coherence']}%")
print(f" 합계        : {best_game['sum']}  (유효범위 {SUM_LO}~{SUM_HI})")
print(f" 핫포함      : {best_game['hot_included']}")
print(f"{'='*54}")
