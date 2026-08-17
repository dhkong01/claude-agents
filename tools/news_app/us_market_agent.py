"""
미국 시장 뉴스 에이전트
CNBC/MarketWatch/WSJ/Yahoo RSS 수집 → Gemini 종합 → cache/us_market.json
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gemini_client import call_gemini_json, MODEL_LIGHT
from news_fetcher import fetch_region, today_kst, cache_fresh, load_cache, save_cache

SYSTEM_PROMPT = """당신은 미국 주식시장을 분석하는 전문 애널리스트입니다.
목표는 "오늘 미국 시장에 무슨 트렌드가 있었는지"를 매일 다르게 짚어내는 것입니다.
"미국 증시는 다양한 이슈로 움직였습니다" 같은 상투적이고 매일 비슷한 서두는 절대 쓰지 말고,
오늘 헤드라인들 중 가장 두드러지는 흐름/변화 하나를 바로 짚어서 시작하세요.
거시경제(금리·인플레이션·고용), 빅테크 실적, 연준 발언, 주요 기업 이벤트를 우선순위로 반영하고
확인되지 않은 추측성 루머는 배제하세요.
반드시 아래 JSON 스키마로만 응답하고 다른 설명은 절대 추가하지 마세요.

{
  "trend_headline": "오늘의 핵심 트렌드를 한 문장으로 (20~25자, 강조 배지로 표시될 헤드라인)",
  "summary": "2~3문장 — 오늘 트렌드 중심 브리핑, 상투적 서두 없이 바로 핵심부터",
  "key_points": ["구체적 수치/고유명사가 들어간 핵심 포인트1", "핵심 포인트2", "핵심 포인트3"],
  "sector_hints": ["Technology", "Financials"]
}"""


def _build_user_prompt(items: list[dict]) -> str:
    lines = [f"- [{it['source']}] {it['title']} — {it['summary']}" for it in items]
    return "오늘자 미국 시장 헤드라인 목록:\n" + "\n".join(lines)


def analyze_us_market(dry_run: bool = False) -> dict:
    today = today_kst()
    items = fetch_region("US", limit=40)

    result: dict = {
        "date": today,
        "region": "US",
        "headlines": items[:20],
        "trend_headline": "",
        "summary": "",
        "key_points": [],
        "sector_hints": [],
    }

    if dry_run or not items:
        save_cache("us_market.json", result)
        return result

    parsed = call_gemini_json(SYSTEM_PROMPT, _build_user_prompt(items), model=MODEL_LIGHT)
    if parsed:
        result["trend_headline"] = parsed.get("trend_headline", "")
        result["summary"] = parsed.get("summary", "")
        result["key_points"] = parsed.get("key_points", [])
        result["sector_hints"] = parsed.get("sector_hints", [])

    save_cache("us_market.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Gemini 호출 없이 RSS 수집만 검증")
    args = parser.parse_args()

    today = today_kst()
    if not args.dry_run and cache_fresh("us_market.json", today):
        print("[us_market] 당일 캐시 존재 — 재실행 생략")
        return load_cache("us_market.json")

    result = analyze_us_market(dry_run=args.dry_run)
    print(f"[us_market] 헤드라인 {len(result['headlines'])}건 수집, 요약: {result['summary'][:60]}")
    return result


if __name__ == "__main__":
    main()
