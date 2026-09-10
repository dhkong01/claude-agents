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
        # Bloomberg·Barron's는 공식 RSS를 대부분 폐기해서 Google News 사이트 필터로 수집
        ("Bloomberg", "https://news.google.com/rss/search?q=when:2d%20site:bloomberg.com&hl=en-US&gl=US&ceid=US:en"),
        ("Barron's", "https://news.google.com/rss/search?q=when:2d%20site:barrons.com&hl=en-US&gl=US&ceid=US:en"),
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

    is_gnews = "news.google.com" in url
    items: list[dict] = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", content, re.IGNORECASE | re.DOTALL):
        title_m = re.search(r"<title[^>]*>(.*?)</title>", block, re.IGNORECASE | re.DOTALL)
        desc_m = re.search(r"<description[^>]*>(.*?)</description>", block, re.IGNORECASE | re.DOTALL)
        link_m = re.search(r"<link[^>]*>(.*?)</link>", block, re.IGNORECASE | re.DOTALL)
        if not title_m:
            continue
        title = _clean(title_m.group(1))
        if is_gnews:
            # Google News item은 <source>매체명</source>을 제공 → 제목 끝의 " - 매체명" 제거
            src_m = re.search(r"<source[^>]*>(.*?)</source>", block, re.IGNORECASE | re.DOTALL)
            if src_m:
                pub = _clean(src_m.group(1))
                title = re.sub(re.escape(f" - {pub}") + r"\s*$", "", title).strip()
        if not title or title.lower() == "google news":
            continue
        summary = _clean(desc_m.group(1))[:300] if desc_m else ""
        # Google News description은 관련기사 링크 HTML 덩어리라 쓸모없음 → 버림
        if is_gnews or "href=" in summary:
            summary = ""
        items.append({
            "title": title,
            "summary": summary,
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


def fetch_region(region: str, limit: int = 40, per_feed: int = 12) -> list[dict]:
    """region 코드(US/KR/JP/TW/CN/EUROPE)에 등록된 피드를 모두 수집해 최대 limit건 반환.

    피드를 라운드로빈으로 섞어 특정 피드(Google News 등 100건 반환)가 결과를 독점하지 않게 한다.
    per_feed: 피드당 상한.
    """
    feeds = REGION_FEEDS.get(region, [])
    per_feed_items: list[list[dict]] = []
    seen_titles: set[str] = set()
    for source, url in feeds:
        picked: list[dict] = []
        for item in _fetch_one(source, url):
            if len(picked) >= per_feed:
                break
            key = item["title"].lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            picked.append(item)
        per_feed_items.append(picked)

    interleaved: list[dict] = []
    for i in range(per_feed):
        for feed_items in per_feed_items:
            if i < len(feed_items):
                interleaved.append(feed_items[i])
    return interleaved[:limit]
