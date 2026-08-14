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
from data_utils import CACHE_DIR, market_today


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


# ── Cup with Handle 탐지 ─────────────────────────────────────

def detect_cup_with_handle(close: pd.Series) -> dict:
    """
    Cup with Handle 패턴 탐지.
    - Cup: U자형 베이스, 깊이 12~50%, 기간 7~52주
    - Handle: 컵 고점 대비 소폭 조정(3~20%), 우측 반등
    - Pivot: 핸들 최고점 +0.5%
    """
    if len(close) < 100:
        return {"has_cwh": False, "cwh_score": 0}

    p = close.values.astype(float)
    cup_len = min(len(p), 252)
    p_cup   = p[-cup_len:]

    # 왼쪽 고점 (전체의 앞 60% 구간)
    left_end      = max(int(len(p_cup) * 0.60), 40)
    left_peak_idx = int(np.argmax(p_cup[:left_end]))
    left_peak_val = float(p_cup[left_peak_idx])

    if left_peak_idx >= len(p_cup) - 40:
        return {"has_cwh": False, "cwh_score": 0}

    # 컵 바닥: 왼쪽 고점 이후~75% 지점 사이 최저점
    after_peak   = p_cup[left_peak_idx:]
    handle_start = max(int(len(after_peak) * 0.75), 10)
    cup_section  = after_peak[:handle_start]
    if len(cup_section) < 15:
        return {"has_cwh": False, "cwh_score": 0}

    cup_bot_rel = int(np.argmin(cup_section))
    cup_bot_val = float(cup_section[cup_bot_rel])
    cup_depth   = (left_peak_val - cup_bot_val) / left_peak_val

    if not (0.12 <= cup_depth <= 0.50):
        return {"has_cwh": False, "cwh_score": 0,
                "cup_depth_pct": round(cup_depth * 100, 1)}

    # 오른쪽 고점 (컵 바닥 ~ 핸들 시작 전 최고점)
    cup_bot_abs  = left_peak_idx + cup_bot_rel
    right_search = p_cup[cup_bot_abs : left_peak_idx + handle_start]
    if len(right_search) < 8:
        return {"has_cwh": False, "cwh_score": 0,
                "cup_depth_pct": round(cup_depth * 100, 1)}

    right_lip_val = float(np.max(right_search))
    lip_diff      = abs(right_lip_val - left_peak_val) / left_peak_val

    if lip_diff > 0.10:
        return {"has_cwh": False, "cwh_score": 0,
                "cup_depth_pct": round(cup_depth * 100, 1)}

    # 핸들: 마지막 구간 (오른쪽 75% 이후)
    handle_section = p_cup[left_peak_idx + handle_start :]
    if len(handle_section) < 5:
        handle_section = p_cup[-20:]

    handle_high  = float(np.max(handle_section))
    handle_low   = float(np.min(handle_section))
    handle_depth = (handle_high - handle_low) / handle_high if handle_high > 0 else 0
    has_handle   = (0.02 <= handle_depth <= 0.20) and (handle_low > cup_bot_val)

    pivot         = round(handle_high * 1.005, 2)
    current       = float(p[-1])
    dist_to_pivot = (pivot - current) / pivot if pivot > 0 else 0

    score = 0
    if 0.15 <= cup_depth <= 0.33: score += 25
    elif 0.12 <= cup_depth <= 0.50: score += 12
    if lip_diff <= 0.05: score += 20
    elif lip_diff <= 0.10: score += 10
    if has_handle:
        score += 20
        if handle_depth <= 0.12: score += 10
    if -0.10 <= dist_to_pivot <= 0.05: score += 10

    has_cwh = bool(has_handle and lip_diff <= 0.10 and 0.12 <= cup_depth <= 0.50)
    return {
        "has_cwh":          has_cwh,
        "cwh_score":        min(85, score),
        "cup_depth_pct":    round(cup_depth * 100, 1),
        "handle_depth_pct": round(handle_depth * 100, 1) if has_handle else 0,
        "cwh_pivot":        float(pivot),
        "cwh_dist_pct":     round(dist_to_pivot * 100, 1),
        "lip_diff_pct":     round(lip_diff * 100, 1),
    }


