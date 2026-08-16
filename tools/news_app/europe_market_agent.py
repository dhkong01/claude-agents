"""
유럽 뉴스 에이전트
BBC/Euronews/DW/Politico RSS 수집 → Gemini 종합 → cache/europe_market.json
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gemini_client import call_gemini_json, MODEL_LIGHT
from news_fetcher import fetch_region, today_kst, cache_fresh, load_cache, save_cache

SYSTEM_PROMPT = """당신은 유럽 시장·정책을 분석하는 매크로 애널리스트입니다.
주어진 헤드라인 목록을 바탕으로 실제 시장에 의미있는 종합 브리핑을 한국어로 작성하세요.
ECB 통화정책·유로존 인플레이션·독일/프랑스 경기지표를 우선순위로 반영하고,
EU 규제(반독점·AI법·관세)가 특정 섹터(빅테크·자동차·에너지)에 미치는 영향을 명시하세요.
지정학 이슈(우크라이나 전쟁 등)는 자체 리스크 스코어링이 아니라 Energy/Defense 섹터
시사점 위주로만 요약하세요.
반드시 아래 JSON 스키마로만 응답하고 다른 설명은 절대 추가하지 마세요.

{
  "summary": "2~4문장 종합 브리핑",
  "key_points": ["핵심 포인트1", "핵심 포인트2"],
  "sector_hints": ["Energy", "Financials"]
}"""


def _build_user_prompt(items: list[dict]) -> str:
    lines = [f"- [{it['source']}] {it['title']} — {it['summary']}" for it in items]
    return "오늘자 유럽 헤드라인 목록:\n" + "\n".join(lines)


def analyze_europe_market(dry_run: bool = False) -> dict:
    today = today_kst()
    items = fetch_region("EUROPE", limit=40)

    result: dict = {
        "date": today,
        "region": "EUROPE",
        "headlines": items[:20],
        "summary": "",
        "key_points": [],
        "sector_hints": [],
    }

    if dry_run or not items:
        save_cache("europe_market.json", result)
        return result

    parsed = call_gemini_json(SYSTEM_PROMPT, _build_user_prompt(items), model=MODEL_LIGHT)
    if parsed:
        result["summary"] = parsed.get("summary", "")
        result["key_points"] = parsed.get("key_points", [])
        result["sector_hints"] = parsed.get("sector_hints", [])

    save_cache("europe_market.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Gemini 호출 없이 RSS 수집만 검증")
    args = parser.parse_args()

    today = today_kst()
    if not args.dry_run and cache_fresh("europe_market.json", today):
        print("[europe_market] 당일 캐시 존재 — 재실행 생략")
        return load_cache("europe_market.json")

    result = analyze_europe_market(dry_run=args.dry_run)
    print(f"[europe_market] 헤드라인 {len(result['headlines'])}건 수집, 요약: {result['summary'][:60]}")
    return result


if __name__ == "__main__":
    main()
