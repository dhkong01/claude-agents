"""
추세 추종 HTML 리포트 생성기
trend_result_YYYY-MM-DD.json → reports/trend_report_YYYY-MM-DD.html
"""
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR   = Path(__file__).parent
CACHE_DIR  = BASE_DIR / "cache"
REPORT_DIR = BASE_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)


# ─── 데이터 로더 ──────────────────────────────────────────────

def load_result(date: str | None = None) -> dict:
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    p = CACHE_DIR / f"trend_result_{date}.json"
    if not p.exists():
        raise FileNotFoundError(f"결과 파일 없음: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_vcp() -> list[dict]:
    p = CACHE_DIR / "vcp_top20.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("stocks", [])


def load_canslim() -> list[dict]:
    p = CACHE_DIR / "canslim_top10.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("top10", [])


# ─── 헬퍼 ────────────────────────────────────────────────────

def _pct(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def _donchian_bar(current: float, lower: float, upper: float) -> str:
    """현재가의 Donchian 채널 내 위치를 진행바로 표현 (0%=손절, 100%=돌파선)"""
    span = upper - lower
    if span <= 0:
        pos = 50
    else:
        pos = max(0, min(100, int((current - lower) / span * 100)))
    color = "#22c55e" if pos >= 90 else ("#f59e0b" if pos >= 50 else "#ef4444")
    return f"""
      <div class="dc-bar-wrap">
        <span class="dc-label">손절 ${lower:.2f}</span>
        <div class="dc-bar">
          <div class="dc-fill" style="width:{pos}%;background:{color}"></div>
          <div class="dc-marker" style="left:{pos}%"></div>
        </div>
        <span class="dc-label">돌파 ${upper:.2f}</span>
      </div>
      <div class="dc-pos-text" style="color:{color}">채널 내 위치 {pos}%</div>"""


def _signal_badge(signal: str) -> str:
    cfg = {
        "BREAKOUT": ("badge-breakout", "🚀 BREAKOUT"),
        "EXIT":     ("badge-exit",     "⚠ EXIT"),
        "HOLD":     ("badge-hold",     "HOLD"),
    }
    cls, label = cfg.get(signal, ("badge-hold", signal))
    return f'<span class="badge {cls}">{label}</span>'


def _risk_badge(level: str) -> str:
    cfg = {
        "HIGH":   ("risk-high",   "🔴 HIGH"),
        "MEDIUM": ("risk-medium", "🟡 MEDIUM"),
        "LOW":    ("risk-low",    "🟢 LOW"),
    }
    cls, label = cfg.get(level, ("risk-medium", level))
    return f'<span class="risk-badge {cls}">{label}</span>'


def _impact_badge(impact: str) -> str:
    if impact == "ELEVATED":
        return '<span class="impact elevated">ELEVATED</span>'
    return '<span class="impact watch">WATCH</span>'


# ─── HTML 섹션 빌더 ──────────────────────────────────────────

def _section_geo(geo: dict) -> str:
    level  = geo.get("risk_level", "?")
    score  = geo.get("risk_score", 0)
    bias   = geo.get("market_bias", "?")
    events = geo.get("top_risk_events", [])
    impacts = geo.get("sector_impacts", {})
    rec    = geo.get("recommendation", "")

    bias_color = {"RISK_ON": "#22c55e", "NEUTRAL": "#f59e0b", "RISK_OFF": "#ef4444"}.get(bias, "#94a3b8")

    impact_html = "".join(
        f'<div class="impact-item"><span class="sector-name">{s}</span> {_impact_badge(v)}</div>'
        for s, v in impacts.items()
    ) or "<p class='muted'>감지된 섹터 영향 없음</p>"

    events_html = "".join(
        f"<li>{e}</li>" for e in events[:3]
    ) or "<li class='muted'>주요 이벤트 없음</li>"

    gauge_deg = int(score / 10 * 180)
    gauge_color = "#ef4444" if score >= 6 else ("#f59e0b" if score >= 3 else "#22c55e")

    return f"""
    <section class="card geo-card">
      <h2>🌍 지정학 리스크 분석</h2>
      <div class="geo-grid">
        <div class="geo-score-wrap">
          <div class="gauge">
            <svg viewBox="0 0 120 70" class="gauge-svg">
              <path d="M10,60 A50,50 0 0,1 110,60" fill="none" stroke="#1e293b" stroke-width="12"/>
              <path d="M10,60 A50,50 0 0,1 110,60" fill="none" stroke="{gauge_color}"
                    stroke-width="12" stroke-dasharray="157" stroke-dashoffset="{157 - int(157 * score / 10)}"/>
            </svg>
            <div class="gauge-value" style="color:{gauge_color}">{score}</div>
            <div class="gauge-label">/ 10</div>
          </div>
          <div class="geo-badges">
            {_risk_badge(level)}
            <span class="bias-badge" style="color:{bias_color}">▶ {bias}</span>
          </div>
        </div>
        <div class="geo-details">
          <div class="impact-grid">{impact_html}</div>
          <div class="geo-rec">{rec}</div>
        </div>
        <div class="geo-events">
          <h4>주요 지정학 이벤트</h4>
          <ul>{events_html}</ul>
        </div>
      </div>
    </section>"""


def _section_top5(top5: list[dict], geo: dict) -> str:
    if not top5:
        return '<section class="card"><h2>🏆 Donchian TOP 5</h2><p class="muted">데이터 없음</p></section>'

    rows = ""
    for i, s in enumerate(top5, 1):
        ticker  = s.get("ticker", "?")
        current = s.get("current_price", 0)
        upper   = s.get("donchian_upper", 0)
        lower   = s.get("donchian_lower", 0)
        signal  = s.get("donchian_signal", "HOLD")
        score   = s.get("final_score", 0)
        rs      = s.get("rs_rating", 0)
        canslim = s.get("canslim_score", 0)
        vcp     = s.get("vcp_score", 0)
        sector  = s.get("sector", "")
        in_both = s.get("in_both", False)
        dist_u  = s.get("dist_to_upper_pct", 0)
        dist_l  = s.get("dist_to_lower_pct", 0)
        pivot   = s.get("pivot")

        bar     = _donchian_bar(current, lower, upper)
        badge   = _signal_badge(signal)
        both_tag = '<span class="both-tag">CS+VCP</span>' if in_both else ""
        pivot_html = f'<span class="pivot-line">Pivot ${pivot:.2f}</span>' if pivot else ""

        rows += f"""
        <div class="top5-card rank-{i}">
          <div class="top5-header">
            <span class="rank-num">#{i}</span>
            <span class="ticker-name">{ticker}</span>
            {badge}
            {both_tag}
            <span class="sector-tag">{sector}</span>
            {pivot_html}
          </div>
          <div class="top5-price">
            <div class="price-main">${current:,.2f}</div>
            <div class="price-subs">
              <span>돌파선까지 {_pct(-dist_u)}</span>
              <span>손절까지 {_pct(dist_l)}</span>
            </div>
          </div>
          {bar}
          <div class="score-row">
            <span class="score-item">종합 <b>{score:.1f}</b></span>
            <span class="score-item">RS <b>{rs:.0f}</b></span>
            <span class="score-item">CANSLIM <b>{canslim}/70</b></span>
            <span class="score-item">VCP <b>{vcp}/45</b></span>
          </div>
        </div>"""

    rebal_rows = "".join(
        f"<tr><td>{i}</td><td class='ticker-cell'>{s['ticker']}</td>"
        f"<td>20%</td><td>${s.get('donchian_lower',0):.2f}</td>"
        f"<td>{s.get('donchian_signal','HOLD')}</td></tr>"
        for i, s in enumerate(top5, 1)
    )

    return f"""
    <section class="card">
      <h2>🏆 Donchian 추세 추종 TOP 5</h2>
      <p class="subtitle">진입: 20일 고점 돌파 | 청산: 10일 저점 이탈 | 동일비중 20%</p>
      <div class="top5-grid">{rows}</div>
      <h3 class="rebal-title">📋 리밸런싱 플랜 (동일비중 20%)</h3>
      <table class="rebal-table">
        <thead><tr><th>#</th><th>티커</th><th>비중</th><th>손절선</th><th>신호</th></tr></thead>
        <tbody>{rebal_rows}</tbody>
      </table>
    </section>"""


def _section_vcp(vcp_list: list[dict]) -> str:
    if not vcp_list:
        return '<section class="card"><h2>📈 Minervini VCP TOP 20</h2><p class="muted">데이터 없음</p></section>'

    rows = ""
    for s in vcp_list:
        ticker  = s.get("ticker", "?")
        score   = s.get("total_score", 0)
        has_vcp = s.get("has_vcp", False)
        pivot   = s.get("pivot")
        rs      = s.get("rs_rating", 0)
        depth   = s.get("final_depth_pct", 0)
        contr   = s.get("contractions", 0)
        price   = s.get("current_price", 0)
        s2      = s.get("stage2_score", 0)
        vcp_sc  = s.get("vcp_score", 0)

        vcp_tag  = '<span class="vcp-confirmed">VCP ✓</span>' if has_vcp else '<span class="vcp-stage2">Stage2</span>'
        pivot_str = f"${pivot:.2f}" if pivot else "—"

        rows += f"""
        <tr>
          <td class="ticker-cell">{ticker}</td>
          <td>{vcp_tag}</td>
          <td>${price:,.2f}</td>
          <td class="score-cell">{score}</td>
          <td>{s2}/40</td>
          <td>{vcp_sc}/45</td>
          <td>{rs:.0f}</td>
          <td>{contr}</td>
          <td>{depth}%</td>
          <td class="pivot-cell">{pivot_str}</td>
        </tr>"""

    vcp_count = sum(1 for s in vcp_list if s.get("has_vcp"))
    return f"""
    <section class="card">
      <h2>📈 Minervini VCP TOP 20</h2>
      <p class="subtitle">Stage2 통과 + VCP 패턴 확인 종목 ({vcp_count}개 VCP 확정)</p>
      <div class="table-wrap">
        <table class="vcp-table">
          <thead>
            <tr>
              <th>티커</th><th>패턴</th><th>현재가</th><th>종합점수</th>
              <th>Stage2</th><th>VCP</th><th>RS</th><th>수축횟수</th><th>최종조정</th><th>피벗</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>"""


def _section_canslim(canslim_list: list[dict]) -> str:
    if not canslim_list:
        return ""
    rows = ""
    for s in canslim_list[:10]:
        ticker = s.get("ticker", "?")
        score  = s.get("canslim_score", 0)
        rs     = s.get("rs_rating", 0)
        sector = s.get("sector", "")
        scores = s.get("scores", {})
        bar_w  = int(score / 70 * 100)
        bar_c  = "#22c55e" if score >= 50 else ("#f59e0b" if score >= 35 else "#ef4444")
        scores_str = " ".join(
            f'<span class="cs-item">{k}:<b>{v}</b></span>'
            for k, v in scores.items()
        )
        rows += f"""
        <tr>
          <td class="ticker-cell">{ticker}</td>
          <td>
            <div class="cs-bar-wrap">
              <div class="cs-bar" style="width:{bar_w}%;background:{bar_c}"></div>
            </div>
            <span class="cs-score">{score}/70</span>
          </td>
          <td>{rs:.0f}</td>
          <td class="cs-detail">{scores_str}</td>
          <td class="muted">{sector}</td>
        </tr>"""

    return f"""
    <section class="card">
      <h2>📊 CANSLIM TOP 10</h2>
      <div class="table-wrap">
        <table class="cs-table">
          <thead><tr><th>티커</th><th>CANSLIM 점수</th><th>RS</th><th>세부 점수 (C/A/N/S/L/I/M)</th><th>섹터</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>"""


# ─── CSS ──────────────────────────────────────────────────────

CSS = """
:root {
  --bg:      #0f172a;
  --bg2:     #1e293b;
  --bg3:     #334155;
  --text:    #e2e8f0;
  --text2:   #94a3b8;
  --accent:  #38bdf8;
  --green:   #22c55e;
  --yellow:  #f59e0b;
  --red:     #ef4444;
  --border:  #334155;
  --radius:  12px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif;
       font-size: 14px; line-height: 1.6; }
.page { max-width: 1280px; margin: 0 auto; padding: 24px 20px; }

/* Header */
.report-header { display: flex; justify-content: space-between; align-items: center;
                 padding: 20px 28px; background: var(--bg2); border-radius: var(--radius);
                 margin-bottom: 24px; border-left: 4px solid var(--accent); }
.report-title  { font-size: 22px; font-weight: 700; color: var(--accent); }
.report-meta   { color: var(--text2); font-size: 13px; text-align: right; }
.report-meta span { display: block; }

/* Cards */
.card { background: var(--bg2); border-radius: var(--radius); padding: 24px;
        margin-bottom: 20px; border: 1px solid var(--border); }
.card h2 { font-size: 17px; font-weight: 600; margin-bottom: 16px;
           padding-bottom: 10px; border-bottom: 1px solid var(--border); }
.card h3 { font-size: 15px; font-weight: 600; margin: 20px 0 12px; }
.subtitle { color: var(--text2); font-size: 12px; margin-top: -10px; margin-bottom: 16px; }
.muted { color: var(--text2); }

/* Badges */
.badge          { display: inline-block; padding: 2px 10px; border-radius: 999px;
                  font-size: 12px; font-weight: 600; }
.badge-breakout { background: rgba(34,197,94,0.2);  color: var(--green);  border: 1px solid var(--green); }
.badge-exit     { background: rgba(239,68,68,0.2);  color: var(--red);    border: 1px solid var(--red); }
.badge-hold     { background: rgba(148,163,184,0.15); color: var(--text2); border: 1px solid var(--border); }

.risk-badge     { display: inline-block; padding: 4px 14px; border-radius: 999px;
                  font-size: 13px; font-weight: 700; }
.risk-high      { background: rgba(239,68,68,0.2);  color: var(--red); }
.risk-medium    { background: rgba(245,158,11,0.2); color: var(--yellow); }
.risk-low       { background: rgba(34,197,94,0.2);  color: var(--green); }

.bias-badge     { font-size: 14px; font-weight: 600; margin-left: 8px; }
.both-tag       { display: inline-block; background: rgba(56,189,248,0.15);
                  color: var(--accent); border: 1px solid var(--accent);
                  padding: 1px 7px; border-radius: 4px; font-size: 11px; }
.sector-tag     { color: var(--text2); font-size: 12px; }
.pivot-line     { color: var(--yellow); font-size: 12px; }
.impact         { display: inline-block; padding: 1px 7px; border-radius: 4px;
                  font-size: 11px; font-weight: 600; }
.elevated       { background: rgba(239,68,68,0.2); color: var(--red); }
.watch          { background: rgba(245,158,11,0.2); color: var(--yellow); }

/* Geo Section */
.geo-grid       { display: grid; grid-template-columns: 180px 1fr 1fr; gap: 20px; }
.gauge          { position: relative; width: 120px; margin: 0 auto 10px; }
.gauge-svg      { width: 120px; height: 70px; }
.gauge-value    { position: absolute; bottom: 4px; left: 50%; transform: translateX(-50%);
                  font-size: 26px; font-weight: 700; }
.gauge-label    { text-align: center; font-size: 12px; color: var(--text2); }
.geo-badges     { text-align: center; margin-top: 8px; }
.geo-rec        { margin-top: 10px; padding: 10px; background: var(--bg3);
                  border-radius: 8px; font-size: 13px; color: var(--text2); }
.impact-grid    { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.impact-item    { display: flex; align-items: center; gap: 6px; }
.sector-name    { font-weight: 500; }
.geo-events h4  { font-size: 13px; color: var(--text2); margin-bottom: 8px; }
.geo-events ul  { padding-left: 16px; }
.geo-events li  { font-size: 12px; color: var(--text2); margin-bottom: 4px; }

/* TOP5 */
.top5-grid      { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px,1fr));
                  gap: 16px; margin-bottom: 24px; }
.top5-card      { background: var(--bg3); border-radius: 10px; padding: 16px;
                  border: 1px solid var(--border); }
.top5-card.rank-1 { border-color: var(--green); }
.top5-header    { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 10px; }
.rank-num       { font-size: 12px; color: var(--text2); }
.ticker-name    { font-size: 18px; font-weight: 700; color: var(--accent); }
.price-main     { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.price-subs     { display: flex; gap: 12px; font-size: 12px; color: var(--text2); }
.score-row      { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.score-item     { font-size: 12px; color: var(--text2); }
.score-item b   { color: var(--text); }

/* Donchian Bar */
.dc-bar-wrap    { display: flex; align-items: center; gap: 6px; margin-top: 12px; }
.dc-label       { font-size: 11px; color: var(--text2); white-space: nowrap; min-width: 70px; }
.dc-label:last-child { text-align: right; }
.dc-bar         { flex: 1; height: 8px; background: var(--bg2); border-radius: 4px;
                  position: relative; overflow: visible; }
.dc-fill        { height: 100%; border-radius: 4px; transition: width 0.3s; }
.dc-marker      { position: absolute; top: -3px; width: 3px; height: 14px;
                  background: white; border-radius: 2px; transform: translateX(-50%); }
.dc-pos-text    { font-size: 11px; text-align: center; margin-top: 2px; font-weight: 600; }

/* Rebalancing Table */
.rebal-title    { margin-top: 24px; }
.rebal-table    { width: 100%; border-collapse: collapse; }
.rebal-table th,
.rebal-table td { padding: 8px 12px; border-bottom: 1px solid var(--border);
                  text-align: left; font-size: 13px; }
.rebal-table th { color: var(--text2); font-weight: 500; font-size: 12px; }

/* VCP Table */
.table-wrap     { overflow-x: auto; }
.vcp-table,
.cs-table       { width: 100%; border-collapse: collapse; min-width: 700px; }
.vcp-table th,
.vcp-table td,
.cs-table th,
.cs-table td    { padding: 9px 12px; border-bottom: 1px solid var(--border);
                  text-align: left; font-size: 13px; }
.vcp-table th,
.cs-table th    { color: var(--text2); font-size: 12px; font-weight: 500;
                  background: var(--bg3); }
.vcp-table tr:hover,
.cs-table tr:hover { background: rgba(255,255,255,0.03); }
.vcp-confirmed  { background: rgba(34,197,94,0.15); color: var(--green);
                  padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.vcp-stage2     { background: rgba(56,189,248,0.1); color: var(--accent);
                  padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.ticker-cell    { font-weight: 700; color: var(--accent); }
.score-cell     { font-weight: 700; }
.pivot-cell     { color: var(--yellow); }

/* CANSLIM bar */
.cs-bar-wrap    { background: var(--bg); border-radius: 4px; height: 6px; width: 120px;
                  display: inline-block; vertical-align: middle; margin-right: 6px; }
.cs-bar         { height: 100%; border-radius: 4px; }
.cs-score       { font-weight: 700; font-size: 13px; }
.cs-detail      { font-size: 12px; color: var(--text2); }
.cs-item        { margin-right: 6px; }
.cs-item b      { color: var(--text); }

/* Footer */
.footer { text-align: center; color: var(--text2); font-size: 12px; padding: 20px 0; }
"""


# ─── 메인 HTML 빌더 ──────────────────────────────────────────

def build_html(result: dict, vcp_list: list[dict], canslim_list: list[dict]) -> str:
    date     = result.get("date", datetime.now().strftime("%Y-%m-%d"))
    mode     = result.get("mode", "weekly")
    geo      = result.get("geo_risk", {})
    top5     = result.get("top5", [])
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")

    mode_label = "주간 리밸런싱" if mode == "weekly" else "일일 추적"
    risk_color = {"HIGH": "#ef4444", "MEDIUM": "#f59e0b", "LOW": "#22c55e"}.get(
        geo.get("risk_level", "MEDIUM"), "#f59e0b"
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>추세추종 리포트 {date}</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">

  <div class="report-header">
    <div>
      <div class="report-title">📊 추세 추종 트레이딩 리포트</div>
      <div style="color:var(--text2);font-size:13px;margin-top:4px">
        Richard Donchian × Mark Minervini × CANSLIM 통합 분석
      </div>
    </div>
    <div class="report-meta">
      <span style="font-size:16px;font-weight:600;color:{risk_color}">{mode_label}</span>
      <span>📅 {date}</span>
      <span style="color:var(--text2)">생성: {now_str}</span>
      <span>지정학 리스크:
        <b style="color:{risk_color}">{geo.get('risk_level','?')}</b>
        ({geo.get('market_bias','?')})
      </span>
    </div>
  </div>

  {_section_geo(geo)}
  {_section_top5(top5, geo)}
  {_section_vcp(vcp_list)}
  {_section_canslim(canslim_list)}

  <div class="footer">
    추세 추종 시스템 — Donchian {20}일 진입 / {10}일 청산 | 생성 {now_str}
  </div>
</div>
</body>
</html>"""


# ─── 진입점 ──────────────────────────────────────────────────

def generate_report(date: str | None = None) -> Path:
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    result      = load_result(date)
    vcp_list    = load_vcp()
    canslim_list = load_canslim()

    html = build_html(result, vcp_list, canslim_list)

    out = REPORT_DIR / f"trend_report_{date}.html"
    out.write_text(html, encoding="utf-8")
    print(f"HTML 리포트 저장: {out}")
    return out


if __name__ == "__main__":
    import argparse, webbrowser
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--open", action="store_true", help="브라우저에서 열기")
    args = parser.parse_args()

    path = generate_report(args.date)
    if args.open:
        webbrowser.open(path.as_uri())
