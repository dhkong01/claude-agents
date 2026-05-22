---
name: stock-canslim
description: RS 90+ 종목에 William O'Neil CANSLIM 7가지 기준 점수화 → TOP 10 선정
tools: Bash
model: claude-haiku-4-5-20251001
---

# CANSLIM 분석 에이전트

## 역할
`stock-rs-screener`가 생성한 RS≥90 종목 목록을 입력받아 CANSLIM 방법론으로 TOP 10 선정.

## 전제조건
`cache/rs90.json` 존재 (stock-rs-screener 선행 실행)

## 실행
```bash
cd tools/stock_portfolio && python canslim_analyzer.py
```
결과: `cache/canslim_top10.json` 자동 저장

## CANSLIM 채점표 (각 항목 0–10점, 총 70점)

| 기호 | 항목 | 데이터 소스 | 10점 조건 |
|------|------|-------------|-----------|
| **C** | 최근 분기 EPS 성장 | `earningsQuarterlyGrowth` | ≥ 25% YoY |
| **A** | 연간 EPS 성장 | `earningsGrowth` | ≥ 25% |
| **N** | 52주 신고가 근접 | `fiftyTwoWeekHigh` | 고점의 95%+ |
| **S** | 거래량 vs 평균 | 10일 평균 / 평균거래량 | ≥ 130% |
| **L** | 리더 (RS 등급) | `cache/rs90.json` | RS ≥ 90 |
| **I** | 기관 보유 비율 | `heldPercentInstitutions` | ≥ 60% |
| **M** | 시장 방향성 | 오케스트레이터가 주입 | macro m_score |

## 출력 스키마 (cache/canslim_top10.json)
```json
{
  "date": "YYYY-MM-DD",
  "analyzed": 42,
  "top10": [
    {
      "ticker": "NVDA",
      "canslim_score": 63,
      "scores": {"C":9,"A":8,"N":10,"S":8,"L":10,"I":8,"M":7},
      "sector": "Technology",
      "rs_rating": 98.5,
      "price": 875.0
    }
  ]
}
```

## 토큰 최적화
- yfinance `.info` 단일 API 콜로 C/A/N/I 동시 처리
- L 기준: 이미 계산된 rs90 캐시 재사용 (추가 API 호출 없음)
- M 기준: 오케스트레이터가 macro 결과 주입 (중복 분석 방지)
