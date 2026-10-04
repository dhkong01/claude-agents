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
    제공하고 2년물은 없어, 공식 공개 CSV(무료·무인증)로 보완한다.
    일반 요청(urllib)은 일부 네트워크에서 응답이 행(hang)되거나 차단되는 경우가
    있어, Yahoo Finance·CNN 차단 우회에 쓰는 것과 동일한 curl_cffi 브라우저 위장
    세션(YF_SESSION)을 우선 쓰고, 세션이 없을 때만 urllib으로 폴백한다."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    text = None

    if YF_SESSION is not None:
        for attempt in range(2):
            try:
                resp = YF_SESSION.get(url, timeout=15)
                if resp.status_code == 200:
                    text = resp.text
                    break
                print(f"[macro_analyzer] FRED {series_id} curl_cffi HTTP {resp.status_code}(시도 {attempt + 1}/2)", file=sys.stderr)
            except Exception as e:
                print(f"[macro_analyzer] FRED {series_id} curl_cffi 조회 실패(시도 {attempt + 1}/2): {e}", file=sys.stderr)

    if text is None:
        import urllib.request
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8")
        except Exception as e:
            print(f"[macro_analyzer] FRED {series_id} urllib 조회 실패: {e}", file=sys.stderr)
            return None

    rows = [r.strip() for r in text.strip().splitlines() if r.strip()]
    for row in reversed(rows[1:]):  # 헤더 제외, 최신 값부터 탐색 (결측치 "." 스킵)
        parts = row.split(",")
        if len(parts) == 2 and parts[1] != ".":
            return float(parts[1])
    return None


def _load_prev_signal(key: str):
    """직전 실행의 cache/macro.json에서 지표값을 읽는다 — 당일 조회가 실패해도
    화면이 N/A로 비는 대신 직전값을 유지하기 위한 폴백."""
    try:
        prev = json.loads((CACHE_DIR / "macro.json").read_text(encoding="utf-8"))
        return prev.get("signals", {}).get(key)
    except Exception:
        return None


def _fetch_fear_greed() -> dict | None:
    """CNN Fear & Greed Index — CNN이 쓰는 비공식 공개 엔드포인트(dataviz.cnn.io).
    일반 요청(urllib/requests)은 봇 차단(HTTP 418)되어, Yahoo Finance 차단
    회피에 쓰는 것과 동일한 curl_cffi 브라우저 위장 세션(YF_SESSION)을 재사용한다."""
    if YF_SESSION is None:
        return None
    try:
        resp = YF_SESSION.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"Referer": "https://edition.cnn.com/markets/fear-and-greed"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        fg = resp.json().get("fear_and_greed", {})
        if "score" not in fg:
            return None
        return {"score": round(fg["score"], 1), "rating": fg.get("rating", "")}
    except Exception as e:
        print(f"[macro_analyzer] CNN Fear&Greed 조회 실패: {e}", file=sys.stderr)
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
    else:
        prev_yield2y = _load_prev_signal("yield2y")
        if prev_yield2y is not None:
            signals["yield2y"] = prev_yield2y
            print(f"[macro_analyzer] 2년물 금리 조회 실패 — 직전값({prev_yield2y}%) 유지", file=sys.stderr)

    fear_greed = _fetch_fear_greed()
    if fear_greed is not None:
        signals["fear_greed_score"] = fear_greed["score"]
        signals["fear_greed_rating"] = fear_greed["rating"]
    else:
        prev_fg = _load_prev_signal("fear_greed_score")
        prev_fg_rating = _load_prev_signal("fear_greed_rating")
        if prev_fg is not None:
            signals["fear_greed_score"] = prev_fg
            signals["fear_greed_rating"] = prev_fg_rating
            print(f"[macro_analyzer] CNN 공포·탐욕지수 조회 실패 — 직전값({prev_fg}) 유지", file=sys.stderr)

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
