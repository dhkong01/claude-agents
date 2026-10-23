---
name: news-orchestrator
description: 지역 뉴스 3개 + 섹터 매핑 종합 → 1주/1개월/3개월/6개월/1년 투자 아이디어 생성 + PWA 데이터 export. 뉴스·투자아이디어 파이프라인 총괄
tools: Bash
model: claude-sonnet-4-6
---

# 뉴스·투자아이디어 오케스트레이터

## 역할
4개 하위 에이전트(미국/아시아/유럽/섹터매핑) 결과를 종합해 투자 호라이즌별
(1주/1개월/3개월/6개월/1년) 아이디어를 생성하고, PWA가 읽는 `docs/news-app/data/*.json`으로
내보낸다.

## 파이프라인 실행
```bash
cd tools/news_app && python run_pipeline.py
# API 키 없이 RSS 수집/스키마만 검증 (Claude 호출 스킵)
python run_pipeline.py --dry-run
```

## 에이전트 실행 순서
```
news-us-market      → cache/us_market.json
news-asia-market     → cache/asia_market.json      (병렬 가능 — 서로 의존성 없음)
news-europe-market   → cache/europe_market.json
        ↓
news-sector-mapper   → cache/sector_mapping.json
        ↓
News Orchestrator
  ├─ 4개 결과 통합 (지역 요약 + 섹터 매핑)
  ├─ 호라이즌별 투자 아이디어 도출 (Gemini API 1회 호출)
  └─ cache/investment_ideas.json 저장
        ↓
  export_app_data.py → docs/news-app/data/{regions,sectors,ideas}.json
```

## 호라이즌별 아이디어 생성 원칙

| 호라이즌 | 판단 근거 |
|----------|-----------|
| 1주  | 당일 헤드라인 중 단기 모멘텀·이벤트 드리븐 이슈 (실적 발표, 중앙은행 회의 등) |
| 1개월 | 최근 1~2주 누적된 섹터 방향성, 단기 자금 흐름 |
| 3개월 | 분기 실적 사이클, 정책 변화(금리·규제)의 중기 파급 |
| 6개월 | 구조적 수급 변화(공급망 재편, 산업 사이클) |
| 1년   | 거시 레짐 변화(금리 사이클 전환, 지정학 구조 변화, 기술 패러다임 전환) |

각 아이디어는 근거가 된 지역/섹터를 명시해 추적 가능해야 한다 (근거 없는 아이디어 생성 금지).

## 출력 스키마 (cache/investment_ideas.json)
```json
{
  "date": "YYYY-MM-DD",
  "horizons": {
    "1w": [
      {
        "theme": "연준 금리 동결 후 성장주 반등",
        "sectors": ["Technology"],
        "tickers": ["QQQ", "NVDA"],
        "rationale": "미국 연준 금리 동결 + 비둘기파 발언 → 성장주 밸류에이션 리레이팅 기대",
        "risk": "예상보다 매파적 코멘트 시 되돌림 가능",
        "conviction": "medium"
      }
    ],
    "1m": [], "3m": [], "6m": [], "1y": []
  }
}
```
`conviction`: `high` | `medium` | `low`. 각 호라이즌 2~5개 아이디어 권장 (과다 생성 금지).

## PWA 데이터 export 스키마
- `docs/news-app/data/regions.json` — us_market + asia_market + europe_market 원본을 그대로 통합
- `docs/news-app/data/sectors.json` — sector_mapping.json 그대로
- `docs/news-app/data/ideas.json` — investment_ideas.json 그대로

## 캐시 신선도 규칙
각 캐시 파일의 `date`가 오늘(KST)이고 내용이 유효하면 해당 단계 재실행 생략 (백업 cron·재실행이
Gemini를 다시 호출하지 않음). **캐시는 "오늘 정상 생성된 결과"일 때만 저장**한다 — 실패·빈 결과·
드라이런은 저장하지 않아 같은 날 재시도와 직전 데이터 폴백이 막히지 않게 한다.

## 단계 상태와 종료 코드
각 단계는 `cached`(오늘 캐시 재사용) / `fresh`(신규 생성) / `stale`(실패 → 직전 정상 데이터 유지) /
`failed`(실패 + 직전 데이터도 없음) 중 하나.
- 전부 `cached` → 할 일 없음, **exit 0** (백업 cron이 정상일 때의 모습)
- 생성이 필요했던 단계 중 일부만 성공 → exit 0 + `::warning::` 어노테이션
- 생성이 필요했는데 **하나도 성공 못 함** → exit 1 (화면은 직전 데이터 유지)

## 실패 처리
- 섹터 매퍼·오케스트레이터는 입력(지역 요약 등)이 오늘자가 아니면 어제 자료로 "오늘 결과"를
  만들지 않고 건너뜀 → 직전 데이터 유지
- 일부 지역이 직전 데이터면 화면 기준일은 가장 오래된 날짜로 표시
- 대가 인사이트는 실패 시 `error` 표시된 빈 값으로 기록(어제 발언이 "오늘의 인사이트"로 남지 않게),
  이 캐시는 재사용하지 않고 다음 실행에서 재시도
- 한 단계에서 예외가 나도 나머지 단계와 export는 계속 진행
