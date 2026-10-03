"""
시장동향(마켓 펄스) — 주요 지수, 나스닥/S&P500 상승·하락 종목수, 거시경제 지표.
PWA '시장동향' 탭 데이터 소스. → cache/market_pulse.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from data_utils import CACHE_DIR, YF_SESSION, batch_download, get_ndx100_tickers, get_sp500_tickers, market_today
from macro_analyzer import analyze_macro

INDEX_TICKERS = {
    "nasdaq": ("^IXIC", "나스닥종합"),
    "dow":    ("^DJI",  "다우존스"),
    "sp500":  ("^GSPC", "S&P500"),
}


def _fetch_index(ticker: str) -> dict | None:
    import yfinance as yf

    try:
        hist = yf.Ticker(ticker, session=YF_SESSION).history(period="5d")
        close = hist["Close"].dropna()
        if len(close) < 2:
            return None
        price, prev = float(close.iloc[-1]), float(close.iloc[-2])
        return {
            "price": round(price, 2),
            "change": round(price - prev, 2),
            "change_pct": round((price / prev - 1) * 100, 2),
        }
    except Exception as e:
        print(f"[market_pulse] {ticker} 조회 실패: {e}", file=sys.stderr)
        return None


def _calc_breadth(tickers: list[str]) -> dict:
    """S&P500+NASDAQ100 유니버스의 전일 대비 상승/하락/보합 종목수."""
    prices = batch_download(tickers, period="5d")
    if prices.empty or prices.shape[0] < 2:
        return {"total": 0, "advancers": 0, "decliners": 0, "unchanged": 0, "adv_pct": None}

    chg = (prices.iloc[-1] - prices.iloc[-2]).dropna()
    advancers = int((chg > 0).sum())
    decliners = int((chg < 0).sum())
    unchanged = int((chg == 0).sum())
    total = advancers + decliners + unchanged
    return {
        "total": total,
        "advancers": advancers,
        "decliners": decliners,
        "unchanged": unchanged,
        "adv_pct": round(advancers / total * 100, 1) if total else None,
    }


def analyze_market_pulse() -> dict:
    today = market_today()

    indices: dict = {}
    for key, (ticker, label) in INDEX_TICKERS.items():
        data = _fetch_index(ticker)
        if data:
            data["label"] = label
            indices[key] = data

    universe = list(dict.fromkeys(get_sp500_tickers() + get_ndx100_tickers()))
    breadth = _calc_breadth(universe)
    breadth["universe"] = "S&P500+NASDAQ100"

    macro = analyze_macro()
    signals = macro.get("signals", {})

    result = {
        "date": today,
        "indices": indices,
        "breadth": breadth,
        "macro": {
            "phase":        macro.get("phase", ""),
            "m_score":      macro.get("m_score"),
            "vix":          signals.get("vix_level"),
            "volatility":   signals.get("volatility"),
            "yield10y":     signals.get("yield10y"),
            "rate_env":     signals.get("rate_env"),
            "dollar_trend": signals.get("dollar_trend"),
            "market_trend": signals.get("market_trend"),
        },
    }
    (CACHE_DIR / "market_pulse.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    pulse = analyze_market_pulse()
    print(
        f"[market_pulse] 지수 {len(pulse['indices'])}개 · "
        f"브레드스 {pulse['breadth']['advancers']}상승/{pulse['breadth']['decliners']}하락"
        f"(총 {pulse['breadth']['total']}) · 국면 {pulse['macro']['phase']}"
    )
