"""
Macro analysis using yfinance proxies.
Determines market phase: RISK_ON / TRANSITIONAL / RISK_OFF
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from data_utils import CACHE_DIR, market_today, YF_SESSION

MACRO_TICKERS = {
    "market":   "^GSPC",
    "vix":      "^VIX",
    "yield10y": "^TNX",
    "yield30y": "^TYX",
    "dollar":   "UUP",    # USD ETF (DXY proxy, more reliable than futures)
    "gold":     "GLD",
    "oil":      "USO",
    "nasdaq":   "QQQ",
}


def _fetch_fred_series(series_id: str) -> float | None:
    """FRED(연준 공개 데이터)에서 최신 값을 가져온다.
    Yahoo Finance 인덱스 티커는 ^IRX(13주)·^FVX(5년)·^TNX(10년)·^TYX(30년)만
    제공하고 2년물은 없어, 공식 공개 CSV(무료·무인증)로 보완한다."""
    import urllib.request

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8")
        rows = [r.strip() for r in text.strip().splitlines() if r.strip()]
        for row in reversed(rows[1:]):  # 헤더 제외, 최신 값부터 탐색 (결측치 "." 스킵)
            parts = row.split(",")
            if len(parts) == 2 and parts[1] != ".":
                return float(parts[1])
        return None
    except Exception as e:
        print(f"[macro_analyzer] FRED {series_id} 조회 실패: {e}", file=sys.stderr)
        return None


def _fetch_indicator(ticker: str) -> dict | None:
    import yfinance as yf

    try:
        hist = yf.Ticker(ticker, session=YF_SESSION).history(period="1y")
        if hist.empty:
            return None
        close = hist["Close"]
        return {
            "price": float(close.iloc[-1]),
            "ma50":  float(close.tail(50).mean()),
            "ma200": float(close.tail(200).mean()) if len(close) >= 200 else None,
            "ret1m": float(close.iloc[-1] / close.iloc[-22] - 1) if len(close) >= 22 else None,
            "ret3m": float(close.iloc[-1] / close.iloc[-63] - 1) if len(close) >= 63 else None,
        }
    except Exception:
        return None


def analyze_macro() -> dict:
    data = {name: _fetch_indicator(ticker) for name, ticker in MACRO_TICKERS.items()}
    signals: dict = {}

    mkt = data.get("market") or {}
    if mkt:
        above200 = mkt["price"] > (mkt["ma200"] or 0)
        above50  = mkt["price"] > mkt["ma50"]
        signals["market_trend"] = "BULL" if (above200 and above50) else ("BEAR" if not above200 else "SIDEWAYS")
        signals["market_ret3m"] = round(mkt.get("ret3m") or 0, 4)

    vix = data.get("vix") or {}
    if vix:
        v = vix["price"]
        signals["vix_level"]  = round(v, 2)
        signals["volatility"] = "LOW" if v < 15 else ("HIGH" if v > 25 else "NORMAL")

    y10 = data.get("yield10y") or {}
    if y10:
        signals["yield10y"] = round(y10["price"], 2)
        signals["rate_env"] = "HIGH" if y10["price"] > 4.5 else ("LOW" if y10["price"] < 2.5 else "NORMAL")

    y30 = data.get("yield30y") or {}
    if y30:
        signals["yield30y"] = round(y30["price"], 2)

    yield2y = _fetch_fred_series("DGS2")
    if yield2y is not None:
        signals["yield2y"] = round(yield2y, 2)

    dxy = data.get("dollar") or {}
    if dxy and dxy.get("ret1m") is not None:
        signals["dollar_trend"] = (
            "STRENGTHENING" if dxy["ret1m"] > 0.01 else ("WEAKENING" if dxy["ret1m"] < -0.01 else "FLAT")
        )

    trend = signals.get("market_trend", "UNKNOWN")
    vol   = signals.get("volatility", "NORMAL")

    if trend == "BULL" and vol in ("LOW", "NORMAL"):
        phase, m_score = "RISK_ON", 10
        sectors = ["Technology", "Consumer Discretionary", "Industrials", "Financials"]
    elif trend == "BEAR" or vol == "HIGH":
        phase, m_score = "RISK_OFF", 2
        sectors = ["Utilities", "Consumer Staples", "Healthcare", "Energy"]
    else:
        phase, m_score = "TRANSITIONAL", 6
        sectors = ["Healthcare", "Financials", "Energy", "Real Estate"]

    result = {
        "date": market_today(),
        "phase": phase,
        "m_score": m_score,
        "signals": signals,
        "recommended_sectors": sectors,
    }
    (CACHE_DIR / "macro.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    macro = analyze_macro()
    print(json.dumps({k: v for k, v in macro.items() if k != "raw"}, indent=2))
