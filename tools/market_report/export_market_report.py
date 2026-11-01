#!/usr/bin/env python3
"""마켓리포트용 실데이터 수집 -> docs/data/market_report.json(개요) + docs/data/mr/(종목 색인·상세)

소스
  - 네이버 증권 모바일 API: 한국 지수/국채, 종목 시세·차트·수급·재무·뉴스·공시·리포트, 순위, 업종
  - yfinance: 해외 지수, 환율, 달러지수, 종목 현금흐름
실패한 항목은 건너뛰고(없는 값은 JSON에서 생략), 핵심 데이터(한국 지수)가 없으면
기존 파일을 덮어쓰지 않고 종료 코드 1로 끝난다.
"""
import argparse
import json
import os
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
# 저장소가 불어나지 않도록 CI에서는 MR_DATA_DIR로 market-data 브랜치 작업 폴더를 지정한다.
# 지정하지 않으면(로컬 미리보기) docs/data 에 쓰고, 그 경로는 .gitignore 로 커밋에서 제외된다.
DATA = Path(os.environ["MR_DATA_DIR"]).resolve() if os.environ.get("MR_DATA_DIR") else ROOT / "docs" / "data"
OUT = DATA / "market_report.json"       # 개요(지수·수급·순위·업종)
INDEX = DATA / "mr" / "index.json"      # 검색·목록용 종목 색인
STOCK_DIR = DATA / "mr" / "s"           # 종목별 상세(차트·재무·이슈) — 화면에서 필요할 때 불러온다
M = "https://m.stock.naver.com/api"
A = "https://api.stock.naver.com"
KST = dt.timezone(dt.timedelta(hours=9))
DEFAULT_WATCH = ["005930", "000660", "042700", "196170"]
N_KOSPI, N_KOSDAQ, N_NASDAQ, N_NYSE = 200, 250, 150, 150  # 시장별 시총 상위 N개
CF_TOP = 150  # 현금흐름(yfinance, 느림)은 한국 시총 상위 N개에만
RANK_N, SPARK_N, BARS_N = 8, 24, 450

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


# ---------------------------------------------------------------- 종목 공통
def parse_rows(fin):
    info = (fin or {}).get("financeInfo") or {}
    cols = info.get("trTitleList") or []
    rows = {r["title"]: r["columns"] for r in info.get("rowList") or []}
    return cols, rows


def build_fin_kr(code, mkt_suffix, with_cf):
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
        d = {"cols": labels, "unit": "억원"}
        for k, title in keymap.items():
            d[k] = [num(rows.get(title, {}).get(c["key"], {}).get("value")) for c in cols]
        d["cfo"] = [None] * len(cols)
        d["cfi"] = [None] * len(cols)
        out[mode] = (d, cols)
    # 연간 현금흐름 (yfinance, 원 -> 억원). 호출이 느려 시총 상위 종목에만 붙인다.
    if with_cf and "annual" in out and yf is not None:
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


def build_fin_us(code):
    """미국 종목: 네이버 월드 재무(백만 달러). EPS·ROE·현금흐름은 소스에 없어 비운다."""
    keymap = {"rev": "매출액", "op": "EBIT", "ni": "당기순이익"}
    out = {}
    for mode in ("annual", "quarter"):
        fin = get(f"{A}/stock/{code}/finance/{mode}")
        cols = (fin or {}).get("trTitleList") or []
        rows = {r["title"]: r["columns"] for r in (fin or {}).get("rowList") or []}
        if not cols:
            continue
        cols = cols[-5:] if mode == "quarter" else cols[-5:]
        labels = []
        for c in cols:
            k = c["key"]  # '2025.09.27'
            lab = k[:4] if mode == "annual" else f"{k[2:4]}.{k[5:7]}"
            labels.append(lab + ("E" if c["isConsensus"] == "Y" else ""))
        d = {"cols": labels, "unit": "백만 달러"}
        for key, title in keymap.items():
            d[key] = [num(rows.get(title, {}).get(c["key"], {}).get("value")) for c in cols]
        d["opm"] = [round(o / r * 100, 1) if o is not None and r else None for o, r in zip(d["op"], d["rev"])]
        for k in ("eps", "roe", "cfo", "cfi"):
            d[k] = [None] * len(cols)
        out[mode] = d
    return out


