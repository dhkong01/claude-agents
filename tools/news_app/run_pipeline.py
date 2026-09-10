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


def _step(idx, label, cache_file, today, dry_run, fn, empty, is_ok):
    """단계 실행 결과를 (data, produced_fresh) 로 반환.

    - 당일 KST 캐시가 있으면 그대로 재사용 (백업 실행이 Gemini 재호출 안 하도록)
    - 없으면 fn() 실행. 결과가 유의미하면(is_ok) 그걸 쓰고,
      실패/빈 결과면 직전 캐시(오래됐어도 실데이터)로 폴백 → 섹션이 통째로 비지 않게.
    - 직전 캐시도 없으면 empty.
    """
    print(f"\n[{idx}/5] {label}...")
    if not dry_run and cache_fresh(cache_file, today):
        print(f"      당일 캐시 재사용 ({cache_file})")
        return load_cache(cache_file), False

    result = fn()
    if result and is_ok(result):
        return result, True

    prev = load_cache(cache_file)
    if prev and is_ok(prev):
        print(f"      Gemini 결과 없음 → 직전 캐시 유지 ({prev.get('date')})", file=sys.stderr)
        return prev, False

    return (result or empty), False


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

    ok_region = lambda d: bool(d.get("summary")) or any(v.get("summary") for v in d.get("countries", {}).values())
    ok_sectors = lambda d: bool(d.get("sectors"))
    ok_ideas = lambda d: any(d.get("horizons", {}).values())

    us, f1 = _step(1, "미국 시장 에이전트", "us_market.json", today, dry_run,
                   lambda: analyze_us_market(dry_run=dry_run),
                   {"date": today, "region": "US", "headlines": [], "summary": ""}, ok_region)
    print(f"      헤드라인 {len(us.get('headlines', []))}건")

    asia, f2 = _step(2, "아시아 시장 에이전트", "asia_market.json", today, dry_run,
                     lambda: analyze_asia_market(dry_run=dry_run),
                     {"date": today, "region": "ASIA", "countries": {}, "summary": ""}, ok_region)
    asia_count = sum(len(v.get("headlines", [])) for v in asia.get("countries", {}).values())
    print(f"      헤드라인 {asia_count}건 (KR/JP/TW/CN)")

    europe, f3 = _step(3, "유럽 에이전트", "europe_market.json", today, dry_run,
                       lambda: analyze_europe_market(dry_run=dry_run),
                       {"date": today, "region": "EUROPE", "headlines": [], "summary": ""}, ok_region)
    print(f"      헤드라인 {len(europe.get('headlines', []))}건")

    sectors, f4 = _step(4, "섹터 매퍼", "sector_mapping.json", today, dry_run,
                        lambda: map_sectors(dry_run=dry_run),
                        {"date": today, "sectors": [], "conflicting_signals": []}, ok_sectors)
    print(f"      섹터 {len(sectors.get('sectors', []))}개 매핑")

    ideas, f5 = _step(5, "오케스트레이터 (투자 아이디어)", "investment_ideas.json", today, dry_run,
                      lambda: generate_ideas(dry_run=dry_run), empty_ideas, ok_ideas)
    counts = {h: len(v) for h, v in ideas.get("horizons", {}).items()}
    print(f"      호라이즌별 아이디어 수: {counts}")

    fresh_count = sum([f1, f2, f3, f4, f5])
    served = {
        "미국 요약": ok_region(us), "아시아 요약": ok_region(asia), "유럽 요약": ok_region(europe),
        "섹터 매핑": ok_sectors(sectors), "투자 아이디어": ok_ideas(ideas),
    }
    served_count = sum(served.values())

    if dry_run:
        print("\n[export] --dry-run: docs/news-app/data 저장 생략 (커밋된 데이터 보존)")
    elif served_count == 0:
        print("\n[export] 신규·기존 데이터 모두 없음 → docs 저장 생략 (기존 파일 보존)", file=sys.stderr)
    else:
        print("\n[export] PWA 데이터 내보내기...")
        from export_app_data import export_app_data
        export_app_data(us, asia, europe, sectors, ideas)
        print("      docs/news-app/data/{regions,sectors,ideas}.json 저장 완료")

    print(f"\n{'='*60}")
    print(f"  이번 실행 신규 생성: {fresh_count}/5 · 화면 제공(신규+직전): {served_count}/5")
    for name, ok in served.items():
        print(f"    [{'OK' if ok else 'FAIL'}] {name}")
    print(f"{'='*60}\n")

    if not dry_run and fresh_count == 0:
        print(
            "[run_pipeline] 이번 실행에서 Gemini 종합을 하나도 새로 만들지 못했습니다.\n"
            "               (화면은 직전 데이터로 유지) GEMINI_API_KEY / 위 [gemini_client] 오류를 확인하세요.",
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
