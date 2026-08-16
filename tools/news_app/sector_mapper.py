"""
섹터 매핑 에이전트
us_market + asia_market + europe_market 종합 → GICS 11개 섹터 영향 매핑
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gemini_client import call_gemini_json, MODEL_HEAVY
from news_fetcher import today_kst, cache_fresh, load_cache, save_cache

SECTORS = [
    "Technology", "Semiconductors", "Financials", "Healthcare", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Real Estate", "Utilities", "Communication Services",
]

SYSTEM_PROMPT = f"""당신은 글로벌 매크로 뉴스를 주식 섹터 영향으로 변환하는 섹터 전략가입니다.
미국/아시아/유럽 3개 지역의 종합 브리핑을 받아 GICS 섹터({', '.join(SECTORS)}) 중
실제 뉴스 근거가 있는 섹터에 대해서만 방향성을 판단하세요. 근거 없는 섹터는 생략하세요.
지역 간 신호가 서로 다르면(예: 미국은 긍정적, 유럽은 부정적) conflicting_signals로 표기하세요.
반드시 아래 JSON 스키마로만 응답하고 다른 설명은 절대 추가하지 마세요.

{{
  "sectors": [
    {{
      "name": "Semiconductors",
      "direction": "positive",
      "score": 7.5,
      "rationale": "근거 설명 (한국어)",
      "related_tickers": ["NVDA", "TSM"],
      "source_regions": ["US", "ASIA"]
    }}
  ],
  "conflicting_signals": [
    {{"sector": "Energy", "note": "지역별 온도차 설명"}}
  ]
}}
direction은 positive/negative/neutral 중 하나, score는 -10~10 (양수=긍정)."""


def _build_user_prompt(us: dict, asia: dict, europe: dict) -> str:
    parts = [
        f"[미국]\n요약: {us.get('summary', '')}\n핵심포인트: {us.get('key_points', [])}\n섹터힌트: {us.get('sector_hints', [])}",
        f"[아시아]\n요약: {asia.get('summary', '')}\n국가별: {[(c, v.get('summary', '')) for c, v in asia.get('countries', {}).items()]}\n"
        f"공통테마: {asia.get('cross_country_themes', [])}\n섹터힌트: {asia.get('sector_hints', [])}",
        f"[유럽]\n요약: {europe.get('summary', '')}\n핵심포인트: {europe.get('key_points', [])}\n섹터힌트: {europe.get('sector_hints', [])}",
    ]
    return "지역별 종합 브리핑:\n\n" + "\n\n".join(parts)


def map_sectors(dry_run: bool = False) -> dict | None:
    today = today_kst()
    us = load_cache("us_market.json")
    asia = load_cache("asia_market.json")
    europe = load_cache("europe_market.json")

    if not (us and asia and europe):
        print("[sector_mapper] 지역 캐시 미완비 — us/asia/europe 에이전트를 먼저 실행하세요", file=sys.stderr)
        return None

    result: dict = {"date": today, "sectors": [], "conflicting_signals": []}

    if dry_run:
        save_cache("sector_mapping.json", result)
        return result

    parsed = call_gemini_json(
        SYSTEM_PROMPT, _build_user_prompt(us, asia, europe),
        model=MODEL_HEAVY,
    )
    if parsed:
        result["sectors"] = parsed.get("sectors", [])
        result["conflicting_signals"] = parsed.get("conflicting_signals", [])

    save_cache("sector_mapping.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Gemini 호출 없이 입력 캐시 검증만")
    args = parser.parse_args()

    today = today_kst()
    if not args.dry_run and cache_fresh("sector_mapping.json", today):
        print("[sector_mapper] 당일 캐시 존재 — 재실행 생략")
        return load_cache("sector_mapping.json")

    result = map_sectors(dry_run=args.dry_run)
    if result:
        print(f"[sector_mapper] 섹터 {len(result['sectors'])}개 매핑 완료")
    return result


if __name__ == "__main__":
    main()
