#!/usr/bin/env python3
"""
strategy_gates.py - KONG Gate T1~T6 전체 자동갱신
파단 해석 보고서 SEC 08 기반 -- 매일 자동 실행 (trend_rebalancing.yml)

T1: M7 4사 연간 캐펙스 YoY < +15% (yfinance annual cashflow)
T2: ICE BofA IG OAS 3개월 변화 +50bp (FRED 공개 CSV)
T3: ^IRX 단기금리 >= 4.25%
T4: MU 그로스마진 proxy (HBM ASP 대리 지표)
T5: MU DIO YoY 변화 proxy (D램 재고 주수 대리 지표)
T6: M7 D&A/영업이익 비율 급증 여부
"""
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

DOCS_DATA = Path(__file__).parent.parent.parent / 'docs' / 'data'
GATES_JSON = DOCS_DATA / 'strategy_gates.json'
KST = timezone(timedelta(hours=9))

GATE_DEFS = [
    {
        "id": "T1", "critical": True,
        "name": "M7 캐펙스 YoY",
        "desc": "AMZN*MSFT*GOOGL*META 합산 연간 캐펙스 YoY < +15%",
        "threshold": "< +15%",
    },
    {
        "id": "T2", "critical": True,
        "name": "IG 크레딧 스프레드",
        "desc": "ICE BofA IG OAS 3개월 변화 +50bp 이상 (FRED BAMLC0A0CM)",
        "threshold": "+50bp 3M",
    },
    {
        "id": "T3", "critical": False,
        "name": "연준 기준금리",
        "desc": "^IRX(13주 T-bill) 4.25% 초과 -- 연준 기준금리 근사",
        "threshold": ">= 4.25%",
    },
    {
        "id": "T4", "critical": False,
        "name": "HBM ASP (MU GM 프록시)",
        "desc": "MU 그로스마진 < 40% 또는 YoY -10pp 이상 하락",
        "threshold": "GM<40% or -10pp YoY",
    },
    {
        "id": "T5", "critical": False,
        "name": "D램 재고 (MU DIO 프록시)",
        "desc": "MU 재고회전일수 YoY +28일(4주) 이상 증가",
        "threshold": "DIO +28일 YoY",
    },
    {
        "id": "T6", "critical": False,
        "name": "M7 D&A/영업이익 급증",
        "desc": "M7 1사 이상 D&A/영업이익 비율 YoY +20pp 이상 급증",
        "threshold": "1사 +20pp YoY",
    },
]

M7_TICKERS = ['AMZN', 'MSFT', 'GOOGL', 'META', 'AAPL', 'NVDA', 'TSLA']
M7_CAPEX   = ['AMZN', 'MSFT', 'GOOGL', 'META']


# ── 유틸 ──────────────────────────────────────────────────────────

def _safe(val, default=None):
    try:
        v = float(val)
        return None if (v != v) else v
    except Exception:
        return default

def _ttm(row, n=4):
    vals = [_safe(row.iloc[i]) for i in range(min(n, len(row)))]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None

def _find_row(df, keywords, require_all=False):
    """DataFrame 인덱스에서 키워드 매칭 행 탐색 (대소문자 무시)"""
    for idx in df.index:
        s = str(idx).lower()
        if require_all:
            if all(k in s for k in keywords):
                return df.loc[idx]
        else:
            if any(k in s for k in keywords):
                return df.loc[idx]
    return None

