"""
로또 추첨 편향 감시 + 자동 교정 가중치 산출.

한국 로또는 실물 공·추첨기를 쓰므로 특정 공 세트/기계에 물리적 편향이
생길 가능성이 이론적으로 존재한다. 이 모듈은 매주 최근 추첨을 검사해
"진짜 편향"일 때만 번호별 교정 가중치를 predict.py에 넘긴다.

오탐 방지 (매주 검사하면 우연히 걸리는 주가 반드시 생김):
  1) 빈도 균등성 검정   — 최근 WINDOW회 번호별 출현빈도가 난수와 다른가 (p < 0.01)
  2) 편향 지속성 검정   — 창을 반으로 나눴을 때 같은 번호가 양쪽 모두에서
                          과다/과소인가 (물리적 편향이면 지속됨, 우연이면 안 됨) (p < 0.05)
  3) 연속 확인          — 1)+2)가 CONFIRM_WEEKS주 연속 감지돼야 교정 활성화
p값은 모두 같은 조건의 가상 추첨을 몬테카를로로 생성해 계산한다.

교정 가중치: 관측빈도를 기댓값 쪽으로 강하게 수축(shrinkage)한 비율,
[W_MIN, W_MAX]로 클리핑. 비활성 시 전부 1.0 (예측에 영향 없음).

실행:  python tools/lotto/bias_monitor.py            # 감시 + lotto_bias.json 갱신
       python tools/lotto/bias_monitor.py --selftest # 인위적 편향 데이터로 감지 성능 검증
"""
import json
import sys
from pathlib import Path

import numpy as np

DIR       = Path(__file__).parent / "data"
HIST_PATH = DIR / "lotto_history.json"
OUT_PATH  = DIR / "lotto_bias.json"

WINDOW        = 300    # 최근 몇 회를 검사할지 (공 세트 교체 주기 고려)
N_SIMS        = 1000   # 몬테카를로 가상 추첨 세트 수
P_CHI2        = 0.01   # 빈도 균등성 유의수준
P_PERSIST     = 0.05   # 지속성 유의수준 (단측, 양의 상관)
CONFIRM_WEEKS = 2      # 연속 감지 주 수
SHRINK_K      = 1.0    # 수축 강도 (기댓값의 배수) — 클수록 보수적
W_MIN, W_MAX  = 0.75, 1.35
REPORT_DEV    = 0.10   # 가중치가 ±10% 이상일 때 과다/과소 번호로 보고


def _counts(draws_idx, n_num=45):
    """draws_idx: (n, 6) 0-based 번호 → 번호별 출현횟수"""
    return np.bincount(np.asarray(draws_idx).ravel(), minlength=n_num).astype(float)


def _stats(first, second):
    """반창 2개의 카운트 → (전체 χ², 반창 간 피어슨 상관)
    지속성은 순위(스피어만)가 아니라 편차 크기 그대로(피어슨) 본다 —
    물리적 편향은 보통 소수 번호에 크게 나타나는데, 순위 상관은 그 큰
    편차를 나머지 40여 개 번호의 노이즈 속에 희석시켜 감지력이 크게 떨어짐."""
    total = first + second
    n_draws = total.sum() / 6
    e = n_draws * 6 / 45
    chi2 = float(((total - e) ** 2 / e).sum())
    persist = float(np.corrcoef(first, second)[0, 1])
    return chi2, persist


def _null_distribution(n, rng, sims=N_SIMS, chunk=100):
    h = n // 2
    chis, pers = [], []
    for s in range(0, sims, chunk):
        c = min(chunk, sims - s)
        picks = np.argpartition(rng.random((c, n, 45)), 6, axis=2)[:, :, :6]
        for k in range(c):
            chi2, persist = _stats(_counts(picks[k, :h]), _counts(picks[k, h:]))
            chis.append(chi2); pers.append(persist)
    return np.array(chis), np.array(pers)


