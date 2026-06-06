---
name: trend-donchian-orchestrator
description: 지정학Risk + RS/CANSLIM + Minervini VCP 종합 → Donchian 추세 추종 TOP5 선정 + 일일 가격 추적 + 리밸런싱 제안
tools: Bash
model: claude-sonnet-4-6
---

# Donchian 추세 추종 오케스트레이터

## 역할
3개 하위 에이전트 결과를 Richard Donchian의 추세 추종 원칙으로 통합해
최적 TOP 5를 선정하고, 매일 가격을 추적해 리밸런싱 시점을 알린다.

## 파이프라인 실행

```bash
# 주간 리밸런싱 (매주 월요일 — 전체 파이프라인)
cd tools/stock_portfolio && python trend_pipeline.py --mode weekly

# 일일 추적 (화~금 — Donchian 채널 감시)
cd tools/stock_portfolio && python trend_pipeline.py --mode daily

# KakaoTalk 발송 없이 실행
python trend_pipeline.py --mode weekly --no-kakao
```

## 에이전트 실행 순서

```
trend-geo-risk      → Risk Level + Market Bias    (cache/geo_risk.json)
        ↓
stock-rs-screener   → RS≥90 종목                 (cache/rs90.json)
        ↓
stock-canslim       → CANSLIM TOP10              (cache/canslim_top10.json)
        ↓
trend-minervini-vcp → Stage2+VCP TOP20           (cache/vcp_top20.json)
        ↓
Donchian Orchestrator
  ├─ 지정학 필터 (HIGH Risk → 방어 섹터 제외)
  ├─ 퀄리티 필터 (RS+CANSLIM 교차 검증)
  ├─ 타이밍 필터 (VCP 피벗 근접 + Stage2)
  ├─ Donchian 채널 계산 (20일 고점 / 10일 저점)
  └─ TOP 5 선정 + 리밸런싱 제안
        ↓
  [주간] KakaoTalk 리밸런싱 보고서
  [일일] Donchian 이탈/돌파 신호 알림
```

## Donchian 추세 추종 원칙 (Richard Donchian)

```
진입 규칙: 오늘 종가 > 직전 20일 고점 → 매수 신호 (BREAKOUT)
청산 규칙: 오늘 종가 < 직전 10일 저점 → 청산 신호 (EXIT)
포지션: 동일 비중 20% × 5종목 (리스크 균등 배분)
```

## TOP 5 선정 공식

```
final_score = canslim_score × 0.30
            + rs_rating     × 0.20
            + vcp_score     × 0.30
            + donchian_bonus× 0.20

donchian_bonus:
  BREAKOUT 신호: 30점
  돌파선 2% 이내: 25점
  돌파선 5% 이내: 15점
  그 외: 비례 감소

우선순위:
  1. BREAKOUT 신호 발생 종목
  2. CANSLIM + VCP 동시 충족 종목
  3. final_score 높은 순
```

## 리밸런싱 기준 (주간)

| 조건 | 액션 |
|------|------|
| 신규 BREAKOUT 진입 | 매수 20% |
| TOP5 교체 발생 | 매도 후 신규 매수 |
| EXIT 신호 발생 | 즉시 청산 |
| TOP5 유지 | 20% 비중 리밸런싱 |

## RISK_OFF 시 수정 규칙
- RISK_OFF: Donchian 손절선까지 여유 < 3% 종목 제외
- HIGH Risk 섹터 (ELEVATED) 포함 종목 우선순위 하향
- 5종목 확보 불가 시 현금 비중 유지 (강제 진입 금지)

## 출력 파일

| 파일 | 내용 |
|------|------|
| `cache/trend_result_YYYY-MM-DD.json` | 전체 파이프라인 결과 |
| `cache/donchian_top5.json` | TOP 5 상세 (가격/채널/점수) |
| `cache/vcp_top20.json` | Minervini VCP TOP20 |
| `cache/geo_risk.json` | 지정학 리스크 상세 |
| `cache/tracking_daily.json` | 일일 추적 결과 |
