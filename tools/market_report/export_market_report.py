#!/usr/bin/env python3
"""마켓리포트용 실데이터 수집 -> docs/data/market_report.json

소스
  - 네이버 증권 모바일 API: 한국 지수/국채, 종목 시세·차트·수급·재무·뉴스·공시·리포트, 순위, 업종
  - yfinance: 해외 지수, 환율, 달러지수, 종목 현금흐름
실패한 항목은 건너뛰고(없는 값은 JSON에서 생략), 핵심 데이터(한국 지수)가 없으면
기존 파일을 덮어쓰지 않고 종료 코드 1로 끝난다.
"""
import json
import sys
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

try:
    import yfinance as yf
except ImportError:  # 해외 지수/환율/현금흐름만 비게 된다
    yf = None

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "data" / "market_report.json"
M = "https://m.stock.naver.com/api"
A = "https://api.stock.naver.com"
KST = dt.timezone(dt.timedelta(hours=9))
DEFAULT_WATCH = ["005930", "000660", "042700", "196170"]
TOP_KOSPI, TOP_KOSDAQ, RANK_N, SPARK_N, BARS_N = 20, 8, 8, 24, 450

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://m.stock.naver.com/"})


def log(msg):
    print("[market_report] " + msg, file=sys.stderr)


def get(url, retries=3):
    for i in range(retries):
        try:
            r = S.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404, 409, 410):
                return None
        except Exception:
            pass
        time.sleep(0.6 * (i + 1))
    return None


