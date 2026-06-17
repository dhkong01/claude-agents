"""
Portfolio Daily Report - GitHub Actions
PC 없이 클라우드에서 실행: 가격조회 → RS/CANSLIM 계산 → 카카오톡 5개 메시지 전송
"""
import subprocess, sys
subprocess.call([sys.executable,'-m','pip','install','yfinance','yahooquery','requests','-q'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import yfinance as yf, requests, os, json as _json, subprocess
from datetime import date, datetime, timedelta, timezone

# ── 포트폴리오 설정 ──────────────────────────────────────────
def _load_portfolio():
    raw = os.environ.get("PORTFOLIO_JSON", "")
    if raw:
        try: return _json.loads(raw)
        except: pass
    return {
        "holdings": [
            {'t':'TSLA', 'sh':140, 'ac':183.6738},
            {'t':'PLTR', 'sh':60,  'ac':168.19},
            {'t':'VKTX', 'sh':350, 'ac':33.4824},
            {'t':'META', 'sh':15,  'ac':637.28},
            {'t':'MRVL', 'sh':220, 'ac':236.58},
            {'t':'ARM',  'sh':90,  'ac':396.62},
            {'t':'LRCX', 'sh':20,  'ac':389.0},
        ],
        "next_rebalance": "2026-08-21",
        "total_cost": 152607
    }

_pf   = _load_portfolio()
PF    = _pf["holdings"]
NEXT_RB    = _pf.get("next_rebalance", "2026-08-21")
TOTAL_COST = _pf.get("total_cost", 148501)

# 나스닥100 대표 종목 집합 (msg4 필터용)
NDX100_SET = {
    'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AVGO','COST','NFLX',
    'AMD','ADBE','QCOM','CSCO','INTU','AMGN','TXN','AMAT','LRCX','KLAC',
    'SNPS','CDNS','MCHP','MU','ADI','PANW','CRWD','ZS','FTNT','DDOG',
    'WDAY','TEAM','TTD','MELI','GILD','REGN','VRTX','ISRG','SBUX','ORLY',
    'MNST','CPRT','PAYX','CTAS','ADP','BKNG','TMUS','PCAR','ON','ARM','MRVL',
}

# 유니버스 CSF 참조 테이블 (IBD 역산값, 미등록 종목은 38 사용)
CSF_UNIVERSE = {
    'TSLA':30,'PLTR':39,'VKTX':24,'META':42,'MRVL':34,'ARM':42,
    'MU':42,'AMD':42,'ONDS':29,'LRCX':42,'ON':27,'AMAT':39,'DDOG':42,'KLAC':35,
    'NVDA':45,'AVGO':43,'AAPL':42,'MSFT':42,'AMZN':42,'GOOGL':42,'COST':40,'NFLX':42,
    'ADBE':40,'QCOM':38,'CSCO':36,'INTU':42,'TXN':38,'SNPS':42,'CDNS':42,
    'PANW':42,'CRWD':42,'ZS':40,'FTNT':40,'WDAY':40,'TEAM':40,'TTD':38,
    'MELI':40,'ADI':38,'MCHP':36,'BKNG':40,'TMUS':36,'PCAR':36,
    'ISRG':42,'SBUX':32,'VRTX':42,'GILD':36,'REGN':42,'AMGN':36,
    'ORLY':38,'MNST':36,'CPRT':38,'PAYX':36,'CTAS':36,'ADP':36,'CAT':38,
}

# IBD RS 비교 유니버스 (daily_report.py 와 동일)
UNIVERSE = list(dict.fromkeys([
    'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AVGO','COST','NFLX',
    'AMD','ADBE','QCOM','CSCO','INTU','AMGN','TXN','AMAT','LRCX','KLAC',
    'SNPS','CDNS','MCHP','MU','ADI','PANW','CRWD','ZS','FTNT','DDOG',
    'WDAY','TEAM','TTD','MELI','GILD','REGN','VRTX','ISRG','SBUX','ORLY',
    'MNST','CPRT','PAYX','CTAS','ADP','BKNG','TMUS','PCAR','ON','ARM','MRVL',
    'JPM','JNJ','UNH','V','MA','XOM','CVX','WMT','PG','HD',
    'MRK','LLY','ABBV','BAC','GS','MS','BLK','SPGI','CB','MMC',
    'LIN','SHW','ECL','ETN','CAT','DE','UPS','GE','RTX','HON',
    'KO','PEP','MCD','CMG','EL','NKE','TGT','LOW','TJX','ROST',
    'NEE','DUK','SO','AEP','SRE',
    'PLD','AMT','EQIX','PSA','SPG',
    'PLTR','MSTR','VKTX','ONDS','RGTI',
] + [p['t'] for p in PF]))

# ── 카카오 토큰 갱신 ──────────────────────────────────────────
def get_kakao_token() -> str:
    """Refresh Token으로 Access Token 갱신"""
    rest_key     = os.environ.get("KAKAO_REST_API_KEY", "")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN", "")
    if not (rest_key and refresh_token):
        print("[Kakao] KAKAO_REST_API_KEY / KAKAO_REFRESH_TOKEN Secret 미설정")
        return ""
    r = requests.post("https://kauth.kakao.com/oauth/token", data={
        "grant_type":    "refresh_token",
        "client_id":     rest_key,
        "refresh_token": refresh_token,
    }, timeout=10)
    if r.status_code == 200:
        data = r.json()
        token = data.get("access_token", "")
        print(f"[Kakao] 토큰 갱신 성공 (expires_in={data.get('expires_in')}s)")
        return token
    else:
        print(f"[Kakao] 토큰 갱신 실패: {r.status_code} {r.text[:200]}")
        return ""

def send_kakao(token: str, message: str) -> bool:
    if not token:
        return False
    r = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {token}"},
        data={"template_object": _json.dumps({
            "object_type": "text",
            "text": message[:1900],   # 카카오 최대 2000자
            "link": {"web_url": "", "mobile_web_url": ""}
        })},
        timeout=10
    )
    ok = r.status_code == 200
    print(f"  {'✓' if ok else '✗'} ({r.status_code})")
    return ok

# ── 데이터 수집 ──────────────────────────────────────────────
def fetch_closes():
    tickers = list(set(UNIVERSE + ['^VIX', '^TNX', 'SPY']))
    print(f"[데이터] {len(tickers)}종목 다운로드...")
    df = yf.download(tickers, period='1y', auto_adjust=True,
                     progress=False, threads=True)
    closes = df['Close']

    # ── 포트폴리오 + 주요 지표: 항상 period='1d' 로 최신가 보강 ──
    # bulk download(period='1y')는 일부 종목의 최신일 데이터가 NaN으로 오는 문제가 있음
    # → fast_info.last_price (실시간) 또는 history(period='1d') 로 덮어쓰기
    must_have = [p['t'] for p in PF] + ['^VIX', '^TNX']
    latest_idx = closes.index[-1]
    for t in must_have:
        price = None
        # 1) fast_info.last_price 시도
        try:
            price = float(yf.Ticker(t).fast_info.last_price)
        except Exception:
            pass
        # 2) fast_info 실패 시 history(period='1d') 시도
        if not price:
            try:
                s = yf.Ticker(t).history(period='1d', auto_adjust=True)['Close'].dropna()
                if not s.empty:
                    price = float(s.iloc[-1])
            except Exception:
                pass
        if price:
            closes.loc[latest_idx, t] = price
            print(f"  {t} = {price:.2f}")

    return closes

# ── IBD RS 계산 (daily_report.py 동일 공식) ──────────────────
def weighted_return(s):
    if len(s) < 50: return None
    def r(n): return (float(s.iloc[-1] / s.iloc[-min(n, len(s)-1)]) - 1) * 100
    return 0.4*r(63) + 0.2*r(126) + 0.2*r(189) + 0.2*r(252)

def calc_universe_rs(closes):
    """전체 유니버스 RS 백분위 계산"""
    wr_map = {}
    for t in UNIVERSE:
        if t in closes.columns:
            s = closes[t].dropna()
            w = weighted_return(s)
            if w is not None:
                wr_map[t] = w
    if not wr_map: return {}
    ranked = sorted(wr_map.items(), key=lambda x: -x[1])
    n = len(ranked)
    return {t: round(max(1, min(99, int((1 - i/n) * 99) + 1)))
            for i, (t, _) in enumerate(ranked)}

def calc_canslim_cs(rs, vix):
    """간략 CANSLIM (GitHub Actions 용)"""
    M = 10 if vix < 15 else 6 if vix < 25 else 2
    L = 10 if rs >= 90 else 7 if rs >= 80 else 5 if rs >= 60 else 3
    # CSF: 유니버스 평균값 사용 (yahooquery 없이)
    CSF_DEFAULT = {'TSLA':30,'PLTR':39,'VKTX':24,'META':42,
                   'MRVL':34,'ONDS':29,'RGTI':31}
    csf = CSF_DEFAULT.get('DEFAULT', 30)
    return min(csf + L + M, 70)

# ── 메시지 빌드 ──────────────────────────────────────────────
def build_messages(closes):
    # KST(UTC+9) 기준 날짜 사용 — GitHub Actions는 UTC 타임존이므로 반드시 변환
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).date()
    dow   = ['월','화','수','목','금','토','일'][today.weekday()]
    # DATE_US: KST 월요일이면 3일 전(금), 그 외 1일 전
    offset = 3 if today.weekday() == 0 else 1
    date_us = (today - timedelta(days=offset)).strftime('%Y-%m-%d')

    def fv(k):
        try: return float(closes[k].dropna().iloc[-1])
        except: return None

    vix = fv('^VIX') or 20.0
    tny = fv('^TNX') or 4.5
    phase_icon  = '🟢' if vix < 15 else '🟡' if vix < 25 else '🔴'
    M = 10 if vix < 15 else 6 if vix < 25 else 2

    print("[RS] 유니버스 계산...")
    rs_map = calc_universe_rs(closes)

    # 포트폴리오 계산
    tv = 0.0
    rows = []
    CSF_MAP = {'TSLA':30,'PLTR':39,'VKTX':24,'META':42,'MRVL':34,'ARM':47,'LRCX':42}
    for p in PF:
        t = p['t']
        price = fv(t)
        rs    = rs_map.get(t, 50)
        L     = 10 if rs >= 90 else 7 if rs >= 80 else 5 if rs >= 60 else 3
        csf   = CSF_MAP.get(t, 30)
        cs    = min(csf + L + M, 70)
        if price and price > 0:
            tv   += price * p['sh']
            pnl   = (price - p['ac']) / p['ac'] * 100 if p['ac'] > 0 else 0
            ico   = '🟢' if pnl >= 0 else '🔴'
            rows.append({'t':t,'price':price,'pnl':pnl,'rs':rs,'cs':cs,'ico':ico,'ok':True})
        else:
            rows.append({'t':t,'price':None,'pnl':0,'rs':rs,'cs':cs,'ico':'❓','ok':False})

    tr = (tv - TOTAL_COST) / TOTAL_COST * 100 if TOTAL_COST else 0
    dl = (date.fromisoformat(NEXT_RB) - today).days

    # 메시지1: 시장 국면
    msg1 = (
        f"📊 포트폴리오 리포트 ({date_us} 종가)\n"
        f"📅 KST {today}({dow}) 07:15기준\n"
        f"{'━'*24}\n"
        f"[시장국면] {phase_icon} VIX {vix:.2f}  금리 {tny:.2f}%"
    )

    # 메시지2: 종목 1~4
    lines2 = [f"[포트폴리오] {date_us}종가"]
    for r in rows[:4]:
        if r['ok']:
            lines2.append(f"{r['ico']}{r['t']:<5} ${r['price']:>8.2f} {r['pnl']:>+5.1f}% RS{r['rs']} CS{r['cs']}/70")
        else:
            lines2.append(f"❓{r['t']:<5} N/A")
    msg2 = '\n'.join(lines2)

    # 메시지3: 종목 5~6 + 합계
    lines3 = []
    for r in rows[4:]:
        if r['ok']:
            lines3.append(f"{r['ico']}{r['t']:<5} ${r['price']:>8.2f} {r['pnl']:>+5.1f}% RS{r['rs']} CS{r['cs']}/70")
        else:
            lines3.append(f"❓{r['t']:<5} N/A")
    lines3 += ['─'*21, f"총평가 ${tv:>10,.0f} ({tr:>+.2f}%)"]
    msg3 = '\n'.join(lines3)

    # CS 계산 헬퍼 (CSF_UNIVERSE 참조, 동적 RS/M 반영)
    def cs_for(t, rs):
        csf = CSF_UNIVERSE.get(t, 38)
        L = 10 if rs >= 90 else 7 if rs >= 80 else 5 if rs >= 60 else 3
        return min(csf + L + M, 70)

    # 메시지4: 나스닥100 RS Top5 (동적 계산)
    ndx_ranked = sorted(
        [(t, rs) for t, rs in rs_map.items() if t in NDX100_SET],
        key=lambda x: -x[1]
    )[:5]
    top5_lines = '\n'.join(
        f"  {i+1}. {t:<5} RS {rs}  CS {cs_for(t, rs)}/70"
        for i, (t, rs) in enumerate(ndx_ranked)
    )
    msg4 = (
        f"[나스닥100 RS Top5 · {date_us}기준]\n"
        f"{top5_lines}\n"
        f"📆 D-{dl} (2026-08-21)\n"
        f"🤖 데이터:{date_us}종가|매일자동갱신"
    )

    # 메시지5: 시장강세 TOP10 (동적 계산)
    top10_ranked = sorted(rs_map.items(), key=lambda x: -x[1])[:10]
    t10 = [f"{t} {cs_for(t, rs)}/{rs}" for t, rs in top10_ranked]
    # 10개 미만일 경우 빈 칸 채워서 IndexError 방지
    while len(t10) < 10:
        t10.append("—")
    msg5 = (
        f"[시장강세TOP10 · {date_us}기준]\n"
        f"1.{t10[0]}  2.{t10[1]}\n"
        f"3.{t10[2]}  4.{t10[3]}\n"
        f"5.{t10[4]}  6.{t10[5]}\n"
        f"7.{t10[6]}  8.{t10[7]}\n"
        f"9.{t10[8]}  10.{t10[9]}"
    )

    return [msg1, msg2, msg3, msg4, msg5]

