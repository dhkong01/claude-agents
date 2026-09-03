"""
역배열→정배열 전환 + VCP 돌파 스크리너
────────────────────────────────────────────────────────────
로그 스케일 112일/224일/448일 이동평균선을 기준으로
  1) 역배열(단기<중기<장기)이었다가 단기선이 반등하며
     정배열로 바뀔 준비가 되는 종목 ("바닥반전" / "전환중")
  2) 224일선·448일선을 VCP(변동성 수축) 패턴 이후 돌파했거나
     돌파 준비가 된 종목
을 함께 만족하는 "저평가 반전주"를 선별한다.

섹터 로테이션(sector_latest.json)이 유리한 방향인 종목에 가점을 준다.
"""
import json
import sys
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from data_utils import CACHE_DIR, market_today, YF_SESSION
from minervini_vcp import detect_vcp

REPO_ROOT = Path(__file__).parent.parent.parent
DOCS_DATA = REPO_ROOT / "docs" / "data"

MA_SHORT, MA_MID, MA_LONG = 112, 224, 448
SLOPE_LOOKBACK  = 20   # 기울기(모멘텀 전환) 판정 기간
CROSS_LOOKBACK  = 10   # 224/448 돌파 판정 기간(거래일)
NEAR_PCT        = 0.06 # "돌파 준비" 판정 임계치(6% 이내)
MIN_HISTORY     = MA_LONG + SLOPE_LOOKBACK + 5

# yfinance GICS 섹터명 → sector_latest.json 섹터명 매핑
YF_SECTOR_MAP = {
    "Technology":            "Technology",
    "Healthcare":             "Healthcare",
    "Financial Services":     "Financials",
    "Financial":              "Financials",
    "Basic Materials":        "Materials",
    "Communication Services": "Communication",
    "Consumer Defensive":     "Consumer Staples",
    "Real Estate":            "Real Estate",
    "Consumer Cyclical":      "Consumer Disc.",
    "Industrials":            "Industrials",
    "Energy":                 "Energy",
    "Utilities":              "Utilities",
}


# ── 로그 스케일 MA 스테이지 판정 ─────────────────────────────

def _log_ma_stage(close: pd.Series) -> dict:
    """112/224/448일 로그 이동평균선 배열 상태와 전환 신호를 계산."""
    if len(close) < MIN_HISTORY:
        return {"eligible": False}

    logp = np.log(close.values.astype(float))
    s = pd.Series(logp)
    ma112 = s.rolling(MA_SHORT).mean()
    ma224 = s.rolling(MA_MID).mean()
    ma448 = s.rolling(MA_LONG).mean()

    if pd.isna(ma448.iloc[-1]):
        return {"eligible": False}

    c112, c224, c448 = float(ma112.iloc[-1]), float(ma224.iloc[-1]), float(ma448.iloc[-1])
    price = float(close.iloc[-1])

    def _slope(ma: pd.Series, n: int = SLOPE_LOOKBACK) -> float:
        if len(ma) <= n or pd.isna(ma.iloc[-1 - n]):
            return 0.0
        return float(ma.iloc[-1] - ma.iloc[-1 - n])

    slope112, slope224, slope448 = _slope(ma112), _slope(ma224), _slope(ma448)

    p112, p224, p448 = float(np.exp(c112)), float(np.exp(c224)), float(np.exp(c448))

    was_reverse = c112 < c224 < c448                        # 완전 역배열
    flipping    = (c112 > c224) and (c224 <= c448)           # 단기선이 중기선 돌파, 장기선은 아직
    early_base  = was_reverse and slope112 > 0                # 역배열이지만 단기선 반등 시작
    bullish     = (c112 > c224 > c448) and slope112 > 0 and slope224 > 0

    if flipping and slope112 > 0:
        stage = "전환중"     # 단기선이 중기선을 돌파, 정배열 전환 진행 중
    elif early_base:
        stage = "바닥반전"   # 역배열이지만 단기선이 바닥 찍고 반등 시작
    elif bullish:
        stage = "정배열"
    elif was_reverse:
        stage = "역배열"
    else:
        stage = "혼조"

    return {
        "eligible": True, "stage": stage, "price": round(price, 2),
        "ma112": round(p112, 2), "ma224": round(p224, 2), "ma448": round(p448, 2),
        "slope112": round(slope112, 4), "slope224": round(slope224, 4), "slope448": round(slope448, 4),
        "price_above_ma112": price > p112,
        "price_above_ma224": price > p224,
        "price_above_ma448": price > p448,
    }


# ── 224/448일선 돌파·돌파준비 판정 ───────────────────────────