# ── Flat Base 탐지 (IBD 최선호 베이스 패턴) ──────────────────

def detect_flat_base(close: pd.Series) -> dict:
    """
    Flat Base (플랫 베이스) 탐지.
    - 기간: 5~15주 (25~75 거래일) 타이트한 가격 수렴
    - 조정폭: 최대 15% 이내 (이상적으로 10% 이하)
    - 거래량: 베이스 기간 중 감소 추세 (매집 완료 신호)
    - 돌파: 현재가가 베이스 최고점 근처 또는 초과
    조건 충족 시 누적 매집 완료, 돌파 임박 신호
    """
    if len(close) < 30:
        return {"has_flat_base": False, "flat_base_score": 0}

    p = close.values.astype(float)

    # 베이스 구간: 최근 25~75봉 탐색 (5~15주)
    best = {"has_flat_base": False, "flat_base_score": 0,
            "fb_depth_pct": 0.0, "fb_weeks": 0,
            "fb_breakout_pct": 0.0, "fb_breaking": False}

    for span in (50, 35, 25):
        if len(p) < span + 5:
            continue
        base = p[-(span):]
        b_high = float(np.max(base))
        b_low  = float(np.min(base))
        depth  = (b_high - b_low) / b_high if b_high > 0 else 1

        if depth > 0.15:          # 조정 15% 초과 → 플랫 베이스 아님
            continue

        current = float(p[-1])
        dist_to_break = (b_high - current) / b_high if b_high > 0 else 0
        breaking = current >= b_high * 0.99   # 1% 이내 돌파 포함

        # 거래량 감소 확인은 close만 있으므로 가격 변동성으로 대리
        # 후반부 변동성 < 전반부 변동성 → 수렴
        half = span // 2
        vol_early = float(np.std(base[:half]))
        vol_late  = float(np.std(base[half:]))
        vol_contracting = vol_late < vol_early

        score = 0
        if depth <= 0.10:         score += 30   # 10% 이하 매우 타이트
        elif depth <= 0.15:       score += 20
        if vol_contracting:       score += 25   # 변동성 수렴
        if span >= 35:            score += 15   # 충분한 기간
        if dist_to_break <= 0.03: score += 15   # 돌파 임박
        if breaking:              score += 10

        has_fb = bool(depth <= 0.15 and vol_contracting)
        if has_fb and score > best["flat_base_score"]:
            best = {
                "has_flat_base":    True,
                "flat_base_score":  min(95, score),
                "fb_depth_pct":     round(depth * 100, 1),
                "fb_weeks":         round(span / 5),
                "fb_breakout_pct":  round(dist_to_break * 100, 1),
                "fb_breaking":      bool(breaking),
            }

    return best


# ── 하강 삼각수렴 탐지 (상승 반전 시그널) ────────────────────

