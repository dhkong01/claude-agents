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
    }
    (CACHE_DIR / "geo_risk.json").write_text(
        json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return result


def _default_risk(reason: str = "") -> dict:
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


if __name__ == "__main__":
    result = analyze_geo_risk()
    print(json.dumps(result, ensure_ascii=False, indent=2))
