---
name: news-europe-market
description: 유럽 주요 이슈 헤드라인 수집 → Claude 요약 → 핵심 이슈·섹터 시사점 종합. 뉴스·투자아이디어 파이프라인 1단계 (지역 병렬)
tools: Bash
model: claude-haiku-4-5-20251001
---

# 유럽 뉴스 에이전트

## 역할
BBC Business, Euronews Business, DW Business, Politico Europe RSS에서 헤드라인을 수집해
Gemini API(무료 티어)로 실제 자연어 종합을 수행한다. 결과는 `cache/europe_market.json`에 저장된다.

## 실행
```bash
cd tools/news_app && python europe_market_agent.py
```

## 처리 흐름
```
RSS 피드 4~5개 파싱 (title + summary + link + source)
        ↓
중복 제거 + 최신순 상위 40건 선별
        ↓
Gemini API 호출 (system_instruction: 유럽 매크로 애널리스트 페르소나, JSON 출력 강제)
        ↓
cache/europe_market.json 저장
```

## 요약 프롬프트 지침
- 목표는 "오늘 유럽에 무슨 트렌드가 있었는지"를 매일 다르게 짚어내는 것 — 상투적이고 매일
  비슷한 서두 금지, 가장 두드러지는 흐름부터 바로 짚기
- ECB 통화정책·유로존 인플레이션·독일/프랑스 경기지표를 우선순위로 반영
- EU 규제(반독점·AI법·관세)가 특정 섹터(빅테크·자동차·에너지)에 미치는 영향 명시
- 우크라이나 전쟁·에너지 수급 등 지정학 이슈는 Energy/Defense 섹터 시사점 위주로 요약 (지정학 리스크
  자체의 세부 스코어링은 기존 `trend-geo-risk` 에이전트 영역이므로 중복하지 않음)

## 출력 스키마 (cache/europe_market.json)
```json
{
  "date": "YYYY-MM-DD",
  "region": "EUROPE",
  "headlines": [
    {"title": "ECB holds rates, flags energy price risks", "source": "Euronews", "link": "https://..."}
  ],
  "trend_headline": "오늘의 핵심 트렌드 한 문장 (PWA에서 강조 배지로 표시)",
  "summary": "2~3문장 — 트렌드 중심 브리핑",
  "key_points": ["ECB 금리 동결, 에너지 가격 리스크 경고", "..."],
  "sector_hints": ["Energy", "Financials"]
}
```

## 실패 처리
- RSS 피드 접근 불가 시 해당 피드만 스킵 (전체 실패 아님)
- Gemini API 실패 시 `summary`를 빈 문자열로 두고 `headlines`만 채워 폴백

## 토큰 최적화
- 당일 캐시(`date` 일치) 존재 시 재호출 안 함
- 헤드라인 40건 초과분은 Claude 입력에서 제외 (본문 스크래핑 없음, 제목+요약만 사용)
