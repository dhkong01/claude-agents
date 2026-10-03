"""
대가(유명 투자자) 인사이트 추출
오늘자 미국 시장 헤드라인에서 버핏·달리오·드러켄밀러 등 유명 투자자가 실제로
언급된 기사만 찾아 요약한다. 목록 밖 인물이거나 헤드라인에 근거가 없으면
절대 포함하지 않음 — AI가 지어낸 가상 발언을 실제 인물 발언으로 표시하는
것을 방지하기 위함 (해당하는 기사가 없으면 insights는 빈 배열).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gemini_client import call_gemini_json, MODEL_LIGHT
from news_fetcher import cache_fresh, fetch_region, load_cache, save_cache, today_kst

KNOWN_GURUS = [
    "Warren Buffett", "Charlie Munger", "Ray Dalio", "Stanley Druckenmiller",
    "Carl Icahn", "Bill Ackman", "Cathie Wood", "Michael Burry", "George Soros",
    "Howard Marks", "Jim Simons", "David Tepper", "Jeffrey Gundlach", "Bill Gross",
    "Jim Cramer", "Jamie Dimon",
]

SYSTEM_PROMPT = f"""당신은 금융 뉴스에서 유명 투자자(투자 대가)의 발언·시각만 정확히 추출하는 애널리스트입니다.
아래 인물 목록에 해당하는 사람이 실제로 언급된 헤드라인/요약이 있을 때만 결과에 포함하세요:
{', '.join(KNOWN_GURUS)}

규칙(반드시 준수):
- 목록에 없는 인물이거나, 제공된 헤드라인/요약에 해당 인물의 실제 발언·시각이 드러나지 않으면 절대 포함하지 마세요.
- 추측하거나 지어내지 마세요 — 반드시 제공된 헤드라인/요약 내용에만 근거해야 합니다.
- 해당하는 기사가 하나도 없으면 insights를 빈 배열로 반환하세요. 없는데 억지로 만들어내지 마세요.
- insight는 직접 인용부호로 가상의 발언을 지어내지 말고, 헤드라인/요약을 근거로 한 1문장 한국어 요약으로 쓰세요.

반드시 아래 JSON 스키마로만 응답하고 다른 설명은 절대 추가하지 마세요.

{{
  "insights": [
    {{
      "name": "인물 전체 이름(영문)",
      "insight": "헤드라인/요약에 근거한 1문장 한국어 요약",
      "source": "매체명",
      "link": "원문 링크"
    }}
  ]
}}"""


def _build_user_prompt(items: list[dict]) -> str:
    lines = [
        f"- [{it['source']}] {it['title']}"
        + (f" — {it['summary']}" if it["summary"] else "")
        + f" (link: {it['link']})"
        for it in items
    ]
    return (
        f"오늘은 {today_kst()}입니다. 아래 헤드라인 중 목록에 있는 유명 투자자가 "
        "실제로 언급된 것이 있으면 찾아주세요. 없으면 빈 배열로 응답하세요.\n\n"
        + "\n".join(lines)
    )


def analyze_guru_insights(dry_run: bool = False) -> dict:
    today = today_kst()
    items = fetch_region("US", limit=40)

    result: dict = {"date": today, "insights": []}

    if dry_run or not items:
        save_cache("guru_insights.json", result)
        return result

    parsed = call_gemini_json(SYSTEM_PROMPT, _build_user_prompt(items), model=MODEL_LIGHT)
    if parsed:
        result["insights"] = parsed.get("insights", [])

    save_cache("guru_insights.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Gemini 호출 없이 RSS 수집만 검증")
    args = parser.parse_args()

    today = today_kst()
    if not args.dry_run and cache_fresh("guru_insights.json", today):
        print("[guru_insights] 당일 캐시 존재 — 재실행 생략")
        return load_cache("guru_insights.json")

    result = analyze_guru_insights(dry_run=args.dry_run)
    print(f"[guru_insights] {len(result['insights'])}건 추출")
    return result


if __name__ == "__main__":
    main()
