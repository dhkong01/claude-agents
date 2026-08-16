"""
뉴스·투자아이디어 오케스트레이터
지역 3개 + 섹터매핑 종합 → 1주/1개월/3개월/6개월/1년 투자 아이디어
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gemini_client import call_gemini_json, MODEL_HEAVY
from news_fetcher import today_kst, cache_fresh, load_cache, save_cache

HORIZONS = ["1w", "1m", "3m", "6m", "1y"]

SYSTEM_PROMPT = """당신은 글로벌 매크로/섹터 분석을 투자 아이디어로 변환하는 수석 전략가입니다.
지역별(미국/아시아/유럽) 종합 브리핑과 섹터 매핑 결과를 받아 투자 호라이즌별
(1주/1개월/3개월/6개월/1년) 아이디어를 생성하세요.

판단 기준:
- 1w(1주): 당일 헤드라인 중 단기 모멘텀·이벤트 드리븐 이슈 (실적 발표, 중앙은행 회의 등)
- 1m(1개월): 최근 누적된 섹터 방향성, 단기 자금 흐름
- 3m(3개월): 분기 실적 사이클, 정책 변화(금리·규제)의 중기 파급
- 6m(6개월): 구조적 수급 변화(공급망 재편, 산업 사이클)
- 1y(1년): 거시 레짐 변화(금리 사이클 전환, 지정학 구조 변화, 기술 패러다임 전환)

각 아이디어는 근거 없이 생성하지 말고, 입력된 지역/섹터 정보에 실제로 기반해야 합니다.
각 호라이즌 2~5개 아이디어로 제한하세요 (과다 생성 금지).
반드시 아래 JSON 스키마로만 응답하고 다른 설명은 절대 추가하지 마세요.

{
  "horizons": {
    "1w": [
      {
        "theme": "테마명 (한국어)",
        "sectors": ["Technology"],
        "tickers": ["QQQ", "NVDA"],
        "rationale": "근거 설명",
        "risk": "리스크 요인",
        "conviction": "medium"
      }
    ],
    "1m": [], "3m": [], "6m": [], "1y": []
  }
}
conviction은 high/medium/low 중 하나."""


def _build_user_prompt(us: dict, asia: dict, europe: dict, sectors: dict) -> str:
    parts = [
        f"[미국]\n{us.get('summary', '')}",
        f"[아시아]\n{asia.get('summary', '')}\n공통테마: {asia.get('cross_country_themes', [])}",
        f"[유럽]\n{europe.get('summary', '')}",
        "[섹터 매핑]\n" + "\n".join(
            f"- {s.get('name')}: {s.get('direction')} (score={s.get('score')}) — {s.get('rationale')} "
            f"[관련티커: {s.get('related_tickers', [])}]"
            for s in sectors.get("sectors", [])
        ),
    ]
    if sectors.get("conflicting_signals"):
        parts.append("[상충 신호]\n" + "\n".join(
            f"- {c.get('sector')}: {c.get('note')}" for c in sectors["conflicting_signals"]
        ))
    return "종합 입력 자료:\n\n" + "\n\n".join(parts)


def generate_ideas(dry_run: bool = False) -> dict | None:
    today = today_kst()
    us = load_cache("us_market.json")
    asia = load_cache("asia_market.json")
    europe = load_cache("europe_market.json")
    sectors = load_cache("sector_mapping.json")

    if not (us and asia and europe and sectors):
        print("[orchestrator] 선행 캐시 미완비 — 지역 에이전트/섹터매퍼를 먼저 실행하세요", file=sys.stderr)
        return None

    result: dict = {"date": today, "horizons": {h: [] for h in HORIZONS}}

    if dry_run:
        save_cache("investment_ideas.json", result)
        return result

    parsed = call_gemini_json(
        SYSTEM_PROMPT, _build_user_prompt(us, asia, europe, sectors),
        model=MODEL_HEAVY,
    )
    if not parsed:
        print("[orchestrator] Gemini 호출 실패 — 기존 investment_ideas.json 유지", file=sys.stderr)
        existing = load_cache("investment_ideas.json")
        return existing

    horizons = parsed.get("horizons", {})
    for h in HORIZONS:
        result["horizons"][h] = horizons.get(h, [])

    save_cache("investment_ideas.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Gemini 호출 없이 입력 캐시 검증만")
    args = parser.parse_args()

    today = today_kst()
    if not args.dry_run and cache_fresh("investment_ideas.json", today):
        print("[orchestrator] 당일 캐시 존재 — 재실행 생략")
        return load_cache("investment_ideas.json")

    result = generate_ideas(dry_run=args.dry_run)
    if result:
        counts = {h: len(v) for h, v in result["horizons"].items()}
        print(f"[orchestrator] 호라이즌별 아이디어 수: {counts}")
    return result


if __name__ == "__main__":
    main()