def num(s):
    """'1,234' '+1,234' '-5.2%' '9.89배' '-' -> float | None"""
    if s is None:
        return None
    t = str(s).replace(",", "").replace("%", "").replace("배", "").replace("원", "").strip()
    if t in ("", "-", "N/A"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def r2(x):
    return None if x is None else round(float(x), 2)


# ---------------------------------------------------------------- 지수/환율/금리
def naver_index(code, name):
    rows = get(f"{M}/index/{code}/price?pageSize={SPARK_N + 1}&page=1")
    if not rows or len(rows) < 2:
        return None
    closes = [num(r["closePrice"]) for r in rows][::-1]
    return {"name": name, "value": closes[-1], "change": r2(num(rows[0]["compareToPreviousClosePrice"])),
            "pct": r2(num(rows[0]["fluctuationsRatio"])), "spark": [round(c, 2) for c in closes[-SPARK_N:]],
            "date": rows[0]["localTradedAt"]}


_yf_cache = {}


def yf_hist(ticker):
    if yf is None:
        return None
    if ticker not in _yf_cache:
        try:
            h = yf.Ticker(ticker).history(period="2mo", auto_adjust=False)
            c = [float(x) for x in h["Close"].dropna().tolist()]
            _yf_cache[ticker] = (c, str(h.index[-1])[:10]) if len(c) >= 2 else None
        except Exception:
            _yf_cache[ticker] = None
    return _yf_cache[ticker]


def yf_index(ticker, name):
    h = yf_hist(ticker)
    if not h:
        return None
    c, d = h
    return {"name": name, "value": round(c[-1], 2), "change": round(c[-1] - c[-2], 2),
            "pct": round((c[-1] - c[-2]) / c[-2] * 100, 2), "spark": [round(x, 2) for x in c[-SPARK_N:]], "date": d}


def bond_tile(code):
    d = get(f"{A}/marketindex/bond/{code}")
    v = num(d and d.get("closePrice"))
    if v is None:
        return None
    bp = (num(d.get("fluctuations")) or 0) * 100
    return {"label": "10년물 국채금리", "value": f"{v:.2f}%", "delta": f"{abs(bp):.1f}bp" if bp else "", "dir": (bp > 0) - (bp < 0)}


def fx_tile(ticker, label, cur, usd_per_unit=False, dec=2):
    h = yf_hist(ticker)
    if not h:
        return None
    c = h[0]
    pct = (c[-1] - c[-2]) / c[-2] * 100
    d = (pct > 0) - (pct < 0)
    strong = (d > 0) if usd_per_unit else (d < 0)
    unit = f"1{cur}당 달러" if usd_per_unit else f"1달러당 {cur}"
    sub = unit + (f" · {cur} {'강세' if strong else '약세'}" if d else "")
    return {"label": label, "value": f"{c[-1]:,.{dec}f}", "delta": f"{abs(pct):.2f}%" if d else "", "dir": d, "sub": sub}


# (yfinance 지수 [(티커, 이름)], 국채 코드, 환율 인자)
FOREIGN = {
    "US": ([("^GSPC", "S&P500"), ("^IXIC", "나스닥종합"), ("^DJI", "다우존스")], "US10YT=RR", ("DX-Y.NYB", "달러지수", "달러", False, 2)),
    "JP": ([("^N225", "니케이225"), ("1306.T", "TOPIX ETF(1306)")], "JP10YT=RR", ("JPY=X", "엔/달러", "엔", False, 2)),
    "CN": ([("000001.SS", "상해종합"), ("399001.SZ", "선전성분"), ("000300.SS", "CSI300")], "CN10YT=RR", ("CNY=X", "위안/달러", "위안", False, 3)),
    "TW": ([("^TWII", "가권지수")], None, ("TWD=X", "대만달러/달러", "대만달러", False, 2)),
    "IN": ([("^BSESN", "센섹스"), ("^NSEI", "니프티50"), ("^NSEBANK", "니프티뱅크")], "IN10YT=RR", ("INR=X", "루피/달러", "루피", False, 2)),
    "GB": ([("^FTSE", "FTSE100"), ("^FTMC", "FTSE250"), ("^FTLC", "FTSE350")], "GB10YT=RR", ("GBPUSD=X", "파운드/달러", "파운드", True, 3)),
    "DE": ([("^GDAXI", "DAX"), ("^MDAXI", "MDAX"), ("^TECDAX", "TecDAX")], "DE10YT=RR", ("EURUSD=X", "유로/달러", "유로", True, 3)),
    "FR": ([("^FCHI", "CAC40"), ("^SBF120", "SBF120")], "FR10YT=RR", ("EURUSD=X", "유로/달러", "유로", True, 3)),
    "BR": ([("^BVSP", "보베스파")], "BR10YT=RR", ("BRL=X", "헤알/달러", "헤알", False, 2)),
    "AR": ([("ARGT", "MSCI 아르헨티나 ETF(ARGT)")], None, ("ARS=X", "페소/달러", "페소", False, 2)),
    "MX": ([("^MXX", "IPC")], "MX10YT=RR", ("MXN=X", "페소/달러", "페소", False, 2)),
}


def build_countries():
    out = {}
    kr = [naver_index("KOSPI", "코스피"), naver_index("KOSDAQ", "코스닥"), naver_index("KPI200", "코스피200")]
    kr = [x for x in kr if x]
    if not kr:
        return None
    tiles = [bond_tile("KR10YT=RR"), fx_tile("KRW=X", "원/달러", "원", dec=2)]
    out["KR"] = {"indices": kr, "tiles": [t for t in tiles if t]}
    for cid, (idx, bond, fx) in FOREIGN.items():
        ix = [yf_index(t, n) for t, n in idx]
        tiles = [bond_tile(bond) if bond else None, fx_tile(*fx)]
        out[cid] = {"indices": [x for x in ix if x], "tiles": [t for t in tiles if t]}
    return out


# ---------------------------------------------------------------- 종목
def parse_rows(fin):
    info = (fin or {}).get("financeInfo") or {}
    cols = info.get("trTitleList") or []
    rows = {r["title"]: r["columns"] for r in info.get("rowList") or []}
    return cols, rows


def build_fin(code, mkt_suffix):
    keymap = {"rev": "매출액", "op": "영업이익", "ni": "당기순이익", "eps": "EPS", "roe": "ROE", "opm": "영업이익률"}
    out = {}
    for mode in ("annual", "quarter"):
        cols, rows = parse_rows(get(f"{M}/stock/{code}/finance/{mode}"))
        if not cols:
            continue
        if mode == "quarter":
            cols = cols[-5:]
        labels = []
        for c in cols:
            y, m = c["key"][:4], c["key"][4:6]
            lab = y if mode == "annual" else f"{y[2:]}.{(int(m) - 1) // 3 + 1}Q"
            labels.append(lab + ("E" if c["isConsensus"] == "Y" else ""))
        d = {"cols": labels}
        for k, title in keymap.items():
            d[k] = [num(rows.get(title, {}).get(c["key"], {}).get("value")) for c in cols]
        d["cfo"] = [None] * len(cols)
        d["cfi"] = [None] * len(cols)
        out[mode] = (d, cols)
    # 연간 현금흐름 (yfinance, 원 -> 억원)
    if "annual" in out and yf is not None:
        try:
            cf = yf.Ticker(code + mkt_suffix).cashflow
            d, cols = out["annual"]
            for i, c in enumerate(cols):
                for ts in cf.columns:
                    if str(ts.year) == c["key"][:4] and c["isConsensus"] != "Y":
                        for k, row in (("cfo", "Operating Cash Flow"), ("cfi", "Investing Cash Flow")):
                            v = cf.at[row, ts] if row in cf.index else None
                            if v == v and v is not None:  # NaN 제외
                                d[k][i] = round(float(v) / 1e8)
        except Exception:
            pass
    return {m: v[0] for m, v in out.items()}


def fmt_dt(s):
    """'202611011737' | '2026-10-29T06:52:29' -> '11.01 17:37'"""
    d = "".join(ch for ch in str(s) if ch.isdigit())
    return f"{d[4:6]}.{d[6:8]} {d[8:10]}:{d[10:12]}" if len(d) >= 12 else (f"{d[4:6]}.{d[6:8]}" if len(d) >= 8 else "")


def build_issues(code, name, integ):
    issues = []
    disc = get(f"{M}/stock/{code}/disclosure?page=1&pageSize=3") or []
    for x in disc[:1]:
        issues.append({"tag": "공시", "meta": f"{x.get('author', '공시')} · {fmt_dt(x['datetime'])}", "text": x["title"]})
    news = get(f"{M}/news/stock/{code}?pageSize=10&page=1") or []
    # 시황 기사보다 종목명이 제목에 들어간 기사를 먼저 보여준다 (sort는 안정 정렬이라 최신순 유지)
    news.sort(key=lambda cl: 0 if any(name in (it.get("title") or "") for it in (cl.get("items") or [])[:1]) else 1)
    seen = 0
    for cl in news:
        for it in (cl.get("items") or [])[:1]:
            url = it.get("mobileNewsUrl") or ""
            issues.append({"tag": "뉴스", "meta": f"{it.get('officeName', '')} · {fmt_dt(it['datetime'])}", "text": it["titleFull"] if it.get("titleFull") else it["title"],
                           "url": url if url.startswith("https://n.news.naver.com/") else ""})
            seen += 1
        if seen >= 2:
            break
    for x in (integ.get("researches") or [])[:1]:
        issues.append({"tag": "리포트", "meta": f"{x.get('bnm', '')} · {fmt_dt(x.get('wdt'))}", "text": x["tit"]})
    return issues


def build_stock(code):
    basic = get(f"{M}/stock/{code}/basic")
    integ = get(f"{M}/stock/{code}/integration")
    today = dt.datetime.now(KST).date()
    chart = get(f"{A}/chart/domestic/item/{code}/day?startDateTime={(today - dt.timedelta(days=760)).strftime('%Y%m%d')}&endDateTime={today.strftime('%Y%m%d')}")
    if not (basic and integ and chart and len(chart) > 30):
        log(f"skip {code} (데이터 부족)")
        return None
    chart = chart[-BARS_N:]
    bars = [[int(r["localDate"]), int(r["openPrice"]), int(r["highPrice"]), int(r["lowPrice"]), int(r["closePrice"])] for r in chart]
    price = bars[-1][4]
    # 등락은 네이버 공식 값(basic)을 쓴다. 차트 API의 전일 종가와 어긋나는 종목이 있다.
    chg = num(basic.get("compareToPreviousClosePrice"))
    pct = num(basic.get("fluctuationsRatio"))
    if chg is None or pct is None:
        chg, pct = price - bars[-2][4], (price - bars[-2][4]) / bars[-2][4] * 100
    info = {i["code"]: i for i in integ.get("totalInfos") or []}
    val = lambda k: (info.get(k) or {}).get("value")
    deals = (integ.get("dealTrendInfos") or [])[:5][::-1]
    flow = {"dates": [], "f": [], "i": [], "p": []}
    for d in deals:
        px = num(d["closePrice"]) or price
        flow["dates"].append(int(d["bizdate"]))
        for k, key in (("f", "foreignerPureBuyQuant"), ("i", "organPureBuyQuant"), ("p", "individualPureBuyQuant")):
            flow[k].append(round((num(d[key]) or 0) * px / 1e8))
    market = (basic.get("stockExchangeType") or {}).get("nameKor") or "코스피"
    suffix = ".KQ" if market == "코스닥" else ".KS"
    return {
        "code": code, "name": basic["stockName"], "market": market,
        "price": price, "chg": int(chg), "pct": round(pct, 2),
        "cap": val("marketValue"), "per": val("per"), "pbr": val("pbr"),
        "hi52": num(val("highPriceOf52Weeks")), "lo52": num(val("lowPriceOf52Weeks")),
        "volume": int(chart[-1].get("accumulatedTradingVolume") or 0),
        "foreignShare": (deals[-1].get("foreignerHoldRatio") if deals else None) or val("foreignRate"),
        "flow": flow, "issues": build_issues(code, basic["stockName"], integ), "fin": build_fin(code, suffix), "bars": bars,
    }


def top_codes(kind, market, n):
    d = get(f"{M}/stocks/{kind}/{market}?page=1&pageSize={n}") or {}
    return [s for s in d.get("stocks") or [] if s.get("stockEndType") == "stock"]


def build_ranking():
    pool = {}
    for kind in ("quantTop", "up", "down"):
        rows = []
        for mk in ("KOSPI", "KOSDAQ"):
            rows += top_codes(kind, mk, 40)
        key = {"quantTop": lambda s: -num(s["accumulatedTradingVolume"]),
               "up": lambda s: -num(s["fluctuationsRatio"]), "down": lambda s: num(s["fluctuationsRatio"])}[kind]
        rows = [s for s in rows if num(s["accumulatedTradingVolume"]) is not None]
        rows.sort(key=key)
        pool[kind] = [s["itemCode"] for s in rows[:RANK_N + 6]]  # 데이터 부족으로 빠지는 종목 대비 여유분
    return pool


def build_macro():
    rows = []
    for ticker, label, dec in (("^VIX", "VIX(변동성)", 2), ("DX-Y.NYB", "달러지수", 2), ("CL=F", "WTI 원유(선물)", 2), ("GC=F", "금(선물)", 1)):
        h = yf_hist(ticker)
        if h:
            c = h[0]
            rows.append({"label": label, "value": f"{c[-1]:,.{dec}f}", "pct": round((c[-1] - c[-2]) / c[-2] * 100, 2)})
    return rows


def build_sectors():
    d = get(f"{M}/stocks/industry?page=1&pageSize=100") or {}
    g = [x for x in d.get("groups") or [] if x.get("totalCount", 0) >= 8 and num(x.get("changeRate")) is not None]
    g.sort(key=lambda x: -num(x["changeRate"]))
    pick = g[:4] + g[-4:] if len(g) >= 8 else g
    return [{"name": x["name"], "pct": num(x["changeRate"])} for x in pick]


def main():
    countries = build_countries()
    if not countries:
        log("한국 지수 수집 실패 - 기존 파일 유지")
        return 1
    kospi = get(f"{M}/index/KOSPI/integration") or {}
    kosdaq = get(f"{M}/index/KOSDAQ/integration") or {}
    deal = lambda x: {"date": x["bizdate"], "개인": num(x["personalValue"]), "외국인": num(x["foreignValue"]), "기관": num(x["institutionalValue"])}
    ud = lambda x: {k: int(num(v) or 0) for k, v in (x.get("upDownStockInfo") or {}).items()}

    ranking = build_ranking()
    codes = list(DEFAULT_WATCH)
    for mk, n in (("KOSPI", TOP_KOSPI), ("KOSDAQ", TOP_KOSDAQ)):
        codes += [s["itemCode"] for s in top_codes("marketValue", mk, n * 2)[:n]]
    for lst in ranking.values():
        codes += lst
    codes = list(dict.fromkeys(codes))
    log(f"종목 {len(codes)}개 수집")
    with ThreadPoolExecutor(max_workers=8) as ex:
        built = list(ex.map(build_stock, codes))
    stocks = {s["code"]: s for s in built if s}

    def rank_rows(lst):
        rows = []
        for c in lst:
            s = stocks.get(c)
            if s:
                rows.append({"code": c, "price": s["price"], "pct": s["pct"], "vol": s["volume"], "f": s["flow"]["f"][-1], "i": s["flow"]["i"][-1]})
        return rows[:RANK_N]

    out = {
        "version": 1,
        "generatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "asOf": countries["KR"]["indices"][0]["date"],
        "countries": countries,
        "kospiFlows": deal(kospi.get("dealTrendInfo") or {}) if kospi.get("dealTrendInfo") else None,
        "kosdaqFlows": deal(kosdaq["dealTrendInfo"]) if kosdaq.get("dealTrendInfo") else None,
        "breadth": {"kospi": ud(kospi), "kosdaq": ud(kosdaq)},
        "macro": build_macro(),
        "sectors": build_sectors(),
        "ranking": {"volume": rank_rows(ranking["quantTop"]), "gain": rank_rows(ranking["up"]), "loss": rank_rows(ranking["down"])},
        "defaultWatch": [c for c in DEFAULT_WATCH if c in stocks],
        "stocks": stocks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    log(f"완료: {OUT} ({OUT.stat().st_size // 1024}KB, 종목 {len(stocks)}개, 기준일 {out['asOf']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
