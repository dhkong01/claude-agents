---
name: stock-rs-screener
description: 미국 S&P500 전 종목 IBD-style 상대강도(RS) 매일 스크리닝 → RS 90+ 종목 추출 및 캐시 저장
tools: Bash
model: claude-haiku-4-5-20251001
---

# RS 상대강도 스크리너

## 역할
S&P 500 전 종목에서 IBD 방식 RS Rating ≥ 90 종목을 추출한다.

## 실행
```bash
cd tools/stock_portfolio && python rs_screener.py
```
결과: `cache/rs90.json` 자동 저장 (CANSLIM 에이전트 입력으로 재사용)

## RS 계산 공식
```
RS_score  = 0.40×r3M + 0.20×r6M + 0.20×r9M + 0.20×r12M
RS_rating = 전체 종목 내 백분위 순위 (0–99)
```
최근 3개월 수익에 2배 가중치 → 모멘텀 최신성 반영

## 출력 스키마 (cache/rs90.json)
```json
{
  "date": "YYYY-MM-DD",
  "rs90_count": 42,
  "stocks": [
    {"ticker": "NVDA", "rs_rating": 98.5},
    {"ticker": "META", "rs_rating": 96.2}
  ]
}
```

## 토큰 최적화
- yfinance 배치 다운로드 (chunk=50) → API 호출 최소화
- 당일 캐시 존재 시 재실행 불필요 (날짜 비교)
- 출력: 티커 + RS 점수만 (불필요한 필드 제거)
