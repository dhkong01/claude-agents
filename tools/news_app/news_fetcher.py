"""
지역별 RSS 피드 수집 공용 헬퍼
stdlib urllib + 정규식만 사용 (geo_risk_analyzer.py의 _fetch_rss 패턴 확장 —
제목/설명을 blob으로 합치지 않고 {title, summary, link, source} 구조로 유지)
"""
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def load_cache(name: str) -> dict | None:
    p = CACHE_DIR / name
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:
        return None


def cache_fresh(name: str, today: str) -> bool:
    d = load_cache(name)
    return bool(d and d.get("date") == today)


def save_cache(name: str, data: dict) -> None:
    (CACHE_DIR / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def today_kst() -> str:
    """한국시간(KST) 기준 오늘 날짜 (YYYY-MM-DD).

    뉴스 다이제스트는 매일 KST 아침에 생성/소비되므로, 거래일 라벨링에
    미 동부시간을 쓰는 stock_portfolio 파이프라인과 달리 KST를 기준으로 한다.
    """
    return datetime.now(KST).strftime("%Y-%m-%d")


REGION_FEEDS: dict[str, list[tuple[str, str]]] = {
    "US": [
        ("CNBC", "https://www.cnbc.com/id/10001147/device/rss/rss.html"),
        ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
        ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ],
    "KR": [
        ("한국경제", "https://www.hankyung.com/feed/economy"),
        ("매일경제", "https://www.mk.co.kr/rss/30100041/"),
    ],
    "JP": [
        ("Nikkei Asia", "https://asia.nikkei.com/rss/feed/nar"),
    ],
    "TW": [
        ("Google News", "https://news.google.com/rss/search?q=Taiwan+business+OR+TSMC+OR+semiconductor&hl=en-US&gl=US&ceid=US:en"),
    ],
    "CN": [
        ("SCMP Business", "https://www.scmp.com/rss/92/feed"),
    ],
    "EUROPE": [
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("Euronews Business", "https://www.euronews.com/rss?level=theme&name=business"),
        ("DW Business", "https://rss.dw.com/rdf/rss-en-bus"),
        ("Politico Europe", "https://www.politico.eu/feed/"),
    ],
}


def _fetch_one(source: str, url: str) -> list[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[news_fetcher] {source} 피드 접근 실패: {e}", file=sys.stderr)
        return []

    items: list[dict] = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", content, re.IGNORECASE | re.DOTALL):
        title_m = re.search(r"<title[^>]*>(.*?)</title>", block, re.IGNORECASE | re.DOTALL)
        desc_m = re.search(r"<description[^>]*>(.*?)</description>", block, re.IGNORECASE | re.DOTALL)
        link_m = re.search(r"<link[^>]*>(.*?)</link>", block, re.IGNORECASE | re.DOTALL)
        if not title_m:
            continue
        title = _clean(title_m.group(1))
        if not title:
            continue
        items.append({
            "title": title,
            "summary": _clean(desc_m.group(1))[:300] if desc_m else "",
            "link": _clean(link_m.group(1)) if link_m else "",
            "source": source,
        })
    return items


def _clean(text: str) -> str:
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&[a-z#0-9]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_region(region: str, limit: int = 40) -> list[dict]:
    """region 코드(US/KR/JP/TW/CN/EUROPE)에 등록된 피드를 모두 수집해 최대 limit건 반환."""
    feeds = REGION_FEEDS.get(region, [])
    items: list[dict] = []
    seen_titles: set[str] = set()
    for source, url in feeds:
        for item in _fetch_one(source, url):
            key = item["title"].lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            items.append(item)
    return items[:limit]
