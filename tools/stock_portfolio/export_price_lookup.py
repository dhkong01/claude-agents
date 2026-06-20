"""
인기 종목의 현재가를 docs/data/price_lookup.json 으로 저장
GitHub Actions에서 매일 실행 → PWA 편집기에서 신규 종목 자동완성에 사용
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import yfinance as yf

POPULAR_TICKERS = sorted(set([
    # Mega cap
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "BRK-B",
    # Semiconductor / Hardware
    "AMD", "INTC", "QCOM", "MU", "SMCI", "ARM", "MRVL", "LRCX", "AMAT", "KLAC", "ASML",
    "TXN", "MCHP", "ON", "SWKS", "MPWR",
    # Software / Cloud
    "ORCL", "CRM", "SAP", "NOW", "ADBE", "INTU", "SNOW", "DDOG", "ZS", "CRWD", "PANW",
    "NET", "GTLB", "PLTR", "WDAY", "HUBS", "MDB", "ESTC", "TEAM", "OKTA",
    # AI / Speculative Growth
    "SOUN", "IONQ", "RGTI", "QBTS", "RKLB", "LUNR", "ASTS", "ACHR",
    "MSTR", "COIN", "HOOD", "RBLX",
    # Healthcare / Biotech
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "PFE", "AMGN", "GILD",
    "VKTX", "RXRX", "BEAM", "EDIT", "MRNA", "BNTX",
    # Finance
    "JPM", "V", "MA", "GS", "BAC", "WFC", "BX", "KKR", "SCHW", "AXP", "BLK",
    # Consumer / Retail
    "WMT", "COST", "TGT", "HD", "LOW", "NKE", "SBUX",
    # Energy
    "XOM", "CVX", "OXY", "SLB",
    # Transport / EV
    "UBER", "LYFT", "RIVN", "LCID", "NIO", "XPEV", "LI",
    # ETF
    "SPY", "QQQ", "IWM", "SOXX", "SMH", "XLK", "XLF", "XLE",
    "ARKK", "ARKW", "ARKG", "SOXL", "TQQQ", "UVXY",
]))


def _extract_price(data, ticker: str) -> float | None:
    """yfinance 버전 차이(MultiIndex/단일) 모두 처리"""
    try:
        close = data["Close"]
    except (KeyError, AttributeError):
        return None

    # 배치 다운로드: columns = ['AAPL', 'MSFT', ...]
    if hasattr(close, "columns"):
        # 일반 컬럼
        if ticker in close.columns:
            s = close[ticker].dropna()
            return round(float(s.iloc[-1]), 2) if len(s) else None
        # MultiIndex 컬럼: ('Close', 'AAPL') 형태
        for col in close.columns:
            if isinstance(col, tuple) and ticker in col:
                s = close[col].dropna()
                return round(float(s.iloc[-1]), 2) if len(s) else None
        return None

    # 단일 종목 다운로드: Series
    if hasattr(close, "iloc"):
        s = close.dropna()
        return round(float(s.iloc[-1]), 2) if len(s) else None

    return None


def run():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[price_lookup] {len(POPULAR_TICKERS)}개 종목 가격 조회 시작 ({today})...")

    # 배치 다운로드
    try:
        data = yf.download(
            POPULAR_TICKERS, period="1d",
            progress=False, auto_adjust=True, threads=True,
        )
    except Exception as e:
        print(f"[price_lookup] 배치 다운로드 실패: {e}", file=sys.stderr)
        data = None

    prices = {}

    if data is not None and not data.empty:
        for t in POPULAR_TICKERS:
            p = _extract_price(data, t)
            if p:
                prices[t] = p

    # 누락 종목 개별 재시도
    missing = [t for t in POPULAR_TICKERS if t not in prices]
    if missing:
        print(f"[price_lookup] 개별 재시도: {missing}")
        for t in missing:
            try:
                d = yf.download(t, period="1d", progress=False, auto_adjust=True)
                p = _extract_price(d, t)
                if p:
                    prices[t] = p
            except Exception:
                pass

    failed = [t for t in POPULAR_TICKERS if t not in prices]
    if failed:
        print(f"[price_lookup] 조회 실패 종목: {failed}", file=sys.stderr)

    out = {
        "date": today,
        "count": len(prices),
        "prices": prices,
    }

    dest = Path(__file__).parent.parent.parent / "docs" / "data" / "price_lookup.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[price_lookup] 완료: {len(prices)}/{len(POPULAR_TICKERS)}개 → {dest.name}")
    return len(prices) > 0


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
