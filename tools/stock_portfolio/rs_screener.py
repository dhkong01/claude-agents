"""
IBD-style Relative Strength (RS) screener.
RS Rating = percentile rank of weighted 3/6/9/12M returns.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from data_utils import CACHE_DIR, batch_download, get_ndx100_tickers


def calc_rs_ratings(price_df: pd.DataFrame) -> pd.Series:
    def _ret(df: pd.DataFrame, months: int) -> pd.Series:
        n = min(int(months * 21), len(df) - 1)
        return (df.iloc[-1] / df.iloc[-n] - 1).clip(-1, 10)

    score = (
        0.40 * _ret(price_df, 3)
        + 0.20 * _ret(price_df, 6)
        + 0.20 * _ret(price_df, 9)
        + 0.20 * _ret(price_df, 12)
    )
    return (score.rank(pct=True) * 99).round(1)


def screen_rs90(min_rating: float = 90.0) -> list[dict]:
    # NDX 100 기준 유니버스 (S&P 500 대신 나스닥 100 사용)
    tickers = get_ndx100_tickers()

    # 유저 포트폴리오 종목도 포함 (NDX100 외 종목 RS 계산)
    my_port = Path(__file__).parent / "my_portfolio.json"
    user_tickers: list[str] = []
    if my_port.exists():
        user_tickers = [h["ticker"] for h in
                        json.loads(my_port.read_text(encoding="utf-8")).get("holdings", [])]
    all_tickers = list(dict.fromkeys(tickers + user_tickers))  # 순서 유지 dedupe

    prices = batch_download(all_tickers, period="1y")
    prices = prices.dropna(axis=1, thresh=int(len(prices) * 0.8))

    ratings = calc_rs_ratings(prices)

    # NDX100 전체 RS 순위 저장 (export_rs가 top30 추출용으로 사용)
    all_sorted = ratings.sort_values(ascending=False)
    all_stocks = [{"ticker": str(t), "rs_rating": float(r)} for t, r in all_sorted.items()]

    # RS≥min_rating 필터 (CANSLIM 입력용)
    rs90 = ratings[ratings >= min_rating].sort_values(ascending=False)

    # 유저 보유 종목 RS 별도 저장 (RS<90도 포함)
    if user_tickers:
        user_rs = {t: round(float(ratings[t]), 1) for t in user_tickers if t in ratings.index}
        (CACHE_DIR / "user_portfolio_rs.json").write_text(
            json.dumps({"date": datetime.now().strftime("%Y-%m-%d"), "ratings": user_rs}, indent=2)
        )

    result = [{"ticker": str(t), "rs_rating": float(r)} for t, r in rs90.items()]
    out = {
        "date":      datetime.now().strftime("%Y-%m-%d"),
        "universe":  "NDX100",
        "rs90_count": len(result),
        "stocks":    all_stocks,   # NDX100 전체 (export_rs top30 표시용)
    }
    (CACHE_DIR / "rs90.json").write_text(json.dumps(out, indent=2))
    return result


if __name__ == "__main__":
    stocks = screen_rs90()
    print(json.dumps({"rs90_count": len(stocks), "top10": stocks[:10]}, indent=2))