def _cross_signal(close: pd.Series, ma_period: int, lookback: int = CROSS_LOOKBACK,
                   near_pct: float = NEAR_PCT) -> dict:
    logp = np.log(close.values.astype(float))
    ma_log = pd.Series(logp).rolling(ma_period).mean().values
    price = close.values.astype(float)
    n = len(price)
    if n < ma_period + lookback + 1 or np.isnan(ma_log[-1]):
        return {"status": "n/a", "dist_pct": None}

    ma_price = np.exp(ma_log)
    cur_above = price[-1] > ma_price[-1]
    idx_prev = max(ma_period, n - 1 - lookback)
    was_below = (not np.isnan(ma_price[idx_prev])) and price[idx_prev] < ma_price[idx_prev]
    dist_pct = float((price[-1] - ma_price[-1]) / ma_price[-1] * 100)

    if cur_above and was_below:
        status = "돌파"
    elif (not cur_above) and (-near_pct * 100) <= dist_pct < 0:
        status = "돌파준비"
    elif cur_above:
        status = "위"
    else:
        status = "아래"
    return {"status": status, "dist_pct": round(dist_pct, 1)}


# ── 섹터 로테이션 가점 ────────────────────────────────────────

def _load_sector_map() -> dict:
    src = DOCS_DATA / "sector_latest.json"
    if not src.exists():
        return {}
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
        return {s["sector"]: s for s in data.get("sectors", [])}
    except Exception:
        return {}


def _sector_bonus(ticker: str, sector_map: dict) -> dict:
    """개별 종목의 yfinance 섹터를 조회해 섹터 로테이션 랭크 기반 가점 산출.
    (숏리스트 통과 종목에 한해서만 호출 — 전체 유니버스 호출 시 너무 느림)"""
    try:
        info = yf.Ticker(ticker, session=YF_SESSION).get_info()
        yf_sector = info.get("sector")
    except Exception:
        yf_sector = None

    mapped = YF_SECTOR_MAP.get(yf_sector or "", None)
    row = sector_map.get(mapped) if mapped else None
    if not row:
        return {"sector": yf_sector, "sector_rank": None, "sector_qtd": None, "sector_bonus": 0}

    rank = row.get("rank", 99)
    bonus = 15 if rank <= 3 else 8 if rank <= 6 else 0
    return {
        "sector": mapped, "sector_rank": rank,
        "sector_qtd": row.get("qtd"), "sector_bonus": bonus,
    }


# ── 실적 가속(매출·영업이익 지속증가 + 증가폭 확대) 가점 ──────

def _growth_series(vals: list[float]) -> list[float | None]:
    """연도별 값 리스트(오래된→최신) → YoY 성장률 리스트."""
    g: list[float | None] = []
    for i in range(1, len(vals)):
        prev = vals[i - 1]
        g.append(None if prev == 0 else (vals[i] - prev) / abs(prev))
    return g


def _accel_flags(g: list[float | None]) -> tuple[bool, bool]:
    """(지속 증가 여부, 최근 성장률이 직전보다 더 커졌는지=가속 여부)"""
    gg = [x for x in g if x is not None]
    if len(gg) < 2:
        return False, False
    growing = all(x > 0 for x in gg)
    accel   = gg[-1] > gg[-2]
    return growing, accel


def _fundamentals_bonus(ticker: str) -> dict:
    """연간 매출·영업이익이 지속적으로 증가하면서 증가폭까지 확대(가속)되는
    종목에 가점을 부여. yfinance 연간 재무제표(최근 4개년) 기반.
    - 매출·영업이익 모두 지속증가 + 가속: +15 (fund_accel=True, "실적가속")
    - 둘 중 하나만 지속증가+가속: +8
    - 그 외: 0
    """
    try:
        tk  = yf.Ticker(ticker, session=YF_SESSION)
        fin = tk.financials  # 연간 손익계산서, 컬럼 최신순
        if fin is None or fin.empty:
            return {"fund_bonus": 0, "fund_accel": False}

        def _row(names: list[str]):
            for n in names:
                if n in fin.index:
                    return fin.loc[n]
            return None

        rev_row = _row(["Total Revenue", "TotalRevenue"])
        opi_row = _row(["Operating Income", "OperatingIncome"])
        if rev_row is None or opi_row is None:
            return {"fund_bonus": 0, "fund_accel": False}

        rev = rev_row.dropna().iloc[:4][::-1].values.astype(float)  # 오래된→최신
        opi = opi_row.dropna().iloc[:4][::-1].values.astype(float)
        if len(rev) < 3 or len(opi) < 3:
            return {"fund_bonus": 0, "fund_accel": False}

        rg = _growth_series(list(rev))
        og = _growth_series(list(opi))
        rev_growing, rev_accel = _accel_flags(rg)
        opi_growing, opi_accel = _accel_flags(og)

        both = rev_growing and rev_accel and opi_growing and opi_accel
        one  = (rev_growing and rev_accel) or (opi_growing and opi_accel)
        bonus = 15 if both else (8 if one else 0)

        rg_valid = [x for x in rg if x is not None]
        og_valid = [x for x in og if x is not None]
        return {
            "fund_bonus":              bonus,
            "fund_accel":              bool(both),
            "rev_growing":             bool(rev_growing),
            "opinc_growing":           bool(opi_growing),
            "rev_growth_recent_pct":   round(rg_valid[-1] * 100, 1) if rg_valid else None,
            "opinc_growth_recent_pct": round(og_valid[-1] * 100, 1) if og_valid else None,
        }
    except Exception:
        return {"fund_bonus": 0, "fund_accel": False}


