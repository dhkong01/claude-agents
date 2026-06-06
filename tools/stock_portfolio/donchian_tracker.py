"""
Donchian Channel Tracker — Richard Donchian 추세 추종
진입: 20일 고점 돌파 | 청산: 10일 저점 이탈
TOP 5 선정 + 보유 종목 일일 추적 + 가격 신선도 검증 + SQQQ 헤지 반영
"""
import json
import sys
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from data_utils import CACHE_DIR

ENTRY_PERIOD = 20   # 진입 기준: N일 고점
EXIT_PERIOD  = 10   # 청산 기준: N일 저점


# ── 가격 신선도 검증 ──────────────────────────────────────────

def verify_price_freshness(tickers: list[str] | None = None) -> dict:
    """
    최신 가격 데이터 신선도 점검.
    마지막 거래일 기준 3영업일 이내면 FRESH, 아니면 STALE.
    """
    probe = tickers or ["SPY", "QQQ", "NVDA"]
    try:
        raw = yf.download(probe, period="5d", auto_adjust=True,
                          progress=False, threads=True)
        if raw.empty:
            return {"status": "FAIL", "reason": "empty response"}

        close = (raw["Close"] if isinstance(raw.columns, pd.MultiIndex)
                 else raw[["Close"]]).dropna(how="all")

        latest_dt  = close.index[-1]
        latest_str = latest_dt.strftime("%Y-%m-%d")
        threshold  = (datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d")
        is_fresh   = latest_str >= threshold

        sample: dict[str, float] = {}
        for t in probe[:3]:
            try:
                col = close[t] if t in close.columns else close.iloc[:, 0]
                sample[t] = round(float(col.dropna().iloc[-1]), 2)
            except Exception:
                pass

        result = {
            "status":      "FRESH" if is_fresh else "STALE",
            "latest_date": latest_str,
            "checked_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sample":      sample,
        }
        print(f"  [가격 신선도] {result['status']}  최신 거래일: {latest_str}  "
              f"샘플: {sample}")
        return result
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}


# ── Donchian 채널 계산 ────────────────────────────────────────

def calc_donchian(close: pd.Series) -> dict | None:
    """
    전일까지 N일 고점/저점 기반 채널.
    오늘 종가 > Upper → BREAKOUT, 오늘 종가 < Lower → EXIT
    """
    needed = max(ENTRY_PERIOD, EXIT_PERIOD) + 2
    if len(close) < needed:
        return None

    p       = close.values.astype(float)
    current = p[-1]
    prev    = p[-2]
    upper   = float(np.max(p[-ENTRY_PERIOD - 1: -1]))
    lower   = float(np.min(p[-EXIT_PERIOD  - 1: -1]))

    if current > upper and prev <= upper:
        signal = "BREAKOUT"
    elif current < lower:
        signal = "EXIT"
    else:
        signal = "HOLD"

    return {
        "current":            round(current, 2),
        "donchian_upper":     round(upper, 2),
        "donchian_lower":     round(lower, 2),
        "signal":             signal,
        "dist_to_upper_pct":  round((upper - current) / current * 100, 1),
        "dist_to_lower_pct":  round((current - lower) / current * 100, 1),
        "channel_width_pct":  round((upper - lower) / lower * 100, 1),
    }


# ── SQQQ 현재 Donchian 조회 ───────────────────────────────────

def get_sqqq_channel() -> dict:
    """SQQQ(3× 역 NASDAQ) Donchian 채널 상태 조회"""
    try:
        raw  = yf.download(["SQQQ"], period="3mo", auto_adjust=True,
                            progress=False, threads=False)
        if raw.empty:
            return {}
        close = (raw["Close"]["SQQQ"] if isinstance(raw.columns, pd.MultiIndex)
                 else raw["Close"]).dropna()
        dc = calc_donchian(close)
        if dc:
            dc["ticker"] = "SQQQ"
        return dc or {}
    except Exception:
        return {}


# ── TOP 5 선정 (주간 리밸런싱) ────────────────────────────────