def _print(msg):
    """Windows cp949 환경에서도 안전한 출력"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


# ── T1: M7 4사 연간 캐펙스 YoY ───────────────────────────────────

def auto_update_t1(state: dict) -> None:
    """
    yfinance annual cashflow에서 캐펙스 추출.
    Guidance 아닌 실제 지출 기준 -- 당년/전년 비교.
    """
    import yfinance as yf
    today = datetime.now(KST).strftime('%Y-%m-%d')

    capex_keywords = ['capital expenditure', 'purchase of property', 'capex']
    ok, curr_total, prev_total = 0, 0.0, 0.0

    for t in M7_CAPEX:
        try:
            time.sleep(0.4)
            cf = yf.Ticker(t).cashflow  # 연간 (4년치)
            if cf is None or cf.empty or len(cf.columns) < 2:
                continue
            row = _find_row(cf, capex_keywords)
            if row is None:
                continue
            c = abs(_safe(row.iloc[0]) or 0)
            p = abs(_safe(row.iloc[1]) or 0)
            if c > 0 and p > 0:
                curr_total += c
                prev_total += p
                ok += 1
        except Exception as e:
            _print(f'[T1] {t}: {e}')

    if ok < 2 or prev_total == 0:
        _print(f'[T1] 데이터 부족 ({ok}/4사) -- 기존 유지')
        return

    yoy = (curr_total - prev_total) / prev_total * 100
    triggered = yoy < 15
    bn = curr_total / 1e9
    state['T1'] = {
        'status': triggered,
        'value': f'{yoy:+.0f}%',
        'note': (
            f'M7 4사 연간 캐펙스 합산 ${bn:.0f}B YoY {yoy:+.0f}%'
            f' -- {"WARNING: 임계 도달" if triggered else "정상 (임계 +15% 미달)"}'
            f' (실제 지출 기준, 가이던스 아님)'
        ),
        'auto': True,
        'updated': today,
    }
    _print(f'[T1] TTM ${bn:.0f}B YoY={yoy:+.0f}% -> {"TRIGGERED" if triggered else "SAFE"}')


# ── T2: FRED ICE BofA IG OAS ─────────────────────────────────────

def auto_update_t2(state: dict) -> None:
    """ICE BofA IG 회사채 OAS (BAMLC0A0CM) 3개월 변화. FRED 공개 CSV."""
    import requests
    today = datetime.now(KST).strftime('%Y-%m-%d')

    url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLC0A0CM'
    try:
        r = requests.get(url, timeout=25, headers={'User-Agent': 'portfolio-bot/1.0'})
        if r.status_code != 200:
            raise ValueError(f'HTTP {r.status_code}')

        rows = []
        for line in r.text.strip().split('\n'):
            if not line or line.startswith('DATE'):
                continue
            parts = line.split(',')
            if len(parts) == 2:
                try:
                    rows.append(float(parts[1].strip()))
                except Exception:
                    pass

        if len(rows) < 65:
            raise ValueError(f'데이터 부족: {len(rows)}행')

        cur = rows[-1]
        pre = rows[-63] if len(rows) >= 63 else rows[0]  # ~3개월 전
        delta_bp = (cur - pre) * 100  # OAS는 % 단위이므로 *100 = bp
        triggered = delta_bp >= 50

        state['T2'] = {
            'status': triggered,
            'value': f'{cur:.2f}% (d3M:{delta_bp:+.0f}bp)',
            'note': (
                f'ICE BofA IG OAS {cur:.2f}%'
                f' -- 3개월 변화 {delta_bp:+.0f}bp'
                f' {"WARNING: +50bp 임계 도달" if triggered else f"(여유 {50-delta_bp:.0f}bp)"}'
            ),
            'auto': True,
            'updated': today,
        }
        _print(f'[T2] BAMLC0A0CM={cur:.2f}% d3M={delta_bp:+.0f}bp -> {"TRIGGERED" if triggered else "SAFE"}')
    except Exception as e:
        _print(f'[T2] FRED 실패: {e} -- 기존 유지')


# ── T3: ^IRX 단기금리 ────────────────────────────────────────────

def auto_update_t3(state: dict) -> None:
    import yfinance as yf
    today = datetime.now(KST).strftime('%Y-%m-%d')
    try:
        irx = yf.Ticker('^IRX').history(period='5d')['Close'].dropna()
        if irx.empty:
            return
        rate = float(irx.iloc[-1])
        triggered = rate >= 4.25
        state['T3'] = {
            'status': triggered,
            'value': f'{rate:.2f}%',
            'note': (
                f'단기금리(^IRX) {rate:.2f}%'
                f' -- {"WARNING: 4.25% 임계 도달" if triggered else f"목표(4.25%)까지 {4.25-rate:.2f}pp 여유"}'
            ),
            'auto': True,
            'updated': today,
        }
        _print(f'[T3] ^IRX={rate:.2f}% -> {"TRIGGERED" if triggered else "SAFE"}')
    except Exception as e:
        _print(f'[T3] 실패: {e}')


# ── T4: MU 그로스마진 (HBM ASP 프록시) ──────────────────────────

def auto_update_t4(state: dict) -> None:
    """
    MU 그로스마진 이용. HBM ASP 하락 직접 지표 아님 -- 대리 지표.
    GM < 40% 또는 YoY -10pp 이상 하락 시 경고.
    """
    import yfinance as yf
    today = datetime.now(KST).strftime('%Y-%m-%d')
    try:
        time.sleep(0.4)
        fin = yf.Ticker('MU').quarterly_income_stmt
        if fin is None or fin.empty:
            # 구 API fallback
            fin = yf.Ticker('MU').quarterly_financials
        if fin is None or fin.empty:
            return

        gp_row  = _find_row(fin, ['gross profit'])
        rev_row = _find_row(fin, ['total revenue', 'net revenue'])

        if gp_row is None or rev_row is None:
            _print('[T4] MU 행 탐색 실패')
            return

        def _gm(i):
            gp  = _safe(gp_row.iloc[i])
            rev = _safe(rev_row.iloc[i])
            if gp is None or rev is None or rev == 0:
                return None
            g = gp / rev * 100
            return g if 0 < g < 85 else None  # 범위 이상치 제거

        gm_cur  = _gm(0)
        gm_prev = _gm(4) if len(gp_row) > 4 else None

        if gm_cur is None:
            _print(f'[T4] MU GM 값 이상 -- 건너뜀')
            return

        reasons = []
        triggered = False
        if gm_cur < 40:
            triggered = True
            reasons.append(f'GM={gm_cur:.1f}%<40%')
        if gm_prev is not None and (gm_cur - gm_prev) < -10:
            triggered = True
            reasons.append(f'YoY{gm_cur-gm_prev:+.1f}pp')

        yoy_str = f' YoY{gm_cur-gm_prev:+.1f}pp' if gm_prev else ''
        state['T4'] = {
            'status': triggered,
            'value': f'GM {gm_cur:.1f}%{yoy_str}',
            'note': (
                f'MU 분기 그로스마진 {gm_cur:.1f}%{yoy_str}'
                f' -- {"WARNING: " + " / ".join(reasons) if triggered else "정상 (HBM ASP 대리지표)"}'
            ),
            'auto': True,
            'updated': today,
        }
        _print(f'[T4] MU GM={gm_cur:.1f}%{yoy_str} -> {"TRIGGERED" if triggered else "SAFE"}')
    except Exception as e:
        _print(f'[T4] 실패: {e}')


# ── T5: MU DIO YoY 변화 (D램 재고 프록시) ───────────────────────

def auto_update_t5(state: dict) -> None:
    """
    MU 재고회전일수(DIO) YoY 변화. D램 재고 8주 이상 반등 대리 지표.
    DIO YoY +28일(4주) 이상 증가 시 경고.
    """
    import yfinance as yf
    today = datetime.now(KST).strftime('%Y-%m-%d')
    try:
        time.sleep(0.4)
        mu = yf.Ticker('MU')

        # 재고: quarterly_balance_sheet
        try:
            bs = mu.quarterly_balance_sheet
        except Exception:
            bs = mu.quarterly_balance_sheet

        # COGS: quarterly_income_stmt
        try:
            fin = mu.quarterly_income_stmt
        except Exception:
            fin = mu.quarterly_financials

        if bs is None or fin is None or bs.empty or fin.empty:
            return

        inv_row  = _find_row(bs,  ['inventory', 'inventories'])
        cogs_row = _find_row(fin, ['cost of revenue', 'cost of goods'])

        if inv_row is None or cogs_row is None:
            _print('[T5] MU 재고/COGS 행 탐색 실패')
            return

        def _dio(col):
            inv  = abs(_safe(inv_row.iloc[col]) or 0)
            cogs = abs(_safe(cogs_row.iloc[col]) or 0)
            if inv > 0 and cogs > 0:
                # 분기 COGS -> 연율 환산
                annual_cogs = cogs * 4
                return inv / (annual_cogs / 365)
            return None

        dio_cur  = _dio(0)
        dio_prev = _dio(4) if len(inv_row) > 4 else None

        if dio_cur is None:
            return

        change = (dio_cur - dio_prev) if dio_prev else None
        # 원본 게이트: "8주 이상 반등" = YoY +56일 이상 증가
        # 실용 기준: YoY +28일(4주) 이상 증가 시 경고 (전조 포착)
        triggered = change is not None and change >= 28

        change_str = f' YoY{change:+.0f}d' if change is not None else ''
        state['T5'] = {
            'status': triggered,
            'value': f'DIO {dio_cur:.0f}d({dio_cur/7:.1f}wk){change_str}',
            'note': (
                f'MU DIO {dio_cur:.0f}일({dio_cur/7:.1f}주){change_str}'
                f' -- {"WARNING: 재고 급증(+28d YoY 임계)" if triggered else "정상 (D램 재고 대리지표)"}'
            ),
            'auto': True,
            'updated': today,
        }
        _print(f'[T5] MU DIO={dio_cur:.0f}d{change_str} -> {"TRIGGERED" if triggered else "SAFE"}')
    except Exception as e:
        _print(f'[T5] 실패: {e}')


# ── T6: M7 D&A/영업이익 비율 급증 ───────────────────────────────

def auto_update_t6(state: dict) -> None:
    """M7 분기 D&A/영업이익 비율 YoY +20pp 이상 증가한 회사 탐지."""
    import yfinance as yf
    today = datetime.now(KST).strftime('%Y-%m-%d')

    alerts, ratios = [], []

    for t in M7_TICKERS:
        try:
            time.sleep(0.4)
            ticker = yf.Ticker(t)

            try:
                fin = ticker.quarterly_income_stmt
            except Exception:
                fin = ticker.quarterly_financials
            try:
                cf = ticker.quarterly_cashflow
            except Exception:
                cf = None

            if fin is None or fin.empty:
                continue

            # D&A: cashflow 우선, 없으면 income_stmt
            da_row = None
            if cf is not None and not cf.empty:
                da_row = _find_row(cf, ['depreciation', 'amortization'])
            if da_row is None:
                da_row = _find_row(fin, ['depreciation', 'amortization'])

            oi_row = _find_row(fin, ['operating income', 'operating income loss'])

            if da_row is None or oi_row is None:
                continue

            da_cur  = abs(_safe(da_row.iloc[0]) or 0)
            oi_cur  = _safe(oi_row.iloc[0])
            da_prev = abs(_safe(da_row.iloc[4]) if len(da_row) > 4 else None or 0)
            oi_prev = _safe(oi_row.iloc[4]) if len(oi_row) > 4 else None

            if not oi_cur or oi_cur <= 0:
                continue

            ratio_cur = da_cur / oi_cur * 100
            # 비율 이상치 제거 (0-200% 범위 밖은 데이터 오류 가능성)
            if not (0 < ratio_cur < 200):
                continue

            ratio_prev = (da_prev / oi_prev * 100) if (oi_prev and oi_prev > 0) else None
            delta = (ratio_cur - ratio_prev) if ratio_prev else None

            ratios.append(f'{t}:{ratio_cur:.0f}%')
            if delta and delta >= 20:
                alerts.append(f'{t}(+{delta:.0f}pp)')
        except Exception as e:
            _print(f'[T6] {t}: {e}')

    triggered = len(alerts) > 0
    ratio_str = ' | '.join(ratios[:4]) if ratios else 'N/A'
    state['T6'] = {
        'status': triggered,
        'value': f'경고 {len(alerts)}사' if triggered else '이상 없음',
        'note': (
            f'M7 D&A/OI -- '
            f'{"WARNING: " + ", ".join(alerts) if triggered else "전사 YoY +20pp 미만 (정상)"}'
            f' | {ratio_str}'
        ),
        'auto': True,
        'updated': today,
    }
    _print(f'[T6] 경고 {len(alerts)}사: {alerts if alerts else "없음"}')


# ── 공통 ──────────────────────────────────────────────────────────

def load_existing_state() -> dict:
    if not GATES_JSON.exists():
        return {}
    try:
        existing = json.loads(GATES_JSON.read_text(encoding='utf-8'))
        return {
            g['id']: {k: g.get(k) for k in ('status', 'value', 'note', 'auto', 'updated')}
            for g in existing.get('gates', [])
        }
    except Exception:
        return {}


def compute_action(lit, t1_on, t2_on):
    if t1_on and t2_on:
        return '!!! 즉시 방어 전환 (T1+T2 동시)', 4
    if lit >= 3:
        return 'M게이트 OFF -- 반도체 익스포저 단계 축소', 3
    if lit >= 2:
        return '신규 진입 중지 / S4-S5 사이즈 금지', 2
    if lit >= 1:
        return '모니터링 강화 -- 추가 점등 대비', 1
    return '정상 운용', 0


def build_output(state: dict) -> dict:
    today = datetime.now(KST).strftime('%Y-%m-%d')
    gates_out = []
    for defn in GATE_DEFS:
        gid = defn['id']
        s = state.get(gid, {})
        gates_out.append({
            **defn,
            'status':  s.get('status', False),
            'value':   s.get('value', 'N/A'),
            'note':    s.get('note', '데이터 없음'),
            'auto':    s.get('auto', True),
            'updated': s.get('updated', today),
        })

    lit   = sum(1 for g in gates_out if g['status'])
    t1_on = next((g['status'] for g in gates_out if g['id'] == 'T1'), False)
    t2_on = next((g['status'] for g in gates_out if g['id'] == 'T2'), False)
    action_text, level = compute_action(lit, t1_on, t2_on)

    level_emoji = {4: '🚨', 3: '🔴', 2: '🟠', 1: '🟡', 0: '🟢'}
    action = f'{level_emoji.get(level, "")} {action_text}'

    return {
        'updated': today,
        'gates': gates_out,
        'lit_count': lit,
        'action_level': level,
        'action': action,
        'rule': '2개: 신규 진입 중지 | 3개: M게이트 OFF | T1+T2 동시: 즉시 방어 전환',
    }


def run() -> dict:
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    state = load_existing_state()

    for gid, fn in [
        ('T1', auto_update_t1),
        ('T2', auto_update_t2),
        ('T3', auto_update_t3),
        ('T4', auto_update_t4),
        ('T5', auto_update_t5),
        ('T6', auto_update_t6),
    ]:
        try:
            fn(state)
        except Exception as e:
            _print(f'[{gid}] 예외: {e}')

    result = build_output(state)
    GATES_JSON.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    _print(f'[strategy_gates] 완료 -- 점등 {result["lit_count"]}/6 -- {result["action"]}')
    return result


if __name__ == '__main__':
    run()
