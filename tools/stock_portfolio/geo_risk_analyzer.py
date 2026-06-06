"""
지정학 리스크 분석기
RSS 뉴스 스캔 → 리스크 점수(0-10) → 섹터 영향 매핑 → RISK_ON/OFF 판단
"""
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

HIGH_RISK_KEYWORDS = [
    "war", "military strike", "invasion", "nuclear", "missile attack",
    "sanctions", "military conflict", "troops deployed", "escalation",
    "coup", "crisis", "airstrike", "blockade", "mobilization",
]
MEDIUM_RISK_KEYWORDS = [
    "tension", "dispute", "tariff", "trade war", "protest", "ceasefire",
    "negotiations", "threat", "warning", "standoff", "sanction",
    "military exercise", "arms", "confrontation",
]
LOW_RISK_KEYWORDS = [
    "agreement", "deal", "peace talks", "summit", "cooperation",
    "de-escalation", "accord", "resolution", "withdrawal", "truce",
]

SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Energy":        ["oil", "gas", "opec", "russia", "ukraine", "iran", "saudi", "pipeline"],
    "Semiconductors":["taiwan", "china", "semiconductor", "chip", "tsmc", "huawei", "export ban"],
    "Defense":       ["military", "war", "nato", "pentagon", "defense", "weapon", "missile", "army"],
    "Consumer":      ["tariff", "trade war", "supply chain", "import ban", "export ban"],
    "Financials":    ["sanctions", "swift", "currency crisis", "dollar", "yuan", "debt ceiling"],
}

RSS_FEEDS = [
    "https://feeds.reuters.com/Reuters/worldNews",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
]


