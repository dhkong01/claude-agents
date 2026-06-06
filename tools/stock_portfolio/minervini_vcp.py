"""
Minervini VCP (Volatility Contraction Pattern) 스크리너
Stage 2 진단 + VCP 수치 패턴 탐지 → 상승 직전 TOP 20 선별
유니버스: S&P 500 + NASDAQ-100
"""
import json
import sys
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from data_utils import CACHE_DIR


# ── Stage 2 판정 ──────────────────────────────────────────────

def check_stage2(close: pd.Series) -> dict:
    """
    Minervini Stage 2 6개 기준 체크.
    Returns: {is_stage2, score(0-40), criteria_passed, ma50/150/200, current, high/low_52w}
    """
    if len(close) < 220:
        return {"is_stage2": False, "score": 0, "criteria_passed": 0}

    p = close.values.astype(float)
    current = p[-1]
    ma50    = np.mean(p[-50:])
    ma150   = np.mean(p[-150:])
    ma200   = np.mean(p[-200:])
    ma200_4w = np.mean(p[-220:-170])     # 4주 전 200MA

    n252   = min(252, len(p))
    high52 = float(np.max(p[-n252:]))
    low52  = float(np.min(p[-n252:]))

    crit = {
        "price_above_ma50":    current > ma50,
        "ma50_above_ma150":    ma50    > ma150,
        "ma150_above_ma200":   ma150   > ma200,
        "ma200_trending_up":   ma200   > ma200_4w,
        "above_30pct_low":     current >= low52  * 1.30,
        "within_25pct_high":   current >= high52 * 0.75,
    }
    passed    = sum(crit.values())
    score     = int(passed / len(crit) * 40)
    is_stage2 = passed >= 5

    return {
        "is_stage2":       is_stage2,
        "score":           score,
        "criteria_passed": passed,
        "current":         round(current, 2),
        "ma50":            round(ma50, 2),
        "ma150":           round(ma150, 2),
        "ma200":           round(ma200, 2),
        "high52":          round(high52, 2),
        "low52":           round(low52, 2),
    }


# ── VCP 패턴 탐지 ─────────────────────────────────────────────

def _local_highs(arr: np.ndarray, w: int = 5) -> list[tuple[int, float]]:
    return [(i, arr[i]) for i in range(w, len(arr) - w)
            if arr[i] == np.max(arr[i - w: i + w + 1])]


def _local_lows(arr: np.ndarray, w: int = 5) -> list[tuple[int, float]]:
    return [(i, arr[i]) for i in range(w, len(arr) - w)
            if arr[i] == np.min(arr[i - w: i + w + 1])]


def detect_vcp(close: pd.Series, volume: pd.Series | None = None) -> dict:
    """
    VCP: 13주 가격에서 연속 수축 패턴 탐지.
    Returns: {has_vcp, score(0-45), pivot, contractions, final_depth_pct, vol_declining}
    """
    if len(close) < 65:
        return {"has_vcp": False, "score": 0, "pivot": None}

    p   = close.values[-65:].astype(float)
    vol = volume.values[-65:].astype(float) if volume is not None and len(volume) >= 65 else None

    highs = _local_highs(p)
    lows  = _local_lows(p)

    if len(highs) < 2 or len(lows) < 2:
        return {"has_vcp": False, "score": 0, "pivot": None}

    # 최근 3개 고점 → 각 고점 이후 최저점까지의 조정폭 계산
    contractions: list[dict] = []
    for h_idx, h_val in highs[-4:]:           # 최근 최대 4개 고점
        # 해당 고점 이후 다음 고점 전까지의 최저점
        next_highs = [(i, v) for i, v in highs if i > h_idx]
        end_idx    = next_highs[0][0] if next_highs else len(p) - 1
        sub_lows   = [(i, v) for i, v in lows if h_idx < i <= end_idx]
        if not sub_lows:
            continue
        l_idx, l_val = min(sub_lows, key=lambda x: x[1])
        depth = (h_val - l_val) / h_val

        vol_ratio = None
        if vol is not None:
            base    = float(np.mean(vol[:20])) or 1.0
            segment = float(np.mean(vol[h_idx:l_idx + 1])) if l_idx > h_idx else base
            vol_ratio = segment / base

        contractions.append({"depth": depth, "vol_ratio": vol_ratio,
                              "h_idx": h_idx, "l_idx": l_idx})

    if len(contractions) < 2:
        return {"has_vcp": False, "score": 0, "pivot": None}

    depths         = [c["depth"] for c in contractions]
    vols_list      = [c["vol_ratio"] for c in contractions if c["vol_ratio"] is not None]
    depth_shrinks  = all(depths[i] < depths[i - 1] for i in range(1, len(depths)))
    vol_declining  = len(vols_list) < 2 or all(vols_list[i] < vols_list[i - 1]
                                                for i in range(1, len(vols_list)))
    final_tight    = depths[-1] < 0.15       # 마지막 조정 15% 미만

    # 피벗: 최근 20일 이내 로컬 고점 상단 +0.5%
    recent_highs = [(i, v) for i, v in highs if i >= len(p) - 20]
    pivot = round(float(recent_highs[-1][1]) * 1.005, 2) if recent_highs else None

    # 점수 산정
    score = 0
    if depth_shrinks: score += 20
    if vol_declining: score += 10
    if final_tight:   score += 10
    if len(contractions) >= 3: score += 5     # 3+ 수축
    if pivot:
        dist = (pivot - p[-1]) / pivot
        if 0 <= dist < 0.05:
            score += 5                         # 피벗 5% 이내

    has_vcp = bool(depth_shrinks and final_tight and len(contractions) >= 2)

    return {
        "has_vcp":            has_vcp,
        "score":              int(score),
        "pivot":              float(pivot) if pivot is not None else None,
        "contractions":       int(len(contractions)),
        "final_depth_pct":    float(round(depths[-1] * 100, 1)),
        "vol_declining":      bool(vol_declining),
    }


