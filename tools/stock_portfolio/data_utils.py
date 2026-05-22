import json
import pandas as pd
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


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
