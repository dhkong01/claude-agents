#!/usr/bin/env python3
"""
strategy_gates.py - KONG 전략 적합성 게이트 (T1~T6) 업데이트
파단 해석 보고서 SEC 08 기반 — 매일 자동 실행, T3(금리)만 자동 갱신
나머지(T1/T2/T4/T5/T6)는 실적시즌·분기마다 수동 업데이트
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

DOCS_DATA = Path(__file__).parent.parent.parent / 'docs' / 'data'
GATES_JSON = DOCS_DATA / 'strategy_gates.json'
KST = timezone(timedelta(hours=9))

GATE_DEFS = [
    {
        "id": "T1", "critical": True,
        "name": "M7 캐펙스 가이던스 YoY",
        "desc": "AMZN·MSFT·GOOGL·META 합산 가이던스 YoY < +15%",
        "threshold": "< +15%",
    },
    {
        "id": "T2", "critical": True,
        "name": "IG 테크 크레딧 스프레드",
        "desc": "+50bp 이상 확대 (3개월 이내)",
        "threshold": "+50bp↑",
    },
    {
        "id": "T3", "critical": False,
        "name": "연준 기준금리",
        "desc": "기준금리 4.25% 초과 또는 연속 2회 인상",
        "threshold": "≥ 4.25%",
    },
    {
        "id": "T4", "critical": False,
        "name": "HBM ASP 인상률",
        "desc": "HBM 연간 계약 ASP 인상률 한 자릿수 or 동결 전환",
        "threshold": "한 자릿수/동결",
    },
    {
        "id": "T5", "critical": False,
        "name": "D램 재고 주수",
        "desc": "D램 재고 8주 이상 반등 또는 이중발주 취소 뉴스",
        "threshold": "8주↑ 또는 취소",
    },
    {
        "id": "T6", "critical": False,
        "name": "M7 EPS 미스 (D&A급증)",
        "desc": "M7 1사 이상 D&A/영업이익 급증으로 EPS 미스",
        "threshold": "1사↑ EPS미스",
    },
]

# 초기값 — 최초 실행 또는 JSON 없을 때 기본값
DEFAULT_STATE = {
    "T1": {"status": False, "value": "+77%",
           "note": "2026 가이던스 +77% (2027E 컨센서스 +38~50%) — 임계 미달",
           "auto": False, "updated": "2026-07-12"},
    "T2": {"status": False, "value": "정상",
           "note": "IG 테크 크레딧 스프레드 정상 범위 — BofA/ICE 지수 미확대",
           "auto": False, "updated": "2026-07-12"},
    "T3": {"status": False, "value": "3.50~3.75%",
           "note": "연준 기준금리 3.50~3.75% — 임계(4.25%) 미달 (자동갱신)",
           "auto": True, "updated": "2026-07-12"},
    "T4": {"status": False, "value": "두 자릿수",
           "note": "HBM ASP 두 자릿수 인상 유지 — 2027 협상 진행 중 (생산자 우위)",
           "auto": False, "updated": "2026-07-12"},
    "T5": {"status": False, "value": "정상",
           "note": "D램 재고 정상 범위 — 이중발주 취소 뉴스 없음",
           "auto": False, "updated": "2026-07-12"},
    "T6": {"status": False, "value": "양호",
           "note": "최근 M7 실적 양호 — 감가상각 파도 2027년부터 예상",
           "auto": False, "updated": "2026-07-12"},
}


def load_existing_state() -> dict:
    """기존 JSON에서 게이트 상태 로드 (비-자동 게이트 수동 값 보존)"""
    if not GATES_JSON.exists():
        return {}
    try:
        existing = json.loads(GATES_JSON.read_text(encoding='utf-8'))
        return {
            g['id']: {
                'status': g.get('status', False),
                'value': g.get('value', '?'),
                'note': g.get('note', ''),
                'auto': g.get('auto', False),
                'updated': g.get('updated', ''),
            }
            for g in existing.get('gates', [])
        }
    except Exception as e:
        print(f'[strategy_gates] 기존 JSON 로드 실패: {e}')
        return {}


def auto_update_t3(state: dict) -> None:
    """T3: ^IRX (13주 T-bill 연율)로 연준 금리 근사치 자동 갱신"""
    try:
        import yfinance as yf
        irx = yf.Ticker('^IRX').history(period='5d')['Close'].dropna()
        if irx.empty:
            print('[T3] ^IRX 데이터 없음 — 기존 값 유지')
            return
        rate = float(irx.iloc[-1])
        triggered = rate >= 4.25
        margin = 4.25 - rate
        note = (
            f'단기금리(^IRX) {rate:.2f}% — ⚠️ 임계 도달 ({rate:.2f}% ≥ 4.25%)'
            if triggered else
            f'단기금리(^IRX) {rate:.2f}% — 목표(4.25%)까지 {margin:.2f}%p 여유'
        )
        state['T3'] = {
            'status': triggered,
            'value': f'{rate:.2f}%',
            'note': note,
            'auto': True,
            'updated': datetime.now(KST).strftime('%Y-%m-%d'),
        }
        print(f'[T3] ^IRX={rate:.2f}% → {"TRIGGERED ⚠️" if triggered else "SAFE ✓"}')
    except Exception as e:
        print(f'[T3] 자동 갱신 실패: {e} — 기존 값 유지')


def compute_action(lit: int, t1_on: bool, t2_on: bool) -> tuple:
    if t1_on and t2_on:
        return '🚨 즉시 방어 전환 (T1+T2 동시 점등)', 4
    if lit >= 3:
        return '🔴 M게이트 OFF — 반도체 익스포저 단계 축소', 3
    if lit >= 2:
        return '🟠 신규 진입 중지 / S4–S5 사이즈 금지', 2
    if lit >= 1:
        return '🟡 모니터링 강화 — 추가 점등 대비', 1
    return '🟢 정상 운용', 0


def build_output(state: dict) -> dict:
    today = datetime.now(KST).strftime('%Y-%m-%d')
    gates_out = []
    for defn in GATE_DEFS:
        gid = defn['id']
        s = state.get(gid, DEFAULT_STATE.get(gid, {}))
        gates_out.append({
            **defn,
            'status': s.get('status', False),
            'value': s.get('value', '?'),
            'note': s.get('note', ''),
            'auto': s.get('auto', False),
            'updated': s.get('updated', today),
        })

    lit = sum(1 for g in gates_out if g['status'])
    t1_on = next((g['status'] for g in gates_out if g['id'] == 'T1'), False)
    t2_on = next((g['status'] for g in gates_out if g['id'] == 'T2'), False)
    action, level = compute_action(lit, t1_on, t2_on)

    return {
        'updated': today,
        'gates': gates_out,
        'lit_count': lit,
        'action_level': level,
        'action': action,
        'rule': '2개↑: 신규 진입 중지 | 3개↑: M게이트 OFF | T1+T2 동시: 즉시 방어 전환',
    }


def run() -> dict:
    DOCS_DATA.mkdir(parents=True, exist_ok=True)

    state = load_existing_state()
    if not state:
        state = {k: dict(v) for k, v in DEFAULT_STATE.items()}

    auto_update_t3(state)

    result = build_output(state)
    GATES_JSON.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    print(f'[strategy_gates] 저장 완료 → 점등 {result["lit_count"]}/6 — {result["action"]}')
    return result


if __name__ == '__main__':
    run()
