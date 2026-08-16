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

from news_fetcher import today_kst


def run_pipeline(dry_run: bool = False) -> dict:
    today = today_kst()
    print(f"\n{'='*60}")
    print(f"  뉴스·투자아이디어 파이프라인  {today}{'  [DRY-RUN]' if dry_run else ''}")
    print(f"{'='*60}")

    print("\n[1/5] 미국 시장 에이전트...")
    from us_market_agent import analyze_us_market
    us = analyze_us_market(dry_run=dry_run)
    print(f"      헤드라인 {len(us['headlines'])}건")

    print("\n[2/5] 아시아 시장 에이전트...")
    from asia_market_agent import analyze_asia_market
    asia = analyze_asia_market(dry_run=dry_run)
    asia_count = sum(len(v["headlines"]) for v in asia["countries"].values())
    print(f"      헤드라인 {asia_count}건 (KR/JP/TW/CN)")

    print("\n[3/5] 유럽 에이전트...")
    from europe_market_agent import analyze_europe_market
    europe = analyze_europe_market(dry_run=dry_run)
    print(f"      헤드라인 {len(europe['headlines'])}건")

    print("\n[4/5] 섹터 매퍼...")
    from sector_mapper import map_sectors
    sectors = map_sectors(dry_run=dry_run) or {"date": today, "sectors": [], "conflicting_signals": []}
    print(f"      섹터 {len(sectors['sectors'])}개 매핑")

    print("\n[5/5] 오케스트레이터 (투자 아이디어)...")
    from orchestrator import generate_ideas
    ideas = generate_ideas(dry_run=dry_run) or {"date": today, "horizons": {h: [] for h in ["1w", "1m", "3m", "6m", "1y"]}}
    counts = {h: len(v) for h, v in ideas["horizons"].items()}
    print(f"      호라이즌별 아이디어 수: {counts}")

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