# ── Git 커밋 ─────────────────────────────────────────────────
def git_push(full_text):
    from datetime import timezone, timedelta
    KST = timezone(timedelta(hours=9))
    kst_date = datetime.now(KST).strftime('%Y-%m-%d')

    path = 'latest_report.txt'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(full_text)

    subprocess.run(['git','config','user.email','github-actions@github.com'], check=True)
    subprocess.run(['git','config','user.name','github-actions'], check=True)
    subprocess.run(['git','add', path], check=True)
    res = subprocess.run(['git','diff','--cached','--quiet'])
    if res.returncode == 0:
        print("[Git] 변경 없음")
        return

    subprocess.run(['git','commit','-m',f'report: {kst_date}'], check=True)

    # trend_rebalancing 워크플로와 동시 실행 충돌 대비: rebase 후 재시도
    for attempt in range(3):
        r = subprocess.run(['git','push'])
        if r.returncode == 0:
            print(f"[Git] 커밋 완료 (시도 {attempt+1})")
            return
        print(f"[Git] push 실패(시도 {attempt+1}), rebase 후 재시도...")
        subprocess.run(['git','pull','--rebase'], check=False)
    print("[Git] push 3회 실패 — 리포트 전송은 완료, 커밋만 스킵")

# ── 메인 ──────────────────────────────────────────────────────
if __name__ == '__main__':
    # 카카오 토큰 갱신
    kakao_token = get_kakao_token()

    # 데이터 수집 + 메시지 생성
    closes  = fetch_closes()
    messages = build_messages(closes)
    full_text = '\n\n'.join(messages)
    print('\n' + full_text)

    # 카카오톡 전송
    print("\n[카카오톡 전송]")
    for i, msg in enumerate(messages, 1):
        print(f"  메시지{i}...", end='')
        send_kakao(kakao_token, msg)

    # Git 커밋
    git_push(full_text)