def detect_descending_triangle(close: pd.Series) -> dict:
    """
    하강 삼각수렴(Descending Triangle / Falling Wedge) 탐지.
    - 하단: 수평 지지선 (저점 2회 이상 터치, 편차 ≤3%)
    - 상단: 하락하는 저항선 (고점이 우하향)
    - 수렴: 간격 축소 → 지지선 이탈 OR 저항선 상향 돌파 시 강한 모멘텀
    - 상승 시그널: 지지선 근처에서 저항선 기울기가 플래트해질 때 반등 확률↑
    """
    if len(close) < 30:
        return {"has_desc_tri": False, "desc_tri_score": 0}

    p       = close.values.astype(float)
    lookback = min(len(p), 80)
    p_lb    = p[-lookback:]

    highs = _local_highs(p_lb, w=4)
    lows  = _local_lows(p_lb, w=4)

    if len(highs) < 2 or len(lows) < 2:
        return {"has_desc_tri": False, "desc_tri_score": 0}

    # 수평 지지선: 최근 저점들이 좁은 범위 내
    rl     = lows[-4:] if len(lows) >= 4 else lows
    l_vals = [v for _, v in rl]
    support     = float(np.mean(l_vals))
    l_spread    = (max(l_vals) - min(l_vals)) / support if support > 0 else 1
    flat_sup    = l_spread <= 0.03

    # 하락 저항선: 고점에 선형 회귀 → 기울기 < 0
    rh    = highs[-4:] if len(highs) >= 4 else highs
    h_idx = np.array([i for i, _ in rh], dtype=float)
    h_val = np.array([v for _, v in rh], dtype=float)
    if len(h_idx) >= 2:
        slope = float(np.polyfit(h_idx, h_val, 1)[0])
        desc_resist = slope < 0
    else:
        slope = 0.0
        desc_resist = False

    # 수렴 확인
    if len(rh) >= 2 and len(rl) >= 2:
        first_gap = h_val[0] - l_vals[0]
        last_gap  = h_val[-1] - l_vals[-1]
        converging = (0 < last_gap < first_gap)
    else:
        converging = False

    current      = float(p[-1])
    # 상승 반전 시그널: 현재가가 지지선 근처 (±5%) + 저항선 기울기 완만해지는 중
    dist_to_sup  = (current - support) / support if support > 0 else 0
    near_support = dist_to_sup < 0.05          # 지지선 5% 이내
    slope_flat   = slope > -0.05 * support / len(p_lb)  # 기울기 완만
    # 저항선 돌파 (상승 반전 확인)
    resist_now   = h_val[-1] + slope * (lookback - h_idx[-1]) if len(h_idx) else current
    breaking_up  = current > resist_now

    score = 0
    if flat_sup:       score += 30
    if desc_resist:    score += 25
    if converging:     score += 15
    if near_support:   score += 10
    if slope_flat:     score += 10
    if breaking_up:    score += 15
    if len(rl) >= 3:   score += 5

    has_desc_tri = bool(flat_sup and desc_resist and converging)
    return {
        "has_desc_tri":       has_desc_tri,
        "desc_tri_score":     min(100, score),
        "support_level":      round(support, 2),
        "l_spread_pct":       round(l_spread * 100, 1),
        "resist_slope":       round(slope, 5),
        "desc_tri_dist_pct":  round(dist_to_sup * 100, 1),
        "desc_tri_breaking":  bool(breaking_up),
        "desc_near_support":  bool(near_support),
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


# ── 쿨러메기(Qullamaggie) 분석 ────────────────────────────────

def _qullamaggie_analysis(rs: float, has_vcp: bool, pivot, current: float,
                           final_depth: float, contractions: int,
                           vol_spike: float, vol_declining: bool) -> dict:
    """
    쿨러메기(Kristjan Kullamägi) 스타일 분석.
    EP 이후 타이트 베이스 → 피벗 돌파 전략.

    Signals:
      BUY_ZONE  — 피벗 5% 이내 대기, RS≥85, VCP 확정
      BREAKOUT  — 피벗 돌파 중 (0~15% 위)
      EXTENDED  — 피벗 대비 15%+ 상승 (추격 위험)
      WATCH     — 조건 부분 충족, 모니터링
      AVOID     — 조건 미달
    """
    score = 0
    # RS (20점)
    score += (20 if rs >= 90 else 15 if rs >= 85 else 10 if rs >= 80 else 5 if rs >= 75 else 0)
    # 타이트 베이스 조정폭 (25점) — EP 이후 작은 수축이 이상적
    score += (25 if final_depth < 5 else 20 if final_depth < 10
              else 12 if final_depth < 15 else 5 if final_depth < 20 else 0)
    # 수축 횟수 (10점)
    score += (10 if contractions >= 3 else 6 if contractions >= 2 else 2 if contractions >= 1 else 0)
    # EP 거래량 급등 (30점) — 최근 5일 최고 / 50일 평균
    score += (30 if vol_spike >= 3.0 else 25 if vol_spike >= 2.5 else 20 if vol_spike >= 2.0
              else 12 if vol_spike >= 1.5 else 5 if vol_spike >= 1.2 else 0)
    # 거래량 감소 (5점) — 수축 중 거래량 감소
    if vol_declining:
        score += 5
    # 피벗 근접도 (10점)
    if pivot:
        d = (pivot - current) / pivot
        score += (10 if d < 0 else 10 if d < 0.02 else 7 if d < 0.05 else 4 if d < 0.10 else 0)

    # 신호 판정 (David Ryan: 피벗 20% 초과 = EXTENDED)
    if pivot:
        dist = (pivot - current) / pivot
        if dist < -0.20:
            signal = "EXTENDED"
        elif dist < 0:
            signal = "BREAKOUT"
        elif dist < 0.05 and has_vcp and rs >= 85 and vol_spike >= 1.3:
            signal = "BUY_ZONE"
        elif dist < 0.10 and (has_vcp or rs >= 85):
            signal = "WATCH"
        else:
            signal = "AVOID"
    else:
        signal = "WATCH" if (rs >= 85 and has_vcp) else "AVOID"

    return {
        "qullamaggie_score":  min(100, score),
        "qullamaggie_signal": signal,
    }


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
        print("  RS 캐시 없음 — NDX100 전종목 대체 사용")
        from data_utils import get_ndx100_tickers
        candidates = get_ndx100_tickers()

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

                    vcp  = detect_vcp(close, volume)
                    prox = _proximity_score(float(close.iloc[-1]), vcp.get("pivot"))

                    # 거래량 급등 비율 (최근 5일 최고 / 50일 평균) — EP 감지용
                    vol_arr = volume.values.astype(float)
                    if len(vol_arr) >= 55:
                        vol_avg50 = float(np.mean(vol_arr[-55:-5]))
                        vol_spike = float(np.max(vol_arr[-5:])) / vol_avg50 if vol_avg50 > 0 else 1.0
                    elif len(vol_arr) >= 10:
                        vol_avg50 = float(np.mean(vol_arr[:-5]))
                        vol_spike = float(np.max(vol_arr[-5:])) / vol_avg50 if vol_avg50 > 0 else 1.0
                    else:
                        vol_spike = 1.0

                    rs_val = float(rs_map.get(ticker, 0))
                    qg = _qullamaggie_analysis(
                        rs           = rs_val,
                        has_vcp      = bool(vcp["has_vcp"]),
                        pivot        = vcp.get("pivot"),
                        current      = float(close.iloc[-1]),
                        final_depth  = float(vcp.get("final_depth_pct", 0)),
                        contractions = int(vcp.get("contractions", 0)),
                        vol_spike    = vol_spike,
                        vol_declining= bool(vcp.get("vol_declining", False)),
                    )

                    # David Ryan 20% 뻗음 체크 (피벗 대비 20% 이상 상승 → 진입 제외)
                    pivot_val = vcp.get("pivot")
                    current_price = float(close.iloc[-1])
                    if pivot_val and float(pivot_val) > 0:
                        extension_pct = (current_price - float(pivot_val)) / float(pivot_val) * 100
                        david_ryan_extended = extension_pct > 20.0
                    else:
                        extension_pct = None
                        david_ryan_extended = False

                    cwh       = detect_cup_with_handle(close)
                    asc_tri   = detect_flat_base(close)
                    desc_tri  = detect_descending_triangle(close)

                    results.append({
                        "ticker":              ticker,
                        "total_score":         int(stage["score"] + vcp["score"] + prox),
                        "stage2_score":        int(stage["score"]),
                        "vcp_score":           int(vcp["score"]),
                        "proximity_score":     int(prox),
                        "has_vcp":             bool(vcp["has_vcp"]),
                        "pivot":               vcp.get("pivot"),
                        "current_price":       round(current_price, 2),
                        "rs_rating":           rs_val,
                        "ma50":                float(stage["ma50"]),
                        "ma200":               float(stage["ma200"]),
                        "final_depth_pct":     float(vcp.get("final_depth_pct", 0)),
                        "contractions":        int(vcp.get("contractions", 0)),
                        "vol_declining":       bool(vcp.get("vol_declining", False)),
                        "vol_spike_ratio":     round(vol_spike, 2),
                        "pivot_extension_pct": round(extension_pct, 1) if extension_pct is not None else None,
                        "david_ryan_extended": david_ryan_extended,
                        **qg,
                        **cwh,
                        **asc_tri,
                        **desc_tri,
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
        "date":          market_today(),
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
