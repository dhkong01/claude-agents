import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

US_EASTERN = ZoneInfo("America/New_York")


def get_yf_session():
    """curl_cffi 세션으로 브라우저(Chrome)를 위장해 Yahoo Finance에 요청.

    GitHub Actions 등 클라우드 CI의 공유 IP는 Yahoo Finance가 빈번히
    429(Too Many Requests)로 차단/레이트리밋한다. yfinance 기본 세션으로는
    이 경우 요청이 조용히 실패(빈 DataFrame)하고, 각 모듈의 "기존 캐시 유지"
    보호 로직이 발동해 며칠씩 데이터가 갱신되지 않는 현상으로 이어졌다.
    curl_cffi로 실제 브라우저 TLS/HTTP 핑거프린트를 재현하면 이 차단을 우회한다.
    curl_cffi 미설치 환경에서는 None을 반환해 yfinance 기본 동작으로 폴백한다.
    """
    try:
        from curl_cffi import requests as cc_requests
        return cc_requests.Session(impersonate="chrome")
    except Exception:
        return None


YF_SESSION = get_yf_session()


def market_today() -> str:
    """미국 동부시간(America/New_York) 기준 오늘 날짜 (YYYY-MM-DD).

    GitHub Actions 스케줄 실행이 지연되어 UTC 자정을 넘기면
    naive datetime.now()(UTC)는 트레이딩 데이 라벨이 하루 앞당겨져
    같은 날짜로 두 거래일 데이터가 충돌(덮어쓰기)하는 문제가 있었다.
    항상 미 동부시간 기준으로 계산해 이 경합을 방지한다.
    """
    return datetime.now(US_EASTERN).strftime("%Y-%m-%d")


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
                threads=False,  # threads=True → GitHub Actions rate-limit 방지
                session=YF_SESSION,
            )
            # yfinance MultiIndex vs single-ticker 대응
            if hasattr(data.columns, "levels"):
                # MultiIndex: (field, ticker)
                if "Close" in data.columns.get_level_values(0):
                    frames.append(data["Close"])
            elif "Close" in data.columns:
                frames.append(data[["Close"]])
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, axis=1)
    # yfinance는 미국 장 마감 전(당일 데이터 미확정 시) 오늘 날짜를 전종목 NaN인
    # "자리표시자" 행으로 추가하는 경우가 있다. 이 행이 남아있으면 iloc[-1]을
    # "현재가"로 쓰는 모든 호출부(RS 계산 등)가 전부 NaN이 되어 스크리닝이
    # 조용히 실패한다 — 완전히 빈 행을 제거해 항상 마지막 유효 거래일이 남게 한다.
    return result.dropna(axis=0, how="all")
