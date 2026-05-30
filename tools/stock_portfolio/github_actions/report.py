"""Portfolio Daily Report - GitHub Actions (with RS + CANSLIM)"""
import subprocess, sys
subprocess.call([sys.executable,'-m','pip','install','yfinance','-q'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import yfinance as yf, subprocess
from datetime import date

import os, json as _json

def _load_portfolio():
    """GitHub Secret PORTFOLIO_JSON 또는 기본값 사용"""
    raw = os.environ.get("PORTFOLIO_JSON", "")
    if raw:
        try:
            return _json.loads(raw)
        except Exception:
            pass
    # 기본값: 티커명만 표시, 수량/단가 비공개
    return {
        "holdings": [
            {'t':'TSLA','sh':0,'ac':0},
            {'t':'PLTR','sh':0,'ac':0},
            {'t':'MSTR','sh':0,'ac':0},
            {'t':'ASTS','sh':0,'ac':0},
            {'t':'RKLB','sh':0,'ac':0},
            {'t':'VKTX','sh':0,'ac':0},
            {'t':'META','sh':0,'ac':0},
            {'t':'VRT', 'sh':0,'ac':0},
        ],
        "next_rebalance": "2026-08-21"
    }

_pf_data = _load_portfolio()
PF      = _pf_data["holdings"]
NEXT_RB = _pf_data["next_rebalance"]

# ── 데이터 수집 ──────────────────────────────────────────────
def fetch():
    tickers = [p['t'] for p in PF] + ['^VIX','^TNX','SPY']
    df = yf.download(tickers, period='1y', auto_adjust=True,
                     progress=False, threads=True)
    return df['Close']

# ── RS 계산 (IBD 방식) ───────────────────────────────────────
def calc_rs(closes, ticker, spy_w):
    try:
        s = closes[ticker].dropna()
        if len(s) < 50: return 50
        def r(n): return (float(s.iloc[-1]/s.iloc[-min(n,len(s)-1)]) - 1)*100
        w = 0.4*r(63) + 0.2*r(126) + 0.2*r(189) + 0.2*r(252)
        d = w - spy_w
        if d>=40: return 95
        if d>=25: return 90
        if d>=15: return 82
        if d>=5:  return 72
        if d>=-5: return 55
        if d>=-15:return 40
        if d>=-25:return 28
        return 15
    except: return 50

# ── CANSLIM 계산 ─────────────────────────────────────────────
def calc_canslim(rs, closes, ticker, m_score):
    try:
        s = closes[ticker].dropna()
        cai = 10 if rs>=90 else 7 if rs>=80 else 5
        N = 7
        if len(s) >= 252:
            h52 = float(s.tail(252).max())
            ratio = float(s.iloc[-1]) / h52
            N = 10 if ratio>=0.95 else 7 if ratio>=0.90 else 4 if ratio>=0.80 else 1
        L = 10 if rs>=90 else 7 if rs>=80 else 3
        return min(cai*3 + N + 7 + L + m_score, 70)
    except: return 35

# ── 메시지 생성 ───────────────────────────────────────────────
def build(closes):
    today = date.today().strftime('%Y-%m-%d')
    dow   = ['월','화','수','목','금','토','일'][date.today().weekday()]

    def fv(k):
        try: return float(closes[k].dropna().iloc[-1])
        except: return None

    vix = fv('^VIX')
    tny = fv('^TNX')
    phase_label = ('🟢 안정' if vix and vix<15 else
                   '🟡 주의' if vix and vix<25 else '🔴 위험')
    m_score = 10 if vix and vix<15 else 6 if vix and vix<25 else 2

    # SPY weighted return (RS 기준)
    try:
        spy = closes['SPY'].dropna()
        def sr(n): return (float(spy.iloc[-1]/spy.iloc[-min(n,len(spy)-1)]) - 1)*100
        spy_w = 0.4*sr(63)+0.2*sr(126)+0.2*sr(189)+0.2*sr(252)
    except: spy_w = 0

    lines = [
        '📊 포트폴리오 일일 리포트',
        '━'*24,
        f'📅 {today} ({dow})',
        '',
        f'[시장 국면] {phase_label}',
        f'  VIX {vix:.2f}  금리 {tny:.2f}%' if (vix and tny) else '  VIX N/A  금리 N/A',
        '',
        '[내 포트폴리오]',
        f"{'티커':<6} {'현재가':>8}  {'손익':>7}  RS  CANSLIM",
        '─'*40,
    ]

    tv = tc = 0
    for p in PF:
        t = p['t']
        price = fv(t)
        if price and price > 0:
            val  = price * p['sh']
            ret  = (price - p['ac']) / p['ac'] * 100
            tv  += val
            tc  += p['ac'] * p['sh']
            rs   = calc_rs(closes, t, spy_w)
            cs   = calc_canslim(rs, closes, t, m_score)
            sgn  = '+' if ret>=0 else ''
            ico  = '🟢' if ret>=0 else '🔴'
            lines.append(f"{ico}{t:<5} ${price:>8.2f}  {sgn}{ret:>5.1f}%  {rs:>2}  {cs}/70")
        else:
            lines.append(f"❓{t:<5}  N/A")

    tr = (tv-tc)/tc*100 if tc else 0
    dl = (date.fromisoformat(NEXT_RB) - date.today()).days
    sgn = '+' if tr>=0 else ''

    lines += [
        '─'*40,
        f'총평가  ${tv:>10,.0f}  ({sgn}{tr:.2f}%)',
        '',
        f'📆 리밸런싱 D-{dl} ({NEXT_RB})',
        '─'*24,
        '🤖 by GitHub Actions',
    ]
    return '\n'.join(lines)

# ── Git 커밋 ─────────────────────────────────────────────────
def git_push(msg_text):
    with open('latest_report.txt','w',encoding='utf-8') as f:
        f.write(msg_text)
    subprocess.run(['git','config','user.email','github-actions@github.com'],check=True)
    subprocess.run(['git','config','user.name','github-actions'],check=True)
    subprocess.run(['git','add','latest_report.txt'],check=True)
    result = subprocess.run(['git','diff','--cached','--quiet'])
    if result.returncode != 0:  # 변경사항 있을 때만 커밋
        subprocess.run(['git','commit','-m',f'report: {date.today()}'],check=True)
        subprocess.run(['git','push'],check=True)
        print("Pushed latest_report.txt")
    else:
        print("No changes to commit")

if __name__ == '__main__':
    closes = fetch()
    msg = build(closes)
    print(msg)
    git_push(msg)