# ── 피벗 근접도 점수 ──────────────────────────────────────────

def _proximity_score(current: float, pivot: float | None) -> int:
    if pivot is None:
        return 0
    dist = (pivot - current) / pivot
    if dist < 0:       return 5   # 이미 돌파
    if dist < 0.02:    return 20
    if dist < 0.05:    return 15
    if dist < 0.10:    return 10
    return 5


# ── 메인 스크리닝 ─────────────────────────────────────────────

def screen_vcp(min_rs: float = 80.0, top_n: int = 20) -> list[dict]:
    """
    RS 캐시(rs90.json) 기반 후보군에서 Stage2 + VCP 스크리닝.
    결과: vcp_top20.json 저장 + list[dict] 반환
    """
    rs_file = CACHE_DIR / "rs90.json"
    rs_map: dict[str, float] = {}
    if rs_file.exists():
        rs_map = {s["ticker"]: s["rs_rating"]
                  for s in json.loads(rs_file.read_text()).get("stocks", [])}

    candidates = [t for t, r in rs_map.items() if r >= min_rs]
    if not candidates:
        print("  RS 캐시 없음 — universe 상위 200종목 대체 사용")
        from data_utils import get_universe_tickers
        candidates = get_universe_tickers()[:200]

    print(f"  VCP 스크리닝 대상: {len(candidates)}개")
    results: list[dict] = []

    for i in range(0, len(candidates), 20):
        batch = candidates[i: i + 20]
        try:
            raw = yf.download(
                batch, period="1y", auto_adjust=True,
                progress=False, threads=True
            )
            if raw.empty:
                continue

            for ticker in batch:
                try:
                    if isinstance(raw.columns, pd.MultiIndex):
                        close  = raw["Close"][ticker].dropna()
                        volume = raw["Volume"][ticker].dropna()
                    else:
                        close  = raw["Close"].dropna()
                        volume = raw["Volume"].dropna()

                    if len(close) < 65:
                        continue

                    stage = check_stage2(close)
                    if not stage["is_stage2"]:
                        continue

                    vcp = detect_vcp(close, volume)
                    prox = _proximity_score(float(close.iloc[-1]), vcp.get("pivot"))

                    results.append({
                        "ticker":              ticker,
                        "total_score":         int(stage["score"] + vcp["score"] + prox),
                        "stage2_score":        int(stage["score"]),
                        "vcp_score":           int(vcp["score"]),
                        "proximity_score":     int(prox),
                        "has_vcp":             bool(vcp["has_vcp"]),
                        "pivot":               vcp.get("pivot"),
                        "current_price":       round(float(close.iloc[-1]), 2),
                        "rs_rating":           float(rs_map.get(ticker, 0)),
                        "ma50":                float(stage["ma50"]),
                        "ma200":               float(stage["ma200"]),
                        "final_depth_pct":     float(vcp.get("final_depth_pct", 0)),
                        "contractions":        int(vcp.get("contractions", 0)),
                    })
                except Exception:
                    continue
        except Exception:
            continue

        if (i // 20 + 1) % 5 == 0:
            print(f"  진행: {min(i + 20, len(candidates))}/{len(candidates)}")

    results.sort(key=lambda x: (x["has_vcp"], x["total_score"]), reverse=True)
    top = results[:top_n]

    out = {
        "date":          datetime.now().strftime("%Y-%m-%d"),
        "total_screened":len(candidates),
        "stage2_count":  len(results),
        "vcp_count":     sum(1 for r in results if r["has_vcp"]),
        "stocks":        top,
    }
    (CACHE_DIR / "vcp_top20.json").write_text(json.dumps(out, indent=2))
    print(f"  Stage2: {len(results)}개  VCP: {out['vcp_count']}개  TOP{top_n} 저장")
    return top


if __name__ == "__main__":
    stocks = screen_vcp()
    for s in stocks[:5]:
        print(f"{s['ticker']:6s} VCP:{s['has_vcp']}  Score:{s['total_score']:3d}"
              f"  Pivot:{s['pivot']}  RS:{s['rs_rating']:.0f}")