def evaluate(draws, rng=None):
    """draws: 오래된→최신 순 번호 리스트(1-based). 최근 WINDOW회로 판정."""
    rng = rng or np.random.default_rng(12345)
    win = draws[-WINDOW:]
    n = len(win)
    idx = np.array(win) - 1
    first, second = _counts(idx[: n // 2]), _counts(idx[n // 2:])
    chi2, persist = _stats(first, second)
    null_chi, null_per = _null_distribution(n, rng)
    p_chi = float((np.sum(null_chi >= chi2) + 1) / (len(null_chi) + 1))
    p_per = float((np.sum(null_per >= persist) + 1) / (len(null_per) + 1))

    total = first + second
    e = n * 6 / 45
    k = SHRINK_K * e
    weights = np.clip((total + k) / (e + k), W_MIN, W_MAX)
    return {
        "chi2": {"stat": round(chi2, 3), "p": round(p_chi, 4), "threshold": P_CHI2},
        "persistence": {"stat": round(persist, 4), "p": round(p_per, 4), "threshold": P_PERSIST},
        "detected": bool(p_chi < P_CHI2 and p_per < P_PERSIST),
        "candidate_weights": [round(float(w), 4) for w in weights],
    }


def run():
    hist = json.loads(HIST_PATH.read_text(encoding="utf-8"))
    recs = sorted(hist["data"], key=lambda r: r["draw"])
    draws = [sorted(r["numbers"]) for r in recs]
    last_draw = recs[-1]["draw"]

    prev = {}
    if OUT_PATH.exists():
        try:
            prev = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    history = [h for h in prev.get("history", []) if h.get("draw") != last_draw]
    was_active = bool(prev.get("active")) and prev.get("evaluated_draw") != last_draw

    res = evaluate(draws)
    history = (history + [{"draw": last_draw, "detected": res["detected"],
                           "p_chi2": res["chi2"]["p"], "p_persist": res["persistence"]["p"]}])[-52:]

    streak = 0
    for h in reversed(history):
        if not h["detected"]:
            break
        streak += 1
    active = streak >= CONFIRM_WEEKS

    weights = res["candidate_weights"] if active else [1.0] * 45
    over  = [i + 1 for i, w in enumerate(weights) if w >= 1 + REPORT_DEV]
    under = [i + 1 for i, w in enumerate(weights) if w <= 1 - REPORT_DEV]

    out = {
        "evaluated_draw": last_draw,
        "window": [recs[-WINDOW]["draw"] if len(recs) >= WINDOW else recs[0]["draw"], last_draw],
        "tests": {"chi2": res["chi2"], "persistence": res["persistence"]},
        "detected_this_week": res["detected"],
        "streak": streak,
        "confirm_weeks": CONFIRM_WEEKS,
        "active": active,
        "newly_active": active and not was_active,
        "weights": weights,
        "biased_numbers": {"over": over, "under": under},
        "history": history,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    status = ("교정 활성" if active else
              f"감지됨 ({streak}/{CONFIRM_WEEKS}주, 확인 대기)" if res["detected"] else "이상 없음")
    print(f"[편향감시] {out['window'][0]}~{last_draw}회 | 빈도 p={res['chi2']['p']:.3f} "
          f"지속성 p={res['persistence']['p']:.3f} | {status}")
    if active:
        print(f"  과다 번호(가중↑): {over}  과소 번호(가중↓): {under}")
    return out


def selftest():
    """인위적으로 편향을 심은 데이터로 감지/교정이 실제로 작동하는지 검증."""
    rng = np.random.default_rng(2026)
    def gen(n, boost=None):
        p = np.ones(45)
        for num, f in (boost or {}).items():
            p[num - 1] = f
        p /= p.sum()
        return [sorted(rng.choice(45, 6, replace=False, p=p) + 1) for _ in range(n)]

    trials = 20
    fp = sum(evaluate(gen(WINDOW), np.random.default_rng(t))["detected"] for t in range(trials))
    print(f"[selftest] 순수 난수 오탐: {fp}/{trials}회 (1주 기준 — 실제 적용은 {CONFIRM_WEEKS}주 연속 필요)")
    for strength in (1.3, 1.6, 2.0):
        boost = {7: strength, 23: strength, 40: strength, 12: 1 / strength}
        tp, hit_w, low_w = 0, [], []
        for t in range(trials):
            r = evaluate(gen(WINDOW, boost), np.random.default_rng(100 + t))
            tp += r["detected"]
            w = r["candidate_weights"]
            hit_w.append((w[6] + w[22] + w[39]) / 3)
            low_w.append(w[11])
        print(f"[selftest] 편향 {strength}배(7·23·40↑, 12↓): 감지 {tp}/{trials}회 | "
              f"교정가중치 ↑번호 {np.mean(hit_w):.3f}, ↓번호 {np.mean(low_w):.3f}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    selftest() if "--selftest" in sys.argv else run()