def fmt_dt(s):
    """'202611011737' | '2026-10-29T06:52:29' -> '11.01 17:37'"""
    d = "".join(ch for ch in str(s) if ch.isdigit())
    return f"{d[4:6]}.{d[6:8]} {d[8:10]}:{d[10:12]}" if len(d) >= 12 else (f"{d[4:6]}.{d[6:8]}" if len(d) >= 8 else "")


def news_issues(url, name, limit=2):
    news = get(url) or []
    news = [cl for cl in news if isinstance(cl, dict) and cl.get("items")]
    # 시황 기사보다 종목명이 제목에 들어간 기사를 먼저 보여준다 (sort는 안정 정렬이라 최신순 유지)
    news.sort(key=lambda cl: 0 if name and name in (cl["items"][0].get("title") or "") else 1)
    out = []
    for cl in news[:limit]:
        it = cl["items"][0]
        link = it.get("mobileNewsUrl") or ""
        out.append({"tag": "뉴스", "meta": f"{it.get('officeName', '')} · {fmt_dt(it['datetime'])}",
                    "text": it.get("titleFull") or it["title"], "url": link if link.startswith("https://n.news.naver.com/") else ""})
    return out


def chart_bars(url_tpl, code):
    today = dt.datetime.now(KST).date()
    chart = get(url_tpl.format(code=code, s=(today - dt.timedelta(days=760)).strftime("%Y%m%d"), e=today.strftime("%Y%m%d")))
    if not chart or len(chart) < 30:
        return None, None
    chart = chart[-BARS_N:]
    rnd = (lambda v: int(round(v))) if url_tpl is KR_CHART else (lambda v: round(float(v), 2))
    bars = [[int(r["localDate"]), rnd(r["openPrice"]), rnd(r["highPrice"]), rnd(r["lowPrice"]), rnd(r["closePrice"])] for r in chart]
    return bars, int(chart[-1].get("accumulatedTradingVolume") or 0)


KR_CHART = A + "/chart/domestic/item/{code}/day?startDateTime={s}&endDateTime={e}"
US_CHART = A + "/chart/foreign/item/{code}/day?startDateTime={s}&endDateTime={e}"


def build_kr(row, with_cf):
    """row: 네이버 시총 리스트 한 줄. 반환: (index_row, detail)"""
    code = row["itemCode"]
    integ = get(f"{M}/stock/{code}/integration")
    bars, vol = chart_bars(KR_CHART, code)
    if not (integ and bars):
        log(f"skip {code} (데이터 부족)")
        return None
    price = bars[-1][4]
    chg, pct = num(row.get("compareToPreviousClosePrice")), num(row.get("fluctuationsRatio"))
    if chg is None or pct is None:  # 등락은 네이버 공식 값. 없을 때만 차트로 계산
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
    name = row["stockName"]
    market = (row.get("stockExchangeType") or {}).get("nameKor") or "코스피"
    issues = []
    for x in (get(f"{M}/stock/{code}/disclosure?page=1&pageSize=3") or [])[:1]:
        issues.append({"tag": "공시", "meta": f"{x.get('author', '공시')} · {fmt_dt(x['datetime'])}", "text": x["title"]})
    issues += news_issues(f"{M}/news/stock/{code}?pageSize=10&page=1", name)
    for x in (integ.get("researches") or [])[:1]:
        issues.append({"tag": "리포트", "meta": f"{x.get('bnm', '')} · {fmt_dt(x.get('wdt'))}", "text": x["tit"]})
    detail = {
        "cap": val("marketValue"), "per": val("per"), "pbr": val("pbr"),
        "hi52": num(val("highPriceOf52Weeks")), "lo52": num(val("lowPriceOf52Weeks")), "volume": vol,
        "extra": ["외국인 지분율", (deals[-1].get("foreignerHoldRatio") if deals else None) or val("foreignRate")],
        "flow": flow, "issues": issues, "fin": build_fin_kr(code, ".KQ" if market == "코스닥" else ".KS", with_cf), "bars": bars,
    }
    idx = [code, name, market, price, int(chg), round(pct, 2), flow["f"][-1] if flow["f"] else None, flow["i"][-1] if flow["i"] else None, code, None, "KRW"]
    return idx, detail


