"""
PWA 데이터 export — cache/*.json → docs/news-app/data/*.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from news_fetcher import today_kst, load_cache

DOCS_DATA_DIR = Path(__file__).parent.parent.parent / "docs" / "news-app" / "data"


def _write(name: str, data: dict) -> None:
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DATA_DIR / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def export_app_data(us: dict, asia: dict, europe: dict, sectors: dict, ideas: dict) -> None:
    regions = {
        "date": us.get("date") or asia.get("date") or europe.get("date") or today_kst(),
        "us": us,
        "asia": asia,
        "europe": europe,
    }
    _write("regions.json", regions)
    _write("sectors.json", sectors)
    _write("ideas.json", ideas)


def main():
    """캐시 파일에서 직접 읽어 export (run_pipeline.py 없이 단독 실행할 때 사용)."""
    today = today_kst()
    us = load_cache("us_market.json") or {"date": today, "region": "US", "headlines": [], "summary": ""}
    asia = load_cache("asia_market.json") or {"date": today, "region": "ASIA", "countries": {}, "summary": ""}
    europe = load_cache("europe_market.json") or {"date": today, "region": "EUROPE", "headlines": [], "summary": ""}
    sectors = load_cache("sector_mapping.json") or {"date": today, "sectors": [], "conflicting_signals": []}
    ideas = load_cache("investment_ideas.json") or {"date": today, "horizons": {h: [] for h in ["1w", "1m", "3m", "6m", "1y"]}}
    export_app_data(us, asia, europe, sectors, ideas)
    print("docs/news-app/data/{regions,sectors,ideas}.json 저장 완료")


if __name__ == "__main__":
    main()