def select_top5(
    canslim_top10: list[dict],
    vcp_top20:     list[dict],
    geo_risk:      dict,
) -> list[dict]:
    """
    Donchian 추세 추종 관점 최종 TOP 5 선정.
    geo_risk["hedge"]를 반영해 종목별 비중(allocation_pct) 산출.
    우선순위: BREAKOUT → CS+VCP 교집합 → final_score
    """
    risk_level = geo_risk.get("risk_level", "MEDIUM")
    hedge      = geo_risk.get("hedge", {
        "long_pct": 100, "sqqq_pct": 0, "cash_pct": 0,
        "per_stock_pct": 20.0, "action": "FULL_LONG",
    })
    per_stock_pct = hedge.get("per_stock_pct", 20.0)

    cs_map   = {s["ticker"]: s for s in canslim_top10}
    vcp_map  = {s["ticker"]: s for s in vcp_top20}
    both     = set(cs_map) & set(vcp_map)
    candidates = (
        list(both) +
        [t for t in vcp_map if t not in both] +
        [t for t in cs_map  if t not in both]
    )[:35]

    if not candidates:
        return []

    try:
        raw = yf.download(candidates, period="3mo", auto_adjust=True,
                          progress=False, threads=True)
    except Exception:
        return []

    scored: list[dict] = []
    for ticker in candidates:
        try:
            close = (raw["Close"][ticker] if isinstance(raw.columns, pd.MultiIndex)
                     else raw["Close"]).dropna()

            if len(close) < 22:
                continue

            dc = calc_donchian(close)
            if dc is None:
                continue

            # 고위험/방어 국면: 손절 여유 < 3% 종목 제외
            if risk_level in ("HIGH",) and dc["dist_to_lower_pct"] < 3:
                continue

            cs_data       = cs_map.get(ticker, {})
            canslim_score = cs_data.get("canslim_score", 0)
            rs_rating     = float(cs_data.get("rs_rating",
                            vcp_map.get(ticker, {}).get("rs_rating", 0)))
            vcp_score     = vcp_map.get(ticker, {}).get("total_score", 0)
            pivot         = vcp_map.get(ticker, {}).get("pivot")
            sector        = cs_data.get("sector", "")

            sig = dc["signal"]
            if sig == "BREAKOUT":
                dc_bonus = 30
            elif dc["dist_to_upper_pct"] < 2:
                dc_bonus = 25
            elif dc["dist_to_upper_pct"] < 5:
                dc_bonus = 15
            else:
                dc_bonus = max(0.0, 10.0 - dc["dist_to_upper_pct"])

            final_score = (
                canslim_score * 0.30 +
                rs_rating     * 0.20 +
                vcp_score     * 0.30 +
                dc_bonus      * 0.20
            )

            scored.append({
                "ticker":            ticker,
                "final_score":       round(final_score, 1),
                "canslim_score":     canslim_score,
                "rs_rating":         rs_rating,
                "vcp_score":         vcp_score,
                "donchian_signal":   sig,
                "current_price":     dc["current"],
                "donchian_upper":    dc["donchian_upper"],
                "donchian_lower":    dc["donchian_lower"],
                "dist_to_upper_pct": dc["dist_to_upper_pct"],
                "dist_to_lower_pct": dc["dist_to_lower_pct"],
                "pivot":             pivot,
                "sector":            sector,
                "in_both":           ticker in both,
                "allocation_pct":    round(per_stock_pct, 1),  # 헤지 반영 비중
            })
        except Exception:
            continue

    scored.sort(
        key=lambda x: (
            x["donchian_signal"] == "BREAKOUT",
            x["in_both"],
            x["final_score"],
        ),
        reverse=True,
    )
    top5 = scored[:5]

    out = {
        "date":   datetime.now().strftime("%Y-%m-%d"),
        "stocks": top5,
        "hedge":  hedge,
    }
    (CACHE_DIR / "donchian_top5.json").write_text(json.dumps(out, indent=2))
    return top5


# ── 보유 종목 일일 추적 ──────────────────────────────────────

def track_portfolio(tickers: list[str]) -> list[dict]:
    """
    보유 종목 + TOP5 Donchian 채널 매일 추적.
    period='3mo' 로 항상 최신 가격 다운로드.
    """
    if not tickers:
        return []

    try:
        raw = yf.download(tickers, period="3mo", auto_adjust=True,
                          progress=False, threads=True)
    except Exception:
        return []

    results: list[dict] = []
    for ticker in tickers:
        try:
            close = (raw["Close"][ticker] if isinstance(raw.columns, pd.MultiIndex)
                     else raw["Close"]).dropna()
            dc = calc_donchian(close)
            if dc:
                results.append({"ticker": ticker, **dc})
        except Exception:
            continue

    (CACHE_DIR / "tracking_daily.json").write_text(
        json.dumps({"date": datetime.now().strftime("%Y-%m-%d"), "data": results}, indent=2)
    )
    return results


if __name__ == "__main__":
    print("=== 가격 신선도 점검 ===")
    freshness = verify_price_freshness()
    print(freshness)

    print("\n=== SQQQ 채널 ===")
    sqqq = get_sqqq_channel()
    print(sqqq)

    print("\n=== 보유 종목 추적 ===")
    test_tickers = ["NVDA", "AAPL", "TSLA", "META", "MSFT"]
    data = track_portfolio(test_tickers)
    for d in data:
        print(f"{d['ticker']:6s} {d.get('signal','?'):9s}  "
              f"현재:{d['current']:7.2f}  "
              f"Upper:{d['donchian_upper']:7.2f}  "
              f"Lower:{d['donchian_lower']:7.2f}")
