"""
인기 종목 100개의 현재가를 docs/data/price_lookup.json 으로 저장
GitHub Actions에서 매일 실행 → PWA 편집기에서 신규 종목 자동완성에 사용
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import yfinance as yf

POPULAR_TICKERS = [
    # Mega cap
    "AAPL","MSFT","NVDA","GOOGL","GOOG","AMZN","META","TSLA","AVGO","BRK-B",
    # Tech
    "AMD","INTC","QCOM","MU","SMCI","ARM","MRVL","LRCX","AMAT","KLAC","ASML",
    "ORCL","CRM","SAP","NOW","ADBE","INTU","SNOW","DDOG","ZS","CRWD","PANW",
    "NET","GTLB","PLTR","COIN","MSTR","HOOD","RBLX",
    # AI / Growth
    "SOUN","IONQ","RGTI","QBTS","ARQQ","BBAI","RKLB","LUNR","ASTS","ACHR",
    # Healthcare / Biotech
    "LLY","UNH","JNJ","ABBV","MRK","PFE","VKTX","RXRX","BEAM","EDIT",
    # Finance
    "JPM","V","MA","GS","BAC","WFC","BX","KKR","SCHW",
    # Consumer / Retail
    "AMZN","WMT","COST","TGT","HD","LOW",
    # Energy
    "XOM","CVX","OXY",
    # Transport / EV
    "UBER","LYFT","RIVN","LCID","NIO","XPEV","LI",
    # ETF
    "SPY","QQQ","SOXX","SMH","XLK","ARKK","ARKW","ARKG","SOXL","TQQQ",
]
# 중복 제거, 정렬
POPULAR_TICKERS = sorted(set(POPULAR_TICKERS))


def run():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[price_lookup] {len(POPULAR_TICKERS)}개 종목 가격 조회 시작...")

    try:
        data = yf.download(POPULAR_TICKERS, period="1d", progress=False, auto_adjust=True)
    except Exception as e:
        print(f"[price_lookup] 다운로드 실패: {e}", file=sys.stderr)
        return False

    prices = {}
    close = data.get("Close", data)
    for t in POPULAR_TICKERS:
        try:
            if hasattr(close, "columns") and t in close.columns:
                prices[t] = round(float(close[t].dropna().iloc[-1]), 2)
            elif hasattr(close, "iloc"):
                prices[t] = round(float(close.dropna().iloc[-1]), 2)
        except Exception:
            pass

    out = {
        "date": today,
        "count": len(prices),
        "prices": prices,
    }

    dest = Path(__file__).parent.parent.parent / "docs" / "data" / "price_lookup.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[price_lookup] {len(prices)}개 종목 저장 완료 → {dest}")
    return True


if __name__ == "__main__":
    run()