def build_us(row):
    code = row["reutersCode"]
    basic = get(f"{A}/stock/{code}/basic")
    bars, vol = chart_bars(US_CHART, code)
    if not (basic and bars):
        log(f"skip {code} (데이터 부족)")
        return None
    info = {i["code"]: i for i in basic.get("stockItemTotalInfos") or []}
    val = lambda k: (info.get(k) or {}).get("value")
    price = num(basic.get("closePrice")) or bars[-1][4]
    chg, pct = num(basic.get("compareToPreviousClosePrice")), num(basic.get("fluctuationsRatio"))
    if chg is None or pct is None:
        chg, pct = price - bars[-2][4], (price - bars[-2][4]) / bars[-2][4] * 100
    name = basic.get("stockName") or row.get("stockName")
    sym = basic.get("symbolCode") or code.split(".")[0]
    market = (basic.get("stockExchangeType") or {}).get("name") or row.get("_ex") or "NASDAQ"
    cap = val("marketValue")
    detail = {
        "cap": cap, "per": val("per"), "pbr": val("pbr"),
        "hi52": num(val("highPriceOf52Weeks")), "lo52": num(val("lowPriceOf52Weeks")), "volume": vol,
        "extra": ["배당수익률", val("dividendYieldRatio")], "flow": None,
        "issues": news_issues(f"{A}/news/stock/{code}?pageSize=10&page=1", name), "fin": build_fin_us(code), "bars": bars,
    }
    idx = [code, name, market, round(price, 2), round(chg, 2), round(pct, 2), None, None, sym, basic.get("stockNameEng"), "USD"]
    return idx, detail


# ---------------------------------------------------------------- 유니버스·순위·업종
def list_rows(url_tpl, n, stock_key="stocks"):
    """페이지를 넘기며 보통주(stockEndType == stock) n개를 모은다."""
    rows, page = [], 1
    while len(rows) < n and page <= 12:
        d = get(url_tpl.format(page=page, size=100)) or {}
        got = d.get(stock_key) or []
        if not got:
            break
        rows += [s for s in got if s.get("stockEndType") == "stock"]
        page += 1
    return rows[:n]


def build_ranking():
    pool = {}
    for kind in ("quantTop", "up", "down"):
        rows = []
        for mk in ("KOSPI", "KOSDAQ"):
            d = get(f"{M}/stocks/{kind}/{mk}?page=1&pageSize=40") or {}
            rows += [s for s in d.get("stocks") or [] if s.get("stockEndType") == "stock"]
        key = {"quantTop": lambda s: -num(s["accumulatedTradingVolume"]),
               "up": lambda s: -num(s["fluctuationsRatio"]), "down": lambda s: num(s["fluctuationsRatio"])}[kind]
        rows = [s for s in rows if num(s["accumulatedTradingVolume"]) is not None]
        rows.sort(key=key)
        pool[kind] = rows[:RANK_N + 6]  # 데이터 부족으로 빠지는 종목 대비 여유분
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


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


