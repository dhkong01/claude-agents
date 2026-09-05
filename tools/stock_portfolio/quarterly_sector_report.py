#!/usr/bin/env python3
"""분기별 강세 섹터 분석 + HTML 리포트 (US/KR 종목 포함)"""
import json
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

CACHE   = Path(__file__).parent / "cache"
OUT_DIR = Path(__file__).parents[4] / "agent_Stocks"

SECTOR_ETFS = {
    "Technology":        "XLK",
    "Financials":        "XLF",
    "Energy":            "XLE",
    "Healthcare":        "XLV",
    "Industrials":       "XLI",
    "Communication":     "XLC",
    "Consumer Disc.":    "XLY",
    "Real Estate":       "XLRE",
    "Utilities":         "XLU",
    "Materials":         "XLB",
    "Consumer Staples":  "XLP",
}

KR_STOCKS = {
    "Technology":       [("005930.KS","삼성전자"),("000660.KS","SK하이닉스"),("035420.KS","NAVER")],
    "Financials":       [("105560.KS","KB금융"),("055550.KS","신한지주"),("086790.KS","하나금융")],
    "Energy":           [("096770.KS","SK이노베이션"),("010950.KS","S-Oil"),("267250.KS","HD현대")],
    "Healthcare":       [("068270.KS","셀트리온"),("207940.KS","삼성바이오"),("128940.KS","한미약품")],
    "Industrials":      [("042660.KS","한화오션"),("012450.KS","한화에어로"),("011200.KS","HMM")],
    "Communication":    [("017670.KS","SK텔레콤"),("030200.KS","KT"),("035720.KS","카카오")],
    "Consumer Disc.":   [("000240.KS","한국타이어"),("003490.KS","대한항공"),("271560.KS","오리온")],
    "Real Estate":      [("395400.KS","SK리츠"),("293940.KS","신한알파리츠"),("088980.KS","맥쿼리인프라")],
    "Utilities":        [("015760.KS","한국전력"),("034020.KS","두산에너빌리티"),("069620.KS","대웅제약")],
    "Materials":        [("010130.KS","고려아연"),("009830.KS","한화솔루션"),("011790.KS","SKC")],
    "Consumer Staples": [("097950.KS","CJ제일제당"),("051900.KS","LG생활건강"),("139480.KS","이마트")],
}


def quarter_label(d: date) -> str:
    return f"{d.year}-Q{(d.month-1)//3+1}"


