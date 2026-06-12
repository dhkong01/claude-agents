"""
PWA용 JSON 데이터 내보내기
trend_result, vcp, canslim, portfolio → docs/data/*.json
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

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


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[export] PWA 데이터 내보내기 시작 ({today})")
    export_trend(today)
    export_vcp()
    export_canslim()
    export_portfolio(today)
    print("[export] 완료")
