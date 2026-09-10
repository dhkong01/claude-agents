"""
뉴스·투자아이디어 파이프라인 — 메인 실행기

Usage:
  python run_pipeline.py [--dry-run]

--dry-run: Gemini API 호출 없이 RSS 수집 + 캐시/스키마 검증만 수행 (로컬 확인용)
"""
import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from news_fetcher import today_kst, cache_fresh, load_cache


def _step(idx: int, label: str, cache_file: str, today: str, dry_run: bool, fn, fallback):
    """당일 KST 캐시가 있으면 재사용(백업 실행이 Gemini를 다시 호출하지 않도록),
    없으면 fn() 실행. fn/캐시 모두 실패하면 fallback 반환."""
    print(f"\n[{idx}/5] {label}...")
    if not dry_run and cache_fresh(cache_file, today):
        print(f"      당일 캐시 재사용 ({cache_file})")
        return load_cache(cache_file)
    return fn() or fallback


def run_pipeline(dry_run: bool = False) -> dict:
    today = today_kst()
    print(f"\n{'='*60}")
    print(f"  뉴스·투자아이디어 파이프라인  {today}{'  [DRY-RUN]' if dry_run else ''}")
    print(f"{'='*60}")

    from us_market_agent import analyze_us_market
    from asia_market_agent import analyze_asia_market
    from europe_market_agent import analyze_europe_market
    from sector_mapper import map_sectors
    from orchestrator import generate_ideas

    empty_ideas = {"date": today, "horizons": {h: [] for h in ["1w", "1m", "3m", "6m", "1y"]}}

    us = _step(1, "미국 시장 에이전트", "us_market.json", today, dry_run,
               lambda: analyze_us_market(dry_run=dry_run),
               {"date": today, "region": "US", "headlines": [], "summary": ""})
    print(f"      헤드라인 {len(us.get('headlines', []))}건")

    asia = _step(2, "아시아 시장 에이전트", "asia_market.json", today, dry_run,
                 lambda: analyze_asia_market(dry_run=dry_run),
                 {"date": today, "region": "ASIA", "countries": {}, "summary": ""})
    asia_count = sum(len(v.get("headlines", [])) for v in asia.get("countries", {}).values())
    print(f"      헤드라인 {asia_count}건 (KR/JP/TW/CN)")

    europe = _step(3, "유럽 에이전트", "europe_market.json", today, dry_run,
                   lambda: analyze_europe_market(dry_run=dry_run),
                   {"date": today, "region": "EUROPE", "headlines": [], "summary": ""})
    print(f"      헤드라인 {len(europe.get('headlines', []))}건")

    sectors = _step(4, "섹터 매퍼", "sector_mapping.json", today, dry_run,
                    lambda: map_sectors(dry_run=dry_run),
                    {"date": today, "sectors": [], "conflicting_signals": []})
    print(f"      섹터 {len(sectors.get('sectors', []))}개 매핑")

    ideas = _step(5, "오케스트레이터 (투자 아이디어)", "investment_ideas.json", today, dry_run,
                  lambda: generate_ideas(dry_run=dry_run), empty_ideas)
    counts = {h: len(v) for h, v in ideas.get("horizons", {}).items()}
    print(f"      호라이즌별 아이디어 수: {counts}")

    if dry_run:
        print("\n[export] --dry-run — docs/news-app/data 저장 생략 (커밋된 데이터 보존)")
    else:
        print("\n[export] PWA 데이터 내보내기...")
        from export_app_data import export_app_data
        export_app_data(us, asia, europe, sectors, ideas)
        print("      docs/news-app/data/{regions,sectors,ideas}.json 저장 완료")

    checks = {
        "미국 요약": bool(us.get("summary")),
        "아시아 요약": bool(asia.get("summary")) or any(v.get("summary") for v in asia.get("countries", {}).values()),
        "유럽 요약": bool(europe.get("summary")),
        "섹터 매핑": bool(sectors.get("sectors")),
        "투자 아이디어": any(ideas.get("horizons", {}).values()),
    }
    ok_count = sum(checks.values())

    print(f"\n{'='*60}")
    print(f"  Gemini 종합 결과: {ok_count}/5 단계 성공")
    for name, ok in checks.items():
        print(f"    [{'OK' if ok else 'FAIL'}] {name}")
    print(f"{'='*60}\n")

    if not dry_run and ok_count == 0:
        print(
            "[run_pipeline] 5개 단계 전부 실패 — RSS 수집은 됐지만 Gemini 종합이 전혀 반영되지 않았습니다.\n"
            "               GEMINI_API_KEY 시크릿 값/이름과 위 [gemini_client] 오류 로그를 확인하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    return {"us": us, "asia": asia, "europe": europe, "sectors": sectors, "ideas": ideas}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Gemini API 호출 없이 RSS 수집/스키마만 검증")
    args = parser.parse_args()
    run_pipeline(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