KR_MARKETS = ("코스피", "코스닥")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["all", "kr", "us"], default="all", help="상세 데이터를 새로 받을 시장 (나머지는 기존 파일 유지)")
    ap.add_argument("--small", action="store_true", help="스모크 테스트: 시장당 10종목만")
    args = ap.parse_args()
    n_kospi, n_kosdaq, n_nas, n_nyse = (10, 10, 10, 10) if args.small else (N_KOSPI, N_KOSDAQ, N_NASDAQ, N_NYSE)

    countries = build_countries()
    if not countries:
        log("한국 지수 수집 실패 - 기존 파일 유지")
        return 1
    prev = load_json(OUT) or {}
    old_idx = (load_json(INDEX) or {}).get("stocks") or []
    new_rows, details = [], {}

    do_kr, do_us = args.only in ("all", "kr"), args.only in ("all", "us")
    ranking_pool = build_ranking() if do_kr else None

    if do_kr:
        rows = list_rows(f"{M}/stocks/marketValue/KOSPI?page={{page}}&pageSize={{size}}", n_kospi)
        rows += list_rows(f"{M}/stocks/marketValue/KOSDAQ?page={{page}}&pageSize={{size}}", n_kosdaq)
        seen = {r["itemCode"] for r in rows}
        wanted = {c: None for c in DEFAULT_WATCH if c not in seen}
        for lst in ranking_pool.values():
            for s in lst:
                if s["itemCode"] not in seen:
                    seen.add(s["itemCode"])
                    rows.append(s)
        for c in wanted:  # 기본 관심종목이 상위에 없을 때만 개별 조회
            b = get(f"{M}/stock/{c}/basic")
            if b and c not in seen:
                b["itemCode"] = c
                rows.append(b)
        log(f"한국 {len(rows)}종목 수집")
        with ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(lambda ir: build_kr(ir[1], ir[0] < CF_TOP), enumerate(rows)))
        for r in res:
            if r:
                new_rows.append(r[0]); details[r[0][0]] = r[1]
    if do_us:
        rows = []
        for ex_name, n in (("NASDAQ", n_nas), ("NYSE", n_nyse)):
            got = list_rows(f"{A}/stock/exchange/{ex_name}/marketValue?page={{page}}&pageSize={{size}}", n)
            for g in got:
                g["_ex"] = ex_name
            rows += got
        log(f"미국 {len(rows)}종목 수집")
        with ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(build_us, rows))
        for r in res:
            if r:
                new_rows.append(r[0]); details[r[0][0]] = r[1]

    # 이번에 안 받은 시장은 기존 색인을 그대로 유지
    keep = []
    if args.only == "kr":
        keep = [r for r in old_idx if r[2] not in KR_MARKETS]
    elif args.only == "us":
        keep = [r for r in old_idx if r[2] in KR_MARKETS]
    index_rows = keep + new_rows
    if not index_rows:
        log("종목 색인이 비어 있음 - 기존 파일 유지")
        return 1
    by_code = {r[0]: r for r in index_rows}

    # 새로 받은 상세 저장 + 색인에서 빠진 종목 파일 정리
    for code, d in details.items():
        dump(STOCK_DIR / f"{code}.json", d)
    live_codes = set(by_code)
    for f in STOCK_DIR.glob("*.json") if STOCK_DIR.exists() else []:
        if f.stem not in live_codes:
            f.unlink()
    dump(INDEX, {"generatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "stocks": index_rows})

    if do_kr:
        kospi = get(f"{M}/index/KOSPI/integration") or {}
        kosdaq = get(f"{M}/index/KOSDAQ/integration") or {}
        deal = lambda x: {"date": x["bizdate"], "개인": num(x["personalValue"]), "외국인": num(x["foreignValue"]), "기관": num(x["institutionalValue"])}
        ud = lambda x: {k: int(num(v) or 0) for k, v in (x.get("upDownStockInfo") or {}).items()}

        def rank_rows(lst):
            out = []
            for s in lst:
                r = by_code.get(s["itemCode"])
                if r:
                    out.append({"code": r[0], "name": r[1], "price": r[3], "pct": r[5], "vol": int(num(s.get("accumulatedTradingVolume")) or 0), "f": r[6], "i": r[7]})
            return out[:RANK_N]

        overview = {
            "kospiFlows": deal(kospi["dealTrendInfo"]) if kospi.get("dealTrendInfo") else None,
            "kosdaqFlows": deal(kosdaq["dealTrendInfo"]) if kosdaq.get("dealTrendInfo") else None,
            "breadth": {"kospi": ud(kospi), "kosdaq": ud(kosdaq)},
            "sectors": build_sectors(),
            "ranking": {"volume": rank_rows(ranking_pool["quantTop"]), "gain": rank_rows(ranking_pool["up"]), "loss": rank_rows(ranking_pool["down"])},
        }
    else:  # 미국만 갱신하는 실행: 한국 장 관련 값은 직전 파일을 유지
        overview = {k: prev.get(k) for k in ("kospiFlows", "kosdaqFlows", "breadth", "sectors", "ranking")}
        overview["sectors"] = overview["sectors"] or []
        overview["ranking"] = overview["ranking"] or {"volume": [], "gain": [], "loss": []}
        overview["breadth"] = overview["breadth"] or {"kospi": {}, "kosdaq": {}}

    out = {
        "version": 2,
        "generatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "asOf": countries["KR"]["indices"][0]["date"],
        "countries": countries,
        "macro": build_macro(),
        "defaultWatch": [c for c in DEFAULT_WATCH if c in by_code],
        **overview,
    }
    dump(OUT, out)
    n_kr = sum(1 for r in index_rows if r[2] in KR_MARKETS)
    log(f"완료: 개요 {OUT.stat().st_size // 1024}KB · 색인 {len(index_rows)}종목(한국 {n_kr}, 미국 {len(index_rows) - n_kr}) · 기준일 {out['asOf']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
