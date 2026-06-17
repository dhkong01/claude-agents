"""
분기 섹터 데이터 → docs/data/sector_latest.json 내보내기
PWA 섹터 탭에서 사용
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR  = Path(__file__).parent
CACHE_DIR = BASE_DIR / "cache"
REPO_ROOT = BASE_DIR.parent.parent
DOCS_DATA = REPO_ROOT / "docs" / "data"
DOCS_DATA.mkdir(parents=True, exist_ok=True)

SECTOR_ETFS = {
    "Technology":       "XLK",
    "Financials":       "XLF",
    "Energy":           "XLE",
    "Healthcare":       "XLV",
    "Industrials":      "XLI",
    "Communication":    "XLC",
    "Consumer Disc.":   "XLY",
    "Real Estate":      "XLRE",
    "Utilities":        "XLU",
    "Materials":        "XLB",
    "Consumer Staples": "XLP",
}


def quarter_start(d: date) -> date:
    m = ((d.month - 1) // 3) * 3 + 1
    return date(d.year, m, 1)


def quarter_label(d: date) -> str:
    return f"{d.year}-Q{(d.month-1)//3+1}"


def qtd_return(hist, q_start: date):
    if hist is None or hist.empty:
        return None
    try:
        idx  = hist.index.normalize()
        base = hist[idx >= str(q_start)]
        if base.empty:
            return None
        p0 = float(base["Close"].iloc[0])
        p1 = float(base["Close"].iloc[-1])
        return round((p1 / p0 - 1) * 100, 2) if p0 else None
    except Exception:
        return None


def get_macro_from_cache() -> dict:
    p = CACHE_DIR / "macro.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def get_geo_risk_from_cache() -> dict:
    p = CACHE_DIR / "geo_risk.json"
    try:
        if not p.exists():
            return {}
        d = json.loads(p.read_text(encoding="utf-8"))
        return {
            "risk_score":  d.get("risk_score", 0),
            "risk_level":  d.get("risk_level", ""),
            "market_bias": d.get("market_bias", ""),
        }
    except Exception:
        return {}


def get_canslim_by_sector() -> dict:
    p = CACHE_DIR / "canslim_top10.json"
    result: dict[str, list] = {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        for s in data.get("top10", []):
            sec = s.get("sector", "Other")
            result.setdefault(sec, []).append({
                "ticker":  s["ticker"],
                "rs":      round(s.get("rs_rating", 0), 1),
                "canslim": s.get("canslim_score", 0),
                "price":   s.get("price", 0),
            })
    except Exception:
        pass
    return result


def export_sector(today: date) -> bool:
    import yfinance as yf

    q_start = quarter_start(today)
    q_label = quarter_label(today)

    print(f"[sector] 분기: {q_label} (시작: {q_start})")

    # ── ETF 수익률 (개별 다운로드 — MultiIndex 파싱 오류 방지)
    import time
    sectors = []
    for sector, etf in SECTOR_ETFS.items():
        qtd = None
        w1  = None
        try:
            raw = yf.download(
                etf,
                start=str(q_start - timedelta(days=5)),
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if raw is not None and not raw.empty:
                # yfinance 1.4+: 단일 티커도 MultiIndex (Close, TICKER)
                closes = raw["Close"][etf] if etf in raw["Close"].columns else raw["Close"].iloc[:, 0]
                closes = closes.dropna()
                if not closes.empty:
                    # QTD
                    idx = closes.index.normalize()
                    base = closes[idx >= str(q_start)]
                    if not base.empty:
                        qtd = round((float(base.iloc[-1]) / float(base.iloc[0]) - 1) * 100, 2)
                    # 1주
                    h1w = closes.tail(5)
                    if len(h1w) >= 2:
                        w1 = round((float(h1w.iloc[-1]) / float(h1w.iloc[0]) - 1) * 100, 2)
        except Exception as e:
            print(f"[sector] {etf} 다운로드 실패: {e}", file=sys.stderr)
        sectors.append({
            "sector": sector,
            "etf":    etf,
            "qtd":    qtd,
            "week1":  w1,
        })
        time.sleep(0.3)  # rate-limit 방지

    # QTD 기준 정렬
    sectors.sort(key=lambda x: x["qtd"] or -999, reverse=True)
    for i, s in enumerate(sectors):
        s["rank"] = i + 1
        # 상태 레이블
        v = s["qtd"] or 0
        s["status"] = "과열" if v > 10 else ("강세" if v > 3 else ("중립" if v >= 0 else "약세"))

    # ── CANSLIM 섹터별 종목
    us_by_sector = get_canslim_by_sector()

    # ── 매크로 + 지정학 리스크
    macro    = get_macro_from_cache()
    geo_risk = get_geo_risk_from_cache()

    out = {
        "date":         today.isoformat(),
        "quarter":      q_label,
        "q_start":      str(q_start),
        "sectors":      sectors,
        "us_by_sector": us_by_sector,
        "macro": {
            "phase":       macro.get("phase", ""),
            "vix":         macro.get("signals", {}).get("vix_level", ""),
            "yield10y":    macro.get("signals", {}).get("yield10y", ""),
            "rec_sectors": macro.get("recommended_sectors", []),
        },
        "geo_risk": geo_risk,
    }

    dest = DOCS_DATA / "sector_latest.json"
    # NaN/Infinity는 표준 JSON이 아니므로 null로 변환 (브라우저 파싱 오류 방지)
    raw = json.dumps(out, ensure_ascii=False, indent=2)
    raw = raw.replace(': NaN,', ': null,').replace(': NaN\n', ': null\n')
    dest.write_text(raw, encoding="utf-8")
    print(f"[sector] 저장 완료 → {dest}")
    return True


if __name__ == "__main__":
    export_sector(date.today())
