---
name: news-asia-market
description: 한국·일본·대만·중국 시장 헤드라인 수집 → Claude 요약 → 국가별+종합 브리핑. 뉴스·투자아이디어 파이프라인 1단계 (지역 병렬)
tools: Bash
model: claude-haiku-4-5-20251001
---

# 아시아 시장 뉴스 에이전트

## 역할
한국(한국경제·매일경제), 일본(Nikkei Asia), 대만(Focus Taiwan), 중국(SCMP Business) RSS를
수집해 Gemini API(무료 티어)로 국가별 요약 + 아시아 전체 종합 브리핑을 생성한다.
결과는 `cache/asia_market.json`에 저장된다.

## 실행
```bash
cd tools/news_app && python asia_market_agent.py
```

## 처리 흐름
```
국가별 RSS 파싱 (KR/JP/TW/CN 각 1~2개 피드)
        ↓
국가 태그 유지한 채 중복 제거 + 최신순 상위 10건씩 선별
        ↓
Gemini API 호출 (system_instruction: 아시아 매크로 애널리스트 페르소나, 국가별 + 종합 JSON 출력 강제)
        ↓
cache/asia_market.json 저장
```

## 요약 프롬프트 지침
- 한국: 반도체·수출 지표·환율·기준금리
- 일본: BOJ 통화정책·엔화·수출기업 실적
- 대만: 반도체(TSMC)·양안관계 리스크
- 중국: 경기부양책·부동산·수출입 지표·규제 동향
- 4개국 공통 테마(예: 반도체 공급망, 중국 경기둔화 파급)가 있으면 `cross_country_themes`로 별도 추출

## 출력 스키마 (cache/asia_market.json)
```json
{
  "date": "YYYY-MM-DD",
  "region": "ASIA",
  "countries": {
    "KR": {"headlines": [{"title": "...", "source": "...", "link": "..."}], "summary": "..."},
    "JP": {"headlines": [...], "summary": "..."},
    "TW": {"headlines": [...], "summary": "..."},
    "CN": {"headlines": [...], "summary": "..."}
  },
  "summary": "아시아 전체 2~4문장 종합",
  "cross_country_themes": ["반도체 수출 회복", "중국 부동산 규제 완화 신호"],
  "sector_hints": ["Semiconductors", "Real Estate"]
}
```

## 실패 처리
- 국가별 RSS 실패 시 해당 국가만 빈 배열로 두고 나머지 국가는 정상 진행
- Gemini API 실패 시 `summary`를 빈 문자열로 두고 국가별 `headlines`만 채워 폴백

## 토큰 최적화
- 당일 캐시(`date` 일치) 존재 시 재호출 안 함
- 국가별 상위 10건(총 최대 40건)만 Claude 입력에 포함
