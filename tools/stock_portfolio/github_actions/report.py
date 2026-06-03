"""Portfolio Daily Report - GitHub Actions (with RS + CANSLIM + KakaoTalk)"""
import subprocess, sys
subprocess.call([sys.executable,'-m','pip','install','yfinance','requests','-q'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import yfinance as yf, requests, subprocess
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
    # 기본값: 2026-06-02 기준 현재 포트폴리오
    return {
        "holdings": [
            {'t':'TSLA', 'sh':160,  'ac':183.6738},
            {'t':'PLTR', 'sh':60,   'ac':168.19},
            {'t':'VKTX', 'sh':350,  'ac':33.4824},
            {'t':'META', 'sh':15,   'ac':637.28},
            {'t':'MRVL', 'sh':140,  'ac':205.50},
            {'t':'ONDS', 'sh':2886, 'ac':13.37},
            {'t':'RGTI', 'sh':1101, 'ac':25.47},
        ],
        "next_rebalance": "2026-08-21",
        "total_cost": 156155
    }

_pf_data = _load_portfolio()
PF      = _pf_data["holdings"]
NEXT_RB = _pf_data.get("next_rebalance", "2026-08-21")
TOTAL_COST = _pf_data.get("total_cost", 156155)

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

# ── 카카오톡 전송 ─────────────────────────────────────────────
def send_kakao(message: str) -> bool:
    token = os.environ.get("KAKAO_ACCESS_TOKEN", "")
    if not token:
        print("[KakaoTalk] KAKAO_ACCESS_TOKEN Secret이 설정되지 않음 — 전송 생략")
        return False
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "template_object": _json.dumps({
            "object_type": "text",
            "text": message,
            "link": {"web_url": "", "mobile_web_url": ""}
        })
    }
    try:
        r = requests.post(url, headers=headers, data=payload, timeout=10)
        if r.status_code == 200:
            print("[KakaoTalk] 전송 성공")
            return True
        else:
            print(f"[KakaoTalk] 전송 실패: {r.status_code} {r.text[:200]}")
            return False
    except Exception as e:
        print(f"[KakaoTalk] 전송 오류: {e}")
        return False

# ── 메시지 생성 ───────────────────────────────────────────────
def build(closes):
    today = date.today().strftime('%Y-%m-%d')
    dow   = ['월','화','수','목','금','토','일'][date.today().weekday()]

    def fv(k):
        try: return float(closes[k].dropna().iloc[-1])
        except: return None

    vix = fv('^VIX')
    tny = fv('^TNX')
    phase_icon  = ('🟢' if vix and vix<15 else '🟡' if vix and vix<25 else '🔴')
    phase_label = ('안정' if vix and vix<15 else '주의' if vix and vix<25 else '위험')
    m_score = 10 if vix and vix<15 else 6 if vix and vix<25 else 2

    # SPY weighted return (RS 기준)
    try:
        spy = closes['SPY'].dropna()
        def sr(n): return (float(spy.iloc[-1]/spy.iloc[-min(n,len(spy)-1)]) - 1)*100
        spy_w = 0.4*sr(63)+0.2*sr(126)+0.2*sr(189)+0.2*sr(252)
    except: spy_w = 0

    dl = (date.fromisoformat(NEXT_RB) - date.today()).days

    # 메시지1: 시장국면
    msg1_lines = [
        f'📊 포트폴리오 리포트 ({today} 종가)',
        f'📅 KST {today}({dow}) GitHub Actions',
        '━'*24,
        f'[시장국면] {phase_icon} {phase_label}  VIX {vix:.2f}  금리 {tny:.2f}%' if (vix and tny) else '[시장국면] N/A',
    ]

    # 포트폴리오 계산
    tv = 0
    rows = []
    for p in PF:
        t = p['t']
        price = fv(t)
        if price and price > 0 and p['ac'] > 0:
            val  = price * p['sh']
            ret  = (price - p['ac']) / p['ac'] * 100
            tv  += val
            rs   = calc_rs(closes, t, spy_w)
            cs   = calc_canslim(rs, closes, t, m_score)
            ico  = '🟢' if ret>=0 else '🔴'
            rows.append({'t':t,'price':price,'ret':ret,'rs':rs,'cs':cs,'ico':ico})
        else:
            rows.append({'t':t,'price':None,'ret':0,'rs':50,'cs':35,'ico':'❓'})

    tr = (tv - TOTAL_COST) / TOTAL_COST * 100 if TOTAL_COST else 0

    # 메시지2: 1~4번째 종목
    msg2_lines = [f'[포트폴리오] {today}종가']
    for r in rows[:4]:
        if r['price']:
            msg2_lines.append(f"{r['ico']}{r['t']:<5} ${r['price']:>8.2f} {r['ret']:>+5.1f}% RS{r['rs']} CS{r['cs']}/70")
        else:
            msg2_lines.append(f"❓{r['t']:<5} N/A")

    # 메시지3: 5~7번째 + 합계
    msg3_lines = []
    for r in rows[4:]:
        if r['price']:
            msg3_lines.append(f"{r['ico']}{r['t']:<5} ${r['price']:>8.2f} {r['ret']:>+5.1f}% RS{r['rs']} CS{r['cs']}/70")
        else:
            msg3_lines.append(f"❓{r['t']:<5} N/A")
    msg3_lines += [
        '─'*21,
        f'총평가 ${tv:>10,.0f} ({tr:>+.2f}%)',
    ]

    return (
        '\n'.join(msg1_lines),
        '\n'.join(msg2_lines),
        '\n'.join(msg3_lines),
        f'📆 D-{dl} (2026-08-21)\n🤖 by GitHub Actions',
    )

# ── Git 커밋 ─────────────────────────────────────────────────
def git_push(full_text):
    with open('latest_report.txt','w',encoding='utf-8') as f:
        f.write(full_text)
    subprocess.run(['git','config','user.email','github-actions@github.com'],check=True)
    subprocess.run(['git','config','user.name','github-actions'],check=True)
    subprocess.run(['git','add','latest_report.txt'],check=True)
    result = subprocess.run(['git','diff','--cached','--quiet'])
    if result.returncode != 0:
        subprocess.run(['git','commit','-m',f'report: {date.today()}'],check=True)
        subprocess.run(['git','push'],check=True)
        print("Pushed latest_report.txt")
    else:
        print("No changes to commit")

if __name__ == '__main__':
    closes = fetch()
    msgs = build(closes)
    full_text = '\n\n'.join(msgs)
    print(full_text)

    # 카카오톡 전송 (4개 메시지)
    for i, msg in enumerate(msgs, 1):
        result = send_kakao(msg)
        print(f"메시지{i} {'✓' if result else '✗'}")

    # Git 커밋
    git_push(full_text)