def quarter_start(d: date) -> date:
    m = ((d.month - 1) // 3) * 3 + 1
    return date(d.year, m, 1)


def qtd_return(hist, q_start: date) -> float | None:
    if hist is None or hist.empty:
        return None
    idx = hist.index.normalize()
    base = hist[idx >= str(q_start)]
    # yfinance가 장 마감 전 당일을 NaN 자리표시자 행으로 포함시키는 경우가 있어
    # iloc[0]/iloc[-1]이 NaN을 가리키지 않도록 방어적으로 제거한다.
    base = base.dropna(subset=["Close"])
    if base.empty:
        return None
    p0 = float(base["Close"].iloc[0])
    p1 = float(base["Close"].iloc[-1])
    return (p1 / p0 - 1) * 100 if p0 else None


def get_sector_rankings(today: date) -> list[dict]:
    q_start = quarter_start(today)
    tickers = list(SECTOR_ETFS.values())
    raw = yf.download(tickers, start=str(q_start - timedelta(days=5)), auto_adjust=True, progress=False)
    rows = []
    for sector, etf in SECTOR_ETFS.items():
        try:
            hist = raw["Close"][[etf]] if "Close" in raw.columns else raw[[etf]]
            hist = hist.rename(columns={etf: "Close"})
            ret = qtd_return(hist, q_start)
        except Exception:
            ret = None
        rows.append({"sector": sector, "etf": etf, "qtd": ret})
    rows.sort(key=lambda x: x["qtd"] or -999, reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


def get_us_stocks_by_sector() -> dict[str, list]:
    result: dict[str, list] = {}
    try:
        data = json.loads((CACHE / "canslim_top10.json").read_text())
        for s in data.get("top10", []):
            sec = s.get("sector", "Unknown")
            result.setdefault(sec, []).append({
                "ticker": s["ticker"],
                "canslim": s.get("canslim_score", 0),
                "rs": round(s.get("rs_rating", 0), 1),
                "price": s.get("price", 0),
            })
    except Exception:
        pass
    # supplement with rs90
    try:
        rs_data = json.loads((CACHE / "rs90.json").read_text())
        known = {t for lst in result.values() for t in [s["ticker"] for s in lst]}
        extra = [s["ticker"] for s in rs_data.get("stocks", []) if s["ticker"] not in known][:20]
        if extra:
            infos = yf.download(extra, period="1d", progress=False)
            for t in extra:
                try:
                    sec = yf.Ticker(t).info.get("sector", "Unknown")
                    rs  = next((s["rs_rating"] for s in rs_data["stocks"] if s["ticker"]==t), 0)
                    result.setdefault(sec, []).append({"ticker": t, "canslim": 0, "rs": round(rs,1), "price": 0})
                except Exception:
                    pass
    except Exception:
        pass
    return result


def get_kr_returns(sector: str, q_start: date) -> list[dict]:
    pairs = KR_STOCKS.get(sector, [])
    if not pairs:
        return []
    tickers = [t for t, _ in pairs]
    try:
        raw = yf.download(tickers, start=str(q_start - timedelta(days=5)),
                          auto_adjust=True, progress=False)
        out = []
        for t, name in pairs:
            try:
                if len(tickers) == 1:
                    hist = raw[["Close"]].rename(columns={"Close": "Close"})
                else:
                    hist = raw["Close"][[t]].rename(columns={t: "Close"})
                ret = qtd_return(hist, q_start)
            except Exception:
                ret = None
            out.append({"ticker": t.replace(".KS",""), "name": name, "qtd": ret})
        return out
    except Exception:
        return [{"ticker": t.replace(".KS",""), "name": name, "qtd": None} for t, name in pairs]


def _ret_str(v) -> str:
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def _ret_class(v) -> str:
    if v is None:
        return ""
    return "hot" if v > 5 else ("warm" if v > 0 else "cold")


def build_html(sector_ranks, us_by_sector, top10, macro) -> str:
    today = date.today()
    q     = quarter_label(today)
    phase = macro.get("phase", "?")
    sig   = macro.get("signals", {})
    vix   = sig.get("vix_level", "?")
    y10   = sig.get("yield10y", "?")
    rec   = ", ".join(macro.get("recommended_sectors", [])[:3])
    q_start = quarter_start(today)

    # sector rows
    sr = ""
    for r in sector_ranks:
        v     = r["qtd"]
        cls   = _ret_class(v)
        ret_s = _ret_str(v)
        pct   = min(abs(v or 0), 20) / 20 * 100
        bar   = f'<div class="bar-wrap"><div class="bar {"neg" if (v or 0)<0 else ""}" style="width:{pct:.0f}%"></div></div>'
        status = "🔥 과열" if (v or 0) > 10 else ("🟢 강세" if (v or 0) > 3 else ("🟡 중립" if (v or 0) >= 0 else "🔴 약세"))
        sr += f'<tr><td>{r["rank"]}</td><td>{r["sector"]}</td><td>{r["etf"]}</td><td class="{cls}">{ret_s}</td><td>{bar}</td><td>{status}</td></tr>\n'

    # sector cards (top 5)
    cards = ""
    for r in sector_ranks[:5]:
        sec   = r["sector"]
        us_st = us_by_sector.get(sec, [])[:3]
        kr_st = get_kr_returns(sec, q_start)

        us_rows = "".join(
            f'<div class="stock-row"><span class="name">{s["ticker"]}</span>'
            f'<span class="ret" style="color:{"#22c55e" if s["rs"]>=90 else "#f59e0b"}">RS {s["rs"]} · CS {s["canslim"]}</span></div>'
            for s in us_st
        ) or "<div style='color:#475569;font-size:.8rem'>데이터 없음</div>"
        kr_rows = "".join(
            f'<div class="stock-row"><span class="name">{k["name"]}</span>'
            f'<span class="ret {_ret_class(k["qtd"])}">{_ret_str(k["qtd"])}</span></div>'
            for k in kr_st
        ) or "<div style='color:#475569;font-size:.8rem'>데이터 없음</div>"

        cards += f"""<div class="card">
<div class="card-title">#{r['rank']} {sec} <span class="{_ret_class(r['qtd'])}" style="font-size:.85rem">{_ret_str(r['qtd'])}</span></div>
<div class="card-sub">ETF: {r['etf']}</div>
<div class="stock-grid">
  <div class="stock-box"><h4>🇺🇸 미국 (CANSLIM 상위)</h4>{us_rows}</div>
  <div class="stock-box"><h4>🇰🇷 국내 대표주</h4>{kr_rows}</div>
</div></div>\n"""

    # top10 rows
    t10 = ""
    for i, s in enumerate(top10, 1):
        score = s.get("final_score", 0)
        bar_w = min(int(score / 100 * 80), 80)
        t10 += (f'<tr><td class="rank">{i}</td><td>{s["ticker"]}</td>'
                f'<td>{s.get("canslim_score",0)}/70</td>'
                f'<td>{round(s.get("rs_rating",0),1)}</td>'
                f'<td>{s.get("sector","?")}</td>'
                f'<td>{score:.1f}<span class="score-bar" style="width:{bar_w}px"></span></td></tr>\n')

    return HTML_TMPL.format(
        quarter=q, generated=today.isoformat(),
        phase=phase, vix=vix, yield10y=y10, rec_sectors=rec,
        sector_rows=sr, sector_cards=cards, top10_rows=t10,
    )


HTML_TMPL = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>분기 섹터 리포트 {quarter}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:16px;font-size:14px}}
h1{{font-size:1.3rem;margin-bottom:3px;color:#f8fafc}}
h2{{font-size:.95rem;margin:20px 0 8px;color:#94a3b8;border-bottom:1px solid #1e293b;padding-bottom:4px}}
.sub{{color:#64748b;font-size:.8rem;margin-bottom:14px}}
.macro-bar{{display:flex;gap:10px;margin-bottom:18px;flex-wrap:wrap}}
.chip{{background:#1e293b;border-radius:6px;padding:6px 12px;font-size:.82rem}}
.chip span{{font-weight:700;color:#38bdf8}}
table{{width:100%;border-collapse:collapse;font-size:.85rem;margin-bottom:6px}}
th{{background:#1e293b;padding:7px 9px;text-align:left;color:#94a3b8;font-weight:600}}
td{{padding:6px 9px;border-bottom:1px solid #1a2540}}
.bw{{background:#1e293b;border-radius:3px;height:8px;width:110px;display:inline-block;vertical-align:middle}}
.bar{{height:100%;border-radius:3px;background:#22c55e}}
.bar.neg{{background:#ef4444}}
.hot{{color:#22c55e;font-weight:700}}
.warm{{color:#f59e0b;font-weight:700}}
.cold{{color:#ef4444;font-weight:700}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-bottom:6px}}
.card{{background:#1e293b;border-radius:8px;padding:12px}}
.card-title{{font-weight:700;margin-bottom:1px}}
.card-sub{{color:#64748b;font-size:.75rem;margin-bottom:8px}}
.sgrid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.sbox{{background:#0f172a;border-radius:5px;padding:8px}}
.sbox h4{{font-size:.75rem;color:#64748b;margin-bottom:5px}}
.srow{{display:flex;justify-content:space-between;padding:2px 0;font-size:.8rem}}
.rank{{font-weight:700;color:#38bdf8}}
.sbar{{display:inline-block;height:5px;border-radius:2px;background:#6366f1;vertical-align:middle;margin-left:5px}}
.foot{{color:#334155;font-size:.72rem;margin-top:14px;text-align:right}}
</style></head><body>
<h1>📊 분기 섹터 강세 리포트</h1>
<div class="sub">{quarter} · {generated} · IBD CANSLIM 기준</div>
<div class="macro-bar">
  <div class="chip">시장 국면 <span>{phase}</span></div>
  <div class="chip">VIX <span>{vix}</span></div>
  <div class="chip">10년 금리 <span>{yield10y}%</span></div>
  <div class="chip">추천 섹터 <span>{rec_sectors}</span></div>
</div>
<h2>전체 섹터 성과 순위 (QTD)</h2>
<table><tr><th>#</th><th>섹터</th><th>ETF</th><th>QTD 수익률</th><th>차트</th><th>상태</th></tr>
{sector_rows}</table>
<h2>강세 섹터 Top5 · 주요 종목</h2>
<div class="cards">{sector_cards}</div>
<h2>🏆 오케스트레이터 최우량 TOP 10</h2>
<table><tr><th>#</th><th>티커</th><th>CANSLIM</th><th>RS</th><th>섹터</th><th>종합점수</th></tr>
{top10_rows}</table>
<div class="foot">🤖 Yahoo Finance · IBD RS · {generated}</div>
</body></html>"""


def run(top10: list | None = None) -> Path:
    today = date.today()
    print("[분기 섹터 리포트] 섹터 수익률 계산 중...")
    sector_ranks = get_sector_rankings(today)

    print("[분기 섹터 리포트] 종목 매핑 중...")
    us_by_sector  = get_us_stocks_by_sector()

    macro = {}
    try:
        macro = json.loads((CACHE / "macro.json").read_text())
    except Exception:
        pass

    if top10 is None:
        top10 = []
        try:
            data = json.loads((CACHE / "canslim_top10.json").read_text())
            top10 = data.get("top10", [])[:10]
        except Exception:
            pass

    html  = build_html(sector_ranks, us_by_sector, top10, macro)
    q     = quarter_label(today)
    OUT_DIR.mkdir(exist_ok=True)
    out   = OUT_DIR / f"quarterly_{q}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[분기 섹터 리포트] 저장: {out}")

    # cache sector rankings
    (CACHE / "sector_rankings.json").write_text(
        json.dumps({"date": today.isoformat(), "rankings": sector_ranks}, indent=2)
    )
    return out


if __name__ == "__main__":
    run()
