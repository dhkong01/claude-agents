"""
뉴스·투자아이디어 파이프라인 — 메인 실행기

Usage:
  python run_pipeline.py [--dry-run]

--dry-run: Gemini API 호출 없이 RSS 수집 + 스키마 검증만 수행 (캐시·docs 파일은 건드리지 않음)

단계별 상태:
  cached  오늘(KST) 이미 정상 생성된 캐시가 있어 재사용 (백업 cron/재실행 — 정상)
  fresh   이번 실행에서 Gemini로 새로 생성
  stale   생성 실패 → 직전 정상 데이터로 화면 유지
  failed  생성 실패 + 직전 데이터도 없음

종료 코드: 이번 실행에서 "생성이 필요했던" 단계가 있는데 하나도 성공하지 못했을 때만 1.
(전부 cached 인 경우는 할 일이 없는 정상 상태이므로 0)
"""
import argparse
import sys
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from news_fetcher import today_kst, load_cache

CACHED, FRESH, STALE, FAILED = "cached", "fresh", "stale", "failed"
STATUS_LABEL = {CACHED: "당일캐시", FRESH: "신규생성", STALE: "직전유지", FAILED: "실패"}


def _step(idx, label, cache_file, today, dry_run, fn, empty, is_ok):
    """단계를 실행하고 (data, status)를 반환한다.

    캐시는 fn() 실행 '전에' 읽어 둔다 — 에이전트가 파일을 덮어써도 직전 정상본을 잃지 않기 위함.
    """
    print(f"\n[{idx}/6] {label}...")
    cached = load_cache(cache_file)

    if not dry_run and cached and cached.get("date") == today and is_ok(cached):
        print(f"      당일 캐시 재사용 ({cache_file})")
        return cached, CACHED

    try:
        result = fn()
    except Exception as e:  # 한 단계의 예외가 나머지 단계·export까지 막지 않도록
        print(f"      [오류] {label} 실행 중 예외: {e!r}", file=sys.stderr)
        traceback.print_exc()
        result = None

    if result and result.get("date") == today and is_ok(result):
        return result, FRESH

    if cached and is_ok(cached):
        print(f"      새로 만들지 못함 → 직전 데이터 유지 (기준일 {cached.get('date')})", file=sys.stderr)
        return cached, STALE

    return (result or empty), FAILED


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
    from guru_insights import analyze_guru_insights

    empty_ideas = {"date": today, "horizons": {h: [] for h in ["1w", "1m", "3m", "6m", "1y"]}}

    ok_region = lambda d: bool(d.get("summary")) or any(v.get("summary") for v in d.get("countries", {}).values())
    ok_sectors = lambda d: bool(d.get("sectors"))
    ok_ideas = lambda d: any(d.get("horizons", {}).values())

    us, s1 = _step(1, "미국 시장 에이전트", "us_market.json", today, dry_run,
                   lambda: analyze_us_market(dry_run=dry_run),
                   {"date": today, "region": "US", "headlines": [], "summary": ""}, ok_region)
    print(f"      헤드라인 {len(us.get('headlines', []))}건")

    asia, s2 = _step(2, "아시아 시장 에이전트", "asia_market.json", today, dry_run,
                     lambda: analyze_asia_market(dry_run=dry_run),
                     {"date": today, "region": "ASIA", "countries": {}, "summary": ""}, ok_region)
    asia_count = sum(len(v.get("headlines", [])) for v in asia.get("countries", {}).values())
    print(f"      헤드라인 {asia_count}건 (KR/JP/TW/CN)")

    europe, s3 = _step(3, "유럽 에이전트", "europe_market.json", today, dry_run,
                       lambda: analyze_europe_market(dry_run=dry_run),
                       {"date": today, "region": "EUROPE", "headlines": [], "summary": ""}, ok_region)
    print(f"      헤드라인 {len(europe.get('headlines', []))}건")

    sectors, s4 = _step(4, "섹터 매퍼", "sector_mapping.json", today, dry_run,
                        lambda: map_sectors(dry_run=dry_run),
                        {"date": today, "sectors": [], "conflicting_signals": []}, ok_sectors)
    print(f"      섹터 {len(sectors.get('sectors', []))}개 매핑")

    ideas, s5 = _step(5, "오케스트레이터 (투자 아이디어)", "investment_ideas.json", today, dry_run,
                      lambda: generate_ideas(dry_run=dry_run), empty_ideas, ok_ideas)
    counts = {h: len(v) for h, v in ideas.get("horizons", {}).items()}
    print(f"      호라이즌별 아이디어 수: {counts}")

    # 대가 인사이트 — 다른 PWA(docs/data/market_pulse.json)가 소비하는 독립 피처라
    # 실패해도 이 파이프라인의 성공 여부 판단에는 영향을 주지 않는다.
    # 오류 표시(error)가 붙은 캐시는 재사용하지 않아 다음 실행에서 재시도된다.
    guru, s6 = _step(6, "대가 인사이트 추출", "guru_insights.json", today, dry_run,
                     lambda: analyze_guru_insights(dry_run=dry_run),
                     {"date": today, "insights": []}, lambda d: not d.get("error"))
    print(f"      대가 인사이트 {len(guru.get('insights', []))}건 [{STATUS_LABEL[s6]}]")

    steps = {
        "미국 요약": (s1, ok_region(us)), "아시아 요약": (s2, ok_region(asia)), "유럽 요약": (s3, ok_region(europe)),
        "섹터 매핑": (s4, ok_sectors(sectors)), "투자 아이디어": (s5, ok_ideas(ideas)),
    }
    statuses = [st for st, _ in steps.values()]
    attempted = sum(1 for st in statuses if st != CACHED)   # 이번 실행에서 생성이 필요했던 단계
    fresh_n = statuses.count(FRESH)
    served_n = sum(1 for _, ok in steps.values() if ok)

    if dry_run:
        print("\n[export] --dry-run: docs/news-app/data 저장 생략 (커밋된 데이터 보존)")
    elif served_n == 0:
        print("\n[export] 신규·기존 데이터 모두 없음 → docs 저장 생략 (기존 파일 보존)", file=sys.stderr)
    else:
        print("\n[export] PWA 데이터 내보내기...")
        from export_app_data import export_app_data
        export_app_data(us, asia, europe, sectors, ideas)
        print("      docs/news-app/data/{regions,sectors,ideas}.json 저장 완료")

    print(f"\n{'='*60}")
    if attempted == 0:
        print("  모든 단계가 오늘자 캐시 — 새로 만들 것 없음 (정상)")
    else:
        print(f"  생성 필요 {attempted}단계 중 성공 {fresh_n} · 화면 제공 {served_n}/5")
    for name, (st, ok) in steps.items():
        print(f"    [{'OK' if ok else 'FAIL'}] {name} ({STATUS_LABEL[st]})")
    print(f"{'='*60}\n", flush=True)

    if dry_run:
        return {"us": us, "asia": asia, "europe": europe, "sectors": sectors, "ideas": ideas}

    if attempted > 0 and fresh_n == 0:
        print(
            f"[run_pipeline] 생성이 필요했던 {attempted}단계가 전부 실패했습니다.\n"
            "               (화면은 직전 데이터로 유지) GEMINI_API_KEY / 위 [gemini_client] 오류를 확인하세요.",
            file=sys.stderr,
        )
        sys.exit(1)
    if attempted > fresh_n:
        print(f"::warning::뉴스 파이프라인 일부 단계 실패 — 생성 필요 {attempted}단계 중 {fresh_n}단계만 성공 (나머지는 직전 데이터 유지)")

    return {"us": us, "asia": asia, "europe": europe, "sectors": sectors, "ideas": ideas}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Gemini API 호출 없이 RSS 수집/스키마만 검증")
    args = parser.parse_args()
    run_pipeline(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
