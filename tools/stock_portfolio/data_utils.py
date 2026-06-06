import json
import pandas as pd
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def get_ndx100_tickers() -> list[str]:
    """NASDAQ-100 구성 종목 (Wikipedia 기준)"""
    cache = CACHE_DIR / "ndx100_tickers.json"
    try:
        import urllib.request, io
        req = urllib.request.Request(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            headers={"User-Agent": "Mozilla/5.0 (compatible; portfolio-bot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
        tables = pd.read_html(io.StringIO(html))
        for df in tables:
            ticker_col = next(
                (c for c in df.columns if str(c).lower() in ("ticker", "ticker symbol", "symbol")),
                None,
            )
            if ticker_col is None:
                continue
            tickers = (
                df[ticker_col].dropna()
                .str.replace(".", "-", regex=False)
                .tolist()
            )
            tickers = [t for t in tickers if isinstance(t, str) and 1 <= len(t) <= 6]
            if len(tickers) > 50:
                cache.write_text(json.dumps(tickers))
                return tickers
        raise ValueError("NDX100 Ticker 컬럼 없음")
    except Exception:
        if cache.exists():
            return json.loads(cache.read_text())
        return []


def get_universe_tickers() -> list[str]:
    """S&P 500 + NASDAQ-100 중복 제거 유니버스"""
    sp500 = get_sp500_tickers()
    ndx100 = get_ndx100_tickers()
    return list(dict.fromkeys(sp500 + ndx100))


def get_sp500_tickers() -> list[str]:
    cache = CACHE_DIR / "sp500_tickers.json"
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0 (compatible; portfolio-bot/1.0)"},
        )
        import io
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
        df = pd.read_html(io.StringIO(html))[0]
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        cache.write_text(json.dumps(tickers))
        return tickers
    except Exception:
        if cache.exists():
            return json.loads(cache.read_text())
        raise RuntimeError("S&P500 티커 로드 실패")


def batch_download(tickers: list[str], period: str = "1y", chunk: int = 50) -> pd.DataFrame:
    import yfinance as yf
    frames = []
    for i in range(0, len(tickers), chunk):
        try:
            data = yf.download(
                tickers[i : i + chunk],
                period=period,
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if "Close" in data.columns:
                frames.append(data["Close"])
        except Exception:
            continue
    return pd.concat(frames, axis=1) if frames else pd.DataFrame()