def _fetch_rss(url: str) -> list[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        titles = re.findall(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
        descs  = re.findall(r"<description[^>]*>(.*?)</description>", content, re.IGNORECASE | re.DOTALL)
        texts  = titles[:30] + descs[:30]
        return [re.sub(r"<[^>]+>|&[a-z#0-9]+;", " ", t).lower() for t in texts]
    except Exception:
        return []


def analyze_geo_risk() -> dict:
    texts: list[str] = []
    for feed in RSS_FEEDS:
        texts.extend(_fetch_rss(feed))

    if not texts:
        return _default_risk("RSS 피드 접근 불가")

    full_text = " ".join(texts)

    high_count = sum(1 for kw in HIGH_RISK_KEYWORDS   if kw in full_text)
    med_count  = sum(1 for kw in MEDIUM_RISK_KEYWORDS if kw in full_text)
    low_count  = sum(1 for kw in LOW_RISK_KEYWORDS    if kw in full_text)

    raw_score  = high_count * 3.0 + med_count * 1.5 - low_count * 0.5
    risk_score = round(min(10.0, max(0.0, raw_score)), 1)

    if risk_score >= 6:
        risk_level, market_bias = "HIGH",   "RISK_OFF"
    elif risk_score >= 3:
        risk_level, market_bias = "MEDIUM", "NEUTRAL"
    else:
        risk_level, market_bias = "LOW",    "RISK_ON"

    sector_impacts: dict[str, str] = {}
    for sector, keywords in SECTOR_KEYWORDS.items():
        cnt = sum(1 for kw in keywords if kw in full_text)
        if cnt >= 2:
            sector_impacts[sector] = "ELEVATED"
        elif cnt == 1:
            sector_impacts[sector] = "WATCH"

    risk_events: list[str] = []
    for text in texts[:30]:
        if any(kw in text for kw in HIGH_RISK_KEYWORDS[:6]):
            clean = text[:120].strip().title()
            if clean and clean not in risk_events:
                risk_events.append(clean)
        if len(risk_events) >= 3:
            break

    hedge = _calc_hedge(risk_score, sector_impacts)

    result = {
        "date":               datetime.now().strftime("%Y-%m-%d"),
        "risk_score":         risk_score,
        "risk_level":         risk_level,
        "market_bias":        market_bias,
        "high_risk_signals":  high_count,
        "medium_risk_signals":med_count,
        "sector_impacts":     sector_impacts,
        "top_risk_events":    risk_events,
        "recommendation":     _recommendation(risk_level, sector_impacts),
        "hedge":              hedge,
    }
    (CACHE_DIR / "geo_risk.json").write_text(
        json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return result


def _default_risk(reason: str = "") -> dict:
    hedge = _calc_hedge(3.0, {})
    result = {
        "date":               datetime.now().strftime("%Y-%m-%d"),
        "risk_score":         3.0,
        "risk_level":         "MEDIUM",
        "market_bias":        "NEUTRAL",
        "high_risk_signals":  0,
        "medium_risk_signals":0,
        "sector_impacts":     {},
        "top_risk_events":    [reason] if reason else [],
        "recommendation":     "Data unavailable - conservative approach recommended.",
        "hedge":              hedge,
    }
    (CACHE_DIR / "geo_risk.json").write_text(
        json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return result


def _recommendation(risk_level: str, sector_impacts: dict) -> str:
    elevated = [s for s, v in sector_impacts.items() if v == "ELEVATED"]
    if risk_level == "HIGH":
        sectors_str = f" ({', '.join(elevated)} 비중 축소)" if elevated else ""
        return f"고위험 국면{sectors_str}. 포지션 축소 및 현금 비중 확대 권장."
    if risk_level == "MEDIUM":
        return "중간 리스크. 분산 포트폴리오 유지. " + (
            f"{', '.join(elevated)} 섹터 모니터링." if elevated else "모니터링 강화."
        )
    return "저위험 국면 — 추세 추종 최적 환경. 공격적 포지션 가능."


# ── SQQQ 헤지 권고 (Orchestrator 신호) ───────────────────────

# risk_score → (long%, sqqq%, cash%, action)
_HEDGE_TABLE = [
    (3.0,  100,  0,   0,  "FULL_LONG"),        # LOW: 완전 추세 추종
    (5.0,   80,  5,  15,  "LIGHT_HEDGE"),       # LOW-MED: 소형 SQQQ 헤지
    (7.0,   60, 10,  30,  "MODERATE_HEDGE"),    # MEDIUM-HIGH: 중간 방어
    (8.5,   40, 15,  45,  "DEFENSIVE"),         # HIGH: 방어 포지션
    (10.1,  20, 20,  60,  "MAX_DEFENSIVE"),     # EXTREME: 최대 방어
]

def _calc_hedge(risk_score: float, sector_impacts: dict) -> dict:
    """
    지정학 리스크 점수 → Orchestrator에 전달할 포트폴리오 헤지 권고
    SQQQ(3× 역 NASDAQ) 비중 + 현금 비중 산출
    """
    long_pct = sqqq_pct = cash_pct = 0
    action = "FULL_LONG"
    for threshold, lp, sp, cp, act in _HEDGE_TABLE:
        if risk_score < threshold:
            long_pct, sqqq_pct, cash_pct, action = lp, sp, cp, act
            break

    elevated = [s for s, v in sector_impacts.items() if v == "ELEVATED"]

    # 반도체 섹터 ELEVATED 시 SQQQ +5% 추가 (NASDAQ 비중 크므로)
    if "Semiconductors" in elevated and sqqq_pct > 0:
        extra = 5
        sqqq_pct = min(sqqq_pct + extra, 30)
        long_pct = max(long_pct - extra, 10)

    per_stock = round(long_pct / 5, 1)   # 5종목 동일비중 기준

    return {
        "long_pct":        int(long_pct),
        "sqqq_pct":        int(sqqq_pct),
        "cash_pct":        int(cash_pct),
        "per_stock_pct":   per_stock,
        "action":          action,
        "sqqq_active":     sqqq_pct > 0,
        "elevated_sectors":elevated,
        "reasoning":       _hedge_reason(action, risk_score, sqqq_pct, cash_pct, elevated),
    }


def _hedge_reason(action: str, score: float, sqqq: int, cash: int, elevated: list) -> str:
    base = {
        "FULL_LONG":      f"Risk {score:.1f} — 추세 추종 100% 롱 유지. SQQQ 불필요.",
        "LIGHT_HEDGE":    f"Risk {score:.1f} — SQQQ {sqqq}% 소형 헤지, 현금 {cash}% 확보.",
        "MODERATE_HEDGE": f"Risk {score:.1f} — SQQQ {sqqq}% 중형 헤지, 현금 {cash}% 방어.",
        "DEFENSIVE":      f"Risk {score:.1f} — SQQQ {sqqq}% 방어 포지션, 현금 {cash}% 유지.",
        "MAX_DEFENSIVE":  f"Risk {score:.1f} — 극단 방어. SQQQ {sqqq}% + 현금 {cash}%. 롱 최소화.",
    }.get(action, "")
    if elevated:
        base += f" [{', '.join(elevated)} ELEVATED]"
    return base


if __name__ == "__main__":
    result = analyze_geo_risk()
    print(json.dumps(result, ensure_ascii=False, indent=2))
