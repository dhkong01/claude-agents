"""
아시아 시장 뉴스 에이전트 (한국/일본/대만/중국)
국가별 RSS 수집 → Gemini 종합 → cache/asia_market.json
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gemini_client import call_gemini_json, MODEL_LIGHT
from news_fetcher import fetch_region, today_kst, cache_fresh, load_cache, save_cache

COUNTRIES = ["KR", "JP", "TW", "CN"]

SYSTEM_PROMPT = """당신은 아시아(한국/일본/대만/중국) 시장을 분석하는 매크로 애널리스트입니다.
국가별 헤드라인 목록을 바탕으로 국가별 요약과 아시아 전체 종합 브리핑을 한국어로 작성하세요.
- 한국: 반도체·수출 지표·환율·기준금리
- 일본: BOJ 통화정책·엔화·수출기업 실적
- 대만: 반도체(TSMC)·양안관계 리스크
- 중국: 경기부양책·부동산·수출입 지표·규제 동향
4개국에 공통적으로 걸친 테마가 있으면 cross_country_themes로 별도 추출하세요.
반드시 아래 JSON 스키마로만 응답하고 다른 설명은 절대 추가하지 마세요.

{
  "countries": {
    "KR": {"summary": "..."},
    "JP": {"summary": "..."},
    "TW": {"summary": "..."},
    "CN": {"summary": "..."}
  },
  "summary": "아시아 전체 2~4문장 종합",
  "cross_country_themes": ["테마1", "테마2"],
  "sector_hints": ["Semiconductors", "Real Estate"]
}"""


def _build_user_prompt(country_items: dict[str, list[dict]]) -> str:
    parts = []
    for country in COUNTRIES:
        items = country_items.get(country, [])
        if not items:
            parts.append(f"[{country}] 수집된 헤드라인 없음")
            continue
        lines = [f"  - [{it['source']}] {it['title']} — {it['summary']}" for it in items]
        parts.append(f"[{country}]\n" + "\n".join(lines))
    return "국가별 오늘자 헤드라인 목록:\n\n" + "\n\n".join(parts)


def analyze_asia_market(dry_run: bool = False) -> dict:
    today = today_kst()
    country_items = {c: fetch_region(c, limit=10) for c in COUNTRIES}

    result: dict = {
        "date": today,
        "region": "ASIA",
        "countries": {c: {"headlines": country_items[c], "summary": ""} for c in COUNTRIES},
        "summary": "",
        "cross_country_themes": [],
        "sector_hints": [],
    }

    has_any = any(country_items.values())
    if dry_run or not has_any:
        save_cache("asia_market.json", result)
        return result

    parsed = call_gemini_json(SYSTEM_PROMPT, _build_user_prompt(country_items), model=MODEL_LIGHT)
    if parsed:
        parsed_countries = parsed.get("countries", {})
        for c in COUNTRIES:
            result["countries"][c]["summary"] = parsed_countries.get(c, {}).get("summary", "")
        result["summary"] = parsed.get("summary", "")
        result["cross_country_themes"] = parsed.get("cross_country_themes", [])
        result["sector_hints"] = parsed.get("sector_hints", [])

    save_cache("asia_market.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Gemini 호출 없이 RSS 수집만 검증")
    args = parser.parse_args()

    today = today_kst()
    if not args.dry_run and cache_fresh("asia_market.json", today):
        print("[asia_market] 당일 캐시 존재 — 재실행 생략")
        return load_cache("asia_market.json")

    result = analyze_asia_market(dry_run=args.dry_run)
    total = sum(len(v["headlines"]) for v in result["countries"].values())
    print(f"[asia_market] 헤드라인 {total}건 수집 (KR/JP/TW/CN), 요약: {result['summary'][:60]}")
    return result


if __name__ == "__main__":
    main()
