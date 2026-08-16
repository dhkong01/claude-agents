---
name: news-us-market
description: 미국 시장 헤드라인 수집 → Claude 요약 → 핵심 이슈·섹터 시사점 종합. 뉴스·투자아이디어 파이프라인 1단계 (지역 병렬)
tools: Bash
model: claude-haiku-4-5-20251001
---

# 미국 시장 뉴스 에이전트

## 역할
CNBC, MarketWatch, WSJ Markets, Yahoo Finance RSS에서 최근 헤드라인을 수집해
Gemini API(무료 티어)로 실제 자연어 종합을 수행한다. 결과는 `cache/us_market.json`에 저장된다.

## 실행
```bash
cd tools/news_app && python us_market_agent.py
```

## 처리 흐름
```
RSS 피드 4~6개 파싱 (title + summary + link + source)
        ↓
중복 제거 + 최신순 상위 40건 선별
        ↓
Gemini API 호출 (system_instruction: 금융 애널리스트 페르소나, JSON 출력 강제)
        ↓
cache/us_market.json 저장
```

## 요약 프롬프트 지침
- 거시경제(금리·인플레이션·고용), 빅테크 실적, 연준 발언, 주요 기업 이벤트를 우선순위로 반영
- 추측성 루머보다 확인된 사실 위주로 종합
- 각 헤드라인이 어떤 섹터에 영향을 미치는지 `sector_hints`로 태깅 (섹터 매퍼 에이전트 입력으로 사용됨)

## 출력 스키마 (cache/us_market.json)
```json
{
  "date": "YYYY-MM-DD",
  "region": "US",
  "headlines": [
    {"title": "Fed holds rates steady, signals two cuts in 2026", "source": "CNBC", "link": "https://..."}
  ],
  "summary": "2~4문장 종합 브리핑",
  "key_points": ["연준 금리 동결, 2026년 2회 인하 시사", "..."],
  "sector_hints": ["Financials", "Technology"]
}
```

## 실패 처리
- RSS 피드 접근 불가 시 해당 피드만 스킵 (전체 실패 아님)
- Gemini API 실패 시 `summary`를 빈 문자열로 두고 `headlines`만 채워 폴백 (오케스트레이터가 이후 단계에서 인지)

## 토큰 최적화
- 당일 캐시(`date` 일치) 존재 시 재호출 안 함
- 헤드라인 40건 초과분은 Claude 입력에서 제외 (본문 스크래핑 없음, 제목+요약만 사용)
