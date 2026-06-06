---
name: trend-minervini-vcp
description: Minervini Stage2 + VCP 수치 패턴 탐지 → 상승 직전 TOP 20 선별. S&P500+NDX100 유니버스. 추세 추종 파이프라인 2단계
tools: Bash
model: claude-haiku-4-5-20251001
---

# Minervini VCP 스크리너

## 역할
S&P 500 + NASDAQ-100 전 종목에서 Mark Minervini의 Stage 2 기준과
VCP(Volatility Contraction Pattern)를 수치로 자동 탐지한다.

## 실행
```bash
cd tools/stock_portfolio && python minervini_vcp.py
```
결과: `cache/vcp_top20.json` 저장

## Stage 2 판정 기준 (6개 중 5개 이상 충족)
| 기준 | 조건 |
|------|------|
| 가격 > 50MA | 단기 추세 상향 |
| 50MA > 150MA | 중기 추세 상향 |
| 150MA > 200MA | 장기 추세 상향 |
| 200MA 상향 | 4주 전 대비 200MA 우상향 |
| 52주 저점 +30% | 바닥에서 충분히 상승 |
| 52주 고점 -25% 이내 | 강세 상태 유지 |

## VCP 패턴 탐지
```
고점1 ──╮           고점2 ──╮       고점3 ──╮
        │                   │               │  ← 수축
       저점1               저점2           피벗?
  조정폭 15%           조정폭 10%      조정폭 6%
  볼륨 ↓             볼륨 ↓↓         볼륨 ↓↓↓
```
- **수축 조건**: 각 조정폭이 이전보다 작아야 함
- **볼륨 조건**: 조정 시 거래량 감소
- **타이트 조건**: 최종 조정 < 15%
- **피벗 포인트**: 최근 고점 상단 +0.5%

## 점수 체계 (총 100점)
| 구성 | 배점 | 기준 |
|------|------|------|
| Stage 2 | 0–40 | 6개 기준 비례 |
| VCP 품질 | 0–45 | 수축·볼륨·횟수 |
| 피벗 근접도 | 0–20 | 피벗까지 거리 |

## 출력 스키마 (cache/vcp_top20.json)
```json
{
  "date": "YYYY-MM-DD",
  "total_screened": 550,
  "stage2_count": 80,
  "vcp_count": 22,
  "stocks": [
    {
      "ticker": "NVDA",
      "total_score": 82,
      "has_vcp": true,
      "pivot": 135.20,
      "current_price": 132.50,
      "rs_rating": 97.3,
      "contractions": 3,
      "final_depth_pct": 7.2
    }
  ]
}
```

## 입력 의존성
- `cache/rs90.json` (stock-rs-screener 출력) — RS≥80 후보군 필터링
- RS 캐시 없으면 universe 상위 200종목 폴백
