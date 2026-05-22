"""
CANSLIM scorer for RS>=90 stocks.
Each of 7 criteria scored 0-10. Total /70.
M criterion injected by orchestrator from macro analysis.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from data_utils import CACHE_DIR


def _score_c(info: dict) -> int:
    g = info.get("earningsQuarterlyGrowth")
    if g is None:
        return 5
    return 10 if g >= 0.25 else (7 if g >= 0.15 else (4 if g >= 0 else 1))


def _score_a(info: dict) -> int:
    g = info.get("earningsGrowth")
    if g is None:
        return 5
    return 10 if g >= 0.25 else (7 if g >= 0.15 else (4 if g >= 0 else 1))


def _score_n(info: dict) -> int:
    high = info.get("fiftyTwoWeekHigh", 0)
    price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
    if not high or not price:
        return 5
    r = price / high
    return 10 if r >= 0.95 else (7 if r >= 0.90 else (4 if r >= 0.80 else 1))


def _score_s(info: dict, hist) -> int:
    avg = info.get("averageVolume", 0)
    recent = float(hist["Volume"].tail(10).mean()) if (hist is not None and not hist.empty) else 0
    if not avg or not recent:
        return 5
    r = recent / avg
    return 10 if r >= 1.3 else (7 if r >= 1.0 else (4 if r >= 0.7 else 1))


def _score_l(ticker: str) -> int:
    rs_map: dict[str, float] = {}
    rs_file = CACHE_DIR / "rs90.json"
    if rs_file.exists():
        rs_map.update({s["ticker"]: s["rs_rating"]
                       for s in json.loads(rs_file.read_text()).get("stocks", [])})
    # 유저 포트폴리오 RS 캐시도 병합
    up_file = CACHE_DIR / "user_portfolio_rs.json"
    if up_file.exists():
        rs_map.update(json.loads(up_file.read_text(encoding="utf-8")).get("ratings", {}))
    rs = rs_map.get(ticker, 0)
    return 10 if rs >= 90 else (7 if rs >= 80 else (3 if rs >= 60 else 0))


def _score_i(info: dict) -> int:
    pct = info.get("heldPercentInstitutions")
    if pct is None:
        return 5
    return 10 if pct >= 0.60 else (7 if pct >= 0.40 else (4 if pct >= 0.20 else 1))


def score_canslim(ticker: str) -> dict:
    import yfinance as yf

    try:
        stk = yf.Ticker(ticker)
        info = stk.info
        hist = stk.history(period="3mo")
        scores = {
            "C": _score_c(info),
            "A": _score_a(info),
            "N": _score_n(info),
            "S": _score_s(info, hist),
            "L": _score_l(ticker),
            "I": _score_i(info),
            "M": 7,  # placeholder; orchestrator replaces with macro m_score
        }
        return {
            "ticker": ticker,
            "canslim_score": sum(scores.values()),
            "scores": scores,
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap", 0),
            "price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
        }
    except Exception as e:
        return {"ticker": ticker, "canslim_score": 0, "error": str(e)}


def analyze_canslim(rs90_stocks: list[dict], top_n: int = 10) -> list[dict]:
    results = []
    for i, s in enumerate(rs90_stocks, 1):
        r = score_canslim(s["ticker"])
        if "error" not in r:
            r["rs_rating"] = s.get("rs_rating", 0)
            results.append(r)
        if i % 10 == 0:
            print(f"  진행: {i}/{len(rs90_stocks)}")

    results.sort(key=lambda x: x["canslim_score"], reverse=True)
    top = results[:top_n]

    out = {"date": datetime.now().strftime("%Y-%m-%d"), "analyzed": len(results), "top10": top}
    (CACHE_DIR / "canslim_top10.json").write_text(json.dumps(out, indent=2, default=str))
    return top


if __name__ == "__main__":
    rs_file = CACHE_DIR / "rs90.json"
    if not rs_file.exists():
        print("rs_screener.py를 먼저 실행하세요")
        sys.exit(1)
    rs90 = json.loads(rs_file.read_text())["stocks"]
    top10 = analyze_canslim(rs90)
    print(json.dumps([{"ticker": s["ticker"], "score": s["canslim_score"]} for s in top10], indent=2))
