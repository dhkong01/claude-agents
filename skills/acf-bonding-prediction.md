---
name: acf-bonding-prediction
description: ACF 본딩 공정 저항 예측 프로젝트 워크플로우. acf-orchestrator를 통해 논문 리서치 → Monte Carlo 시뮬레이션 → FEM 서로게이트 → 저항 예측의 4단계 파이프라인을 실행한다.
---

# ACF Bonding Process Prediction

## When to Use
- ACF 본딩 공정 파라미터(온도/압력/시간)에 대한 접촉 저항 예측
- 공정 최적화를 위한 파라미터 스윕
- 새로운 기판/범프 구조에 대한 초기 저항 추정

## Agent Team

```
acf-orchestrator (메인)
├── acf-paper-researcher  → 문헌 파라미터 추출
├── acf-monte-carlo       → 입자 포획 통계
└── acf-fem-surrogate     → 접촉 역학 예측
```

## How to Invoke

```
Agent(
  subagent_type="acf-orchestrator",
  prompt="""
  ACF 본딩 저항을 예측해주세요.

  기판: glass (COG)
  범프: pitch=50μm, diameter=30μm, height=15μm
  ACF: 표준 상업용 (Hitachi AC-7206U 계열)
  공정 조건: T=180°C, P=2.0MPa, t=10s
  """
)
```

## Pipeline Steps

| 단계 | 에이전트 | 입력 | 출력 |
|------|---------|------|------|
| 1 | acf-paper-researcher | 공정 스펙 | 재료 물성, 보정 데이터 |
| 2 | acf-monte-carlo | 재료 물성 | 입자 포획 통계 (N_eff, A_contact) |
| 3 | acf-fem-surrogate | 입자 통계 | 접촉 반경, 변형, 응력 (R²>0.95) |
| 4 | acf-orchestrator | 전체 결과 | R_total ± 불확실도 |

## Resistance Model

```
R_contact  = ρ_c / (2·a)           [Holm constriction, per particle]
R_parallel = R_contact / N_eff     [N_eff particles in parallel]
R_spread   = ρ_metal / (2·√(π·A_bump))
R_bump     = R_parallel + R_spread
```

## Quality Gates

모든 게이트 통과 시에만 결과 출력:
- [ ] 문헌 주요값 ≥ 2개 독립 출처
- [ ] Monte Carlo 수렴 (CV < 5%, N ≥ 1,000)
- [ ] FEM 서로게이트 R² > 0.95
- [ ] 예측값이 보정 데이터 대비 ±20% 이내

## Example Output

```yaml
R_total_bump_Ohm:
  mean: 0.048
  std:  0.006
  ci_95_lower: 0.036
  ci_95_upper: 0.060
validation:
  literature_benchmark_Ohm: 0.045
  prediction_error_pct: 6.7
  quality_gates_passed: true
```

## Parameter Sweep Usage

```python
conditions = [
  {"T": 170, "P": 1.5, "t": 10},
  {"T": 180, "P": 2.0, "t": 10},
  {"T": 190, "P": 2.5, "t": 8},
]
# acf-orchestrator를 각 조건으로 순차 호출 후 결과 비교표 생성
```
