"""
PWA용 JSON 데이터 내보내기
trend_result, vcp, canslim, portfolio → docs/data/*.json
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from data_utils import market_today

BASE_DIR  = Path(__file__).parent
CACHE_DIR = BASE_DIR / "cache"
REPO_ROOT = BASE_DIR.parent.parent
DOCS_DATA = REPO_ROOT / "docs" / "data"
DOCS_DATA.mkdir(parents=True, exist_ok=True)


def _read(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except Exception:
        return None


def export_trend(today: str) -> bool:
    src = CACHE_DIR / f"trend_result_{today}.json"
    if not src.exists():
        # 가장 최근 결과 파일 사용
        files = sorted(CACHE_DIR.glob("trend_result_*.json"), reverse=True)
        if not files:
            print("[export] trend_result 파일 없음", file=sys.stderr)
            return False
        src = files[0]
        print(f"[export] 최신 결과 사용: {src.name}")

    data = _read(src)
    if not data:
        return False

    out = DOCS_DATA / "trend_latest.json"
    # 기존 파일이 더 최신 날짜면 덮어쓰지 않음 (로컬 수동 실행 시 퇴행 방지)
    existing = _read(out)
    if existing and existing.get("date", "") > data.get("date", ""):
        print(f"[export] trend_latest.json 유지 (기존={existing['date']} > 캐시={data.get('date')})")
        return True
    # 새 데이터가 비어있는데 기존 데이터에 내용이 있으면 덮어쓰지 않음 (다운로드 실패 방지)
    new_rs90 = data.get("rs90_count", 0)
    if new_rs90 == 0 and existing and existing.get("rs90_count", 0) > 0:
        print(f"[export] trend_latest.json 유지 (새 데이터 rs90=0, 기존 rs90={existing['rs90_count']})")
        return True

    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] trend_latest.json → {out}")
    return True


def export_vcp() -> bool:
    src  = CACHE_DIR / "vcp_top20.json"
    data = _read(src)
    if not data:
        print("[export] vcp_top20.json 없음", file=sys.stderr)
        return False
    out = DOCS_DATA / "vcp_top20.json"
    existing = _read(out)
    # 새 데이터가 비어있는데 기존 데이터가 있으면 덮어쓰지 않음
    if not data.get("stocks") and existing and existing.get("stocks"):
        print(f"[export] vcp_top20.json 유지 (새 데이터 빈값, 기존 {len(existing['stocks'])}종목)")
        return True
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] vcp_top20.json → {out}")
    return True


def export_canslim() -> bool:
    src  = CACHE_DIR / "canslim_top10.json"
    data = _read(src)
    if not data:
        print("[export] canslim_top10.json 없음", file=sys.stderr)
        return False
    out = DOCS_DATA / "canslim_top10.json"
    existing = _read(out)
    # 빈 데이터 보호: top10이 비어있는데 기존에 데이터 있으면 유지
    if not data.get("top10") and existing and existing.get("top10"):
        print(f"[export] canslim_top10.json 유지 (새 데이터 빈값, 기존 {len(existing['top10'])}종목)")
        return True
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] canslim_top10.json → {out}")
    return True


def export_portfolio(today: str) -> bool:
    """
    포트폴리오 현재 가격 조회 후 JSON 생성
    PORTFOLIO_JSON 환경변수 또는 my_portfolio.json 사용
    """
    import urllib.request

    # 포트폴리오 로드
    raw_env = os.environ.get("PORTFOLIO_JSON", "")
    if raw_env:
        try:
            pf_raw = json.loads(raw_env)
        except Exception:
            pf_raw = {}
    else:
        pf_file = BASE_DIR / "my_portfolio.json"
        pf_raw  = _read(pf_file) or {}

    holdings_raw = pf_raw.get("holdings", [])
    total_cost   = pf_raw.get("total_cost", 0)
    next_rb      = pf_raw.get("next_rebalance", "")

    if not holdings_raw:
        print("[export] 포트폴리오 데이터 없음", file=sys.stderr)
        return False

    # yfinance로 현재가 조회
    try:
        import yfinance as yf
        tickers = [h.get("ticker") or h.get("t") for h in holdings_raw]
        prices  = {}
        data    = yf.download(tickers, period="1d", progress=False, auto_adjust=True)
        if "Close" in data:
            for t in tickers:
                try:
                    prices[t] = float(data["Close"][t].dropna().iloc[-1])
                except Exception:
                    prices[t] = 0.0
        else:
            for t in tickers:
                try:
                    prices[t] = float(data["Close"].dropna().iloc[-1])
                except Exception:
                    prices[t] = 0.0
    except Exception as e:
        print(f"[export] 가격 조회 실패: {e}", file=sys.stderr)
        prices = {}

    holdings_out = []
    for h in holdings_raw:
        ticker = h.get("ticker") or h.get("t", "?")
        shares = h.get("shares") or h.get("sh", 0)
        ac     = h.get("avg_cost") or h.get("ac", 0)
        price  = prices.get(ticker, 0)
        value  = price * shares
        cost   = ac * shares
        holdings_out.append({
            "ticker": ticker,
            "shares": shares,
            "avg_cost": round(ac, 4),
            "price":   round(price, 2),
            "value":   round(value, 2),
            "cost":    round(cost, 2),
        })

    # total_cost 가 0이면 개별 cost 합산으로 계산
    if not total_cost:
        total_cost = round(sum(h["cost"] for h in holdings_out), 2)

    # next_rebalance 기본값
    if not next_rb:
        next_rb = "2026-08-21"

    out_data = {
        "date":           today,
        "total_cost":     total_cost,
        "next_rebalance": next_rb,
        "holdings":       holdings_out,
    }
    out = DOCS_DATA / "portfolio_latest.json"
    out.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] portfolio_latest.json → {out}")
    return True


def export_rs(top_n: int = 30) -> bool:
    """RS 순위 데이터 내보내기: cache/rs90.json → docs/data/rs_top30.json"""
    src = CACHE_DIR / "rs90.json"
    data = _read(src)
    if not data:
        print("[export] rs90.json 없음", file=sys.stderr)
        return False

    stocks = data.get("stocks", [])
    out = DOCS_DATA / "rs_top30.json"
    existing = _read(out)
    # 빈 데이터 보호: rs90=0인데 기존 데이터 있으면 유지
    if data.get("rs90_count", 0) == 0 and existing and existing.get("rs90_count", 0) > 0:
        print(f"[export] rs_top30.json 유지 (새 데이터 rs90=0, 기존 rs90={existing['rs90_count']})")
        return True

    # 이미 rs_rating 내림차순 정렬되어 있음. top_n만 내보냄
    out_data = {
        "date":      data.get("date", ""),
        "rs90_count": data.get("rs90_count", len(stocks)),
        "stocks":    stocks[:top_n],
    }

    # 유저 포트폴리오 RS 보완 (RS<90 종목도 포함)
    user_rs_file = CACHE_DIR / "user_portfolio_rs.json"
    if user_rs_file.exists():
        user_rs = _read(user_rs_file) or {}
        out_data["portfolio_rs"] = user_rs.get("ratings", {})

    out.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] rs_top30.json → {out} ({len(out_data['stocks'])}종목)")
    return True


if __name__ == "__main__":
    today = market_today()
    print(f"[export] PWA 데이터 내보내기 시작 ({today})")
    export_trend(today)
    export_vcp()
    export_canslim()
    export_portfolio(today)
    export_rs()
    print("[export] 완료")