# ── 메인 스크리닝 ─────────────────────────────────────────────

def screen_reversal(top_n: int = 20) -> list[dict]:
    from data_utils import get_ndx100_tickers, get_sp500_tickers

    tickers = list(dict.fromkeys(get_ndx100_tickers() + get_sp500_tickers()))
    if not tickers:
        print("[reversal] 유니버스 로드 실패", file=sys.stderr)
        return []

    print(f"[reversal] 유니버스 {len(tickers)}종목 다운로드 중 (2y)...")
    candidates: list[dict] = []

    for i in range(0, len(tickers), 50):
        batch = tickers[i:i + 50]
        try:
            raw = yf.download(batch, period="2y", auto_adjust=True,
                               progress=False, threads=False, session=YF_SESSION)
            if raw.empty:
                continue
        except Exception:
            continue

        for ticker in batch:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    close  = raw["Close"][ticker].dropna()
                    volume = raw["Volume"][ticker].dropna()
                else:
                    close  = raw["Close"].dropna()
                    volume = raw["Volume"].dropna()

                if len(close) < MIN_HISTORY:
                    continue

                stage_info = _log_ma_stage(close)
                if not stage_info.get("eligible"):
                    continue
                if stage_info["stage"] not in ("전환중", "바닥반전"):
                    continue   # 핵심 조건: 역배열→정배열 전환 준비 단계만 채택

                cross224 = _cross_signal(close, MA_MID)
                cross448 = _cross_signal(close, MA_LONG)
                interesting_cross = (
                    cross224["status"] in ("돌파", "돌파준비") or
                    cross448["status"] in ("돌파", "돌파준비")
                )

                vcp = detect_vcp(close, volume)
                if not interesting_cross and not vcp["has_vcp"]:
                    continue   # 돌파(준비) 신호도 VCP도 없으면 제외

                reversal_score = 40 if stage_info["stage"] == "전환중" else 25
                breakout_score = (
                    (15 if cross224["status"] == "돌파" else 10 if cross224["status"] == "돌파준비" else 0) +
                    (15 if cross448["status"] == "돌파" else 10 if cross448["status"] == "돌파준비" else 0)
                )
                vcp_score = min(20, int(vcp["score"] * 0.45))
                total = reversal_score + breakout_score + vcp_score

                candidates.append({
                    "ticker": ticker,
                    "stage": stage_info["stage"],
                    "current_price": stage_info["price"],
                    "ma112": stage_info["ma112"], "ma224": stage_info["ma224"], "ma448": stage_info["ma448"],
                    "slope112": stage_info["slope112"], "slope224": stage_info["slope224"],
                    "cross224_status": cross224["status"], "cross224_dist_pct": cross224["dist_pct"],
                    "cross448_status": cross448["status"], "cross448_dist_pct": cross448["dist_pct"],
                    "has_vcp": bool(vcp["has_vcp"]), "vcp_pivot": vcp.get("pivot"),
                    "vcp_contractions": vcp.get("contractions", 0),
                    "reversal_score": reversal_score, "breakout_score": breakout_score,
                    "vcp_score": vcp_score, "total_score": total,
                })
            except Exception:
                continue

        if (i // 50 + 1) % 4 == 0:
            print(f"  진행: {min(i + 50, len(tickers))}/{len(tickers)}  후보:{len(candidates)}")

    print(f"[reversal] 1차 후보 {len(candidates)}종목 - 섹터 로테이션/실적가속 가점 계산 중...")
    sector_map = _load_sector_map()
    for c in candidates:
        c.update(_sector_bonus(c["ticker"], sector_map))
        c["total_score"] += c.get("sector_bonus", 0)
        c.update(_fundamentals_bonus(c["ticker"]))
        c["total_score"] += c.get("fund_bonus", 0)

    candidates.sort(key=lambda x: x["total_score"], reverse=True)
    top = candidates[:top_n]

    out = {
        "date": market_today(),
        "total_screened": len(tickers),
        "candidate_count": len(candidates),
        "stocks": top,
    }
    (CACHE_DIR / "reversal_top20.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[reversal] 완료: 후보 {len(candidates)}개 중 TOP{len(top)} 저장")
    return top


if __name__ == "__main__":
    stocks = screen_reversal()
    for s in stocks[:10]:
        print(f"{s['ticker']:6s} {s['stage']:5s}  Score:{s['total_score']:3d}"
              f"  224:{s['cross224_status']}  448:{s['cross448_status']}  VCP:{s['has_vcp']}")
