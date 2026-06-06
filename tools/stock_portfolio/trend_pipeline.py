"""
추세 추종 트레이딩 시스템 — 주간 리밸런싱 메인 파이프라인

weekly 모드: 지정학Risk + RS/CANSLIM + VCP 전체 실행 → Donchian TOP5 선정
daily  모드: Donchian 채널 추적 → 청산/돌파 신호 발송

Usage:
  python trend_pipeline.py [--mode weekly|daily] [--no-kakao]
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from data_utils import CACHE_DIR


# ── 캐시 로더 ─────────────────────────────────────────────────

def _load(name: str) -> dict | None:
    p = CACHE_DIR / name
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:
        return None


def _cache_fresh(name: str, today: str) -> bool:
    d = _load(name)
    return bool(d and d.get("date") == today)


# ── 파이프라인 ─────────────────────────────────────────────────

def run_trend_pipeline(mode: str = "weekly", send_kakao: bool = True) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  추세 추종 파이프라인 [{mode.upper()}]  {today}")
    print(f"{'='*60}")

    result: dict = {"date": today, "mode": mode}

    # ── 1. RS 스크리닝 ──────────────────────────────────────
    print("\n[1/5] RS 스크리닝 (S&P500 + NDX100)...")
    if not _cache_fresh("rs90.json", today):
        from rs_screener import screen_rs90
        screen_rs90()
    rs_data = _load("rs90.json") or {}
    rs_count = rs_data.get("rs90_count", 0)
    print(f"      RS≥90: {rs_count}개")

    # ── 2. CANSLIM TOP 10 ────────────────────────────────────
    print("\n[2/5] CANSLIM TOP10 분석...")
    if not _cache_fresh("canslim_top10.json", today):
        from canslim_analyzer import analyze_canslim
        rs_stocks = rs_data.get("stocks", [])
        analyze_canslim(rs_stocks, top_n=10)
    canslim_data  = _load("canslim_top10.json") or {}
    canslim_top10 = canslim_data.get("top10", [])
    print(f"      CANSLIM TOP10: {[s['ticker'] for s in canslim_top10]}")

    # ── 3. 지정학 리스크 ─────────────────────────────────────
    print("\n[3/5] 지정학 리스크 분석...")
    from geo_risk_analyzer import analyze_geo_risk
    geo_risk = analyze_geo_risk()
    result["geo_risk"] = geo_risk
    print(f"      [{geo_risk['risk_level']}]  "
          f"Score:{geo_risk['risk_score']}  "
          f"Bias:{geo_risk['market_bias']}")

    # ── 4. Minervini VCP TOP 20 ──────────────────────────────
    print("\n[4/5] Minervini VCP 스크리닝...")
    if mode == "weekly" or not _cache_fresh("vcp_top20.json", today):
        from minervini_vcp import screen_vcp
        vcp_top20 = screen_vcp(min_rs=80.0, top_n=20)
    else:
        vcp_top20 = (_load("vcp_top20.json") or {}).get("stocks", [])
    vcp_hits = sum(1 for s in vcp_top20 if s.get("has_vcp"))
    print(f"      VCP 패턴 확인: {vcp_hits}개")
    result["vcp_top20"] = vcp_top20

    # ── 5. Donchian TOP 5 선정 ───────────────────────────────
    print("\n[5/5] Donchian 추세 추종 TOP 5 선정...")
    from donchian_tracker import select_top5, track_portfolio
    top5 = select_top5(canslim_top10, vcp_top20, geo_risk)
    result["top5"] = top5

    _print_top5(top5)

    # ── 일일 추적 ────────────────────────────────────────────
    if mode == "daily":
        print("\n[일일] Donchian 채널 추적...")
        port_file = BASE_DIR / "my_portfolio.json"
        port_tickers: list[str] = []
        if port_file.exists():
            port_tickers = [h["ticker"]
                            for h in json.loads(port_file.read_text(encoding="utf-8"))
                            .get("holdings", [])]
        top5_tickers = [s["ticker"] for s in top5]
        track_list   = list(dict.fromkeys(port_tickers + top5_tickers))

        tracking = track_portfolio(track_list)
        result["tracking"] = tracking

        exits     = [t for t in tracking if t.get("signal") == "EXIT"]
        breakouts = [t for t in tracking if t.get("signal") == "BREAKOUT"]
        if exits:
            print(f"  [EXIT] {[t['ticker'] for t in exits]}")
        if breakouts:
            print(f"  [BREAKOUT] {[t['ticker'] for t in breakouts]}")

    # ── 결과 저장 ────────────────────────────────────────────
    out_path = CACHE_DIR / f"trend_result_{today}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")

    # ── HTML 리포트 자동 생성 ────────────────────────────────
    try:
        from trend_report import generate_report
        report_path = generate_report(today)
        print(f"\n[Report] {report_path}")
    except Exception as e:
        print(f"[Report] 생성 실패: {e}", file=sys.stderr)

    # ── KakaoTalk 발송 ───────────────────────────────────────
    if send_kakao:
        _send_kakao(result, mode)

    return result


# ── 콘솔 출력 ─────────────────────────────────────────────────

def _print_top5(top5: list[dict]) -> None:
    if not top5:
        print("      후보 종목 없음")
        return
    print(f"\n  {'Rank':<4} {'Ticker':<7} {'Signal':<10} "
          f"{'현재가':>8} {'돌파선':>8} {'손절선':>8} {'점수':>6}")
    print(f"  {'-'*56}")
    for i, s in enumerate(top5, 1):
        sig   = s.get("donchian_signal", "HOLD")
        print(f"  {i:<4} {s['ticker']:<7} {sig:<10} "
              f"${s.get('current_price',0):>7.2f} "
              f"${s.get('donchian_upper',0):>7.2f} "
              f"${s.get('donchian_lower',0):>7.2f} "
              f"{s.get('final_score',0):>6.1f}")


# ── KakaoTalk 메시지 ─────────────────────────────────────────

def _build_message(result: dict, mode: str) -> str:
    today = result["date"]
    geo   = result.get("geo_risk", {})
    top5  = result.get("top5", [])

    risk_icon = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(
        geo.get("risk_level", "MEDIUM"), "🟡"
    )
    header = "주간리밸런싱" if mode == "weekly" else "일일추적"

    lines = [
        f"📊 추세추종 {header} [{today}]",
        f"",
        f"🌍 지정학: {risk_icon}{geo.get('risk_level','?')} "
        f"Score:{geo.get('risk_score','?')} | {geo.get('market_bias','?')}",
    ]

    if geo.get("sector_impacts"):
        elevated = [s for s, v in geo["sector_impacts"].items() if v == "ELEVATED"]
        if elevated:
            lines.append(f"⚡ 주시섹터: {', '.join(elevated)}")

    lines += [
        f"",
        f"━━━━━━━━━━━━━━━",
        f"🏆 Donchian TOP 5",
        f"━━━━━━━━━━━━━━━",
    ]

    for i, s in enumerate(top5, 1):
        sig = s.get("donchian_signal", "HOLD")
        if sig == "BREAKOUT":
            sig_str = "🚀돌파"
        else:
            dist = s.get("dist_to_upper_pct", 0)
            sig_str = f"↑{dist:.1f}%"

        rs  = s.get("rs_rating", 0)
        vcp = "✓" if s.get("vcp_score", 0) > 20 else ""
        lines.append(
            f"{i}.{s['ticker']} {sig_str}{vcp}  "
            f"${s.get('current_price',0):.1f}  "
            f"RS{rs:.0f}"
        )

    # 일일 추적 신호
    tracking  = result.get("tracking", [])
    exits     = [t["ticker"] for t in tracking if t.get("signal") == "EXIT"]
    breakouts = [t["ticker"] for t in tracking if t.get("signal") == "BREAKOUT"]
    if exits or breakouts:
        lines += ["", "━━━━━━━━━━━━━━━", "⚡ 액션 필요"]
        if exits:
            lines.append(f"⚠️ 청산신호: {', '.join(exits)}")
        if breakouts:
            lines.append(f"🚀 신규진입: {', '.join(breakouts)}")

    # 주간 리밸런싱 제안
    if mode == "weekly" and top5:
        lines += ["", "━━━━━━━━━━━━━━━", "📋 리밸런싱 제안 (동일비중 20%)"]
        for s in top5:
            lines.append(
                f"  {s['ticker']}: 20%  "
                f"손절=${s.get('donchian_lower',0):.2f}"
            )

    return "\n".join(lines)


def _get_kakao_token() -> str:
    """
    GitHub Actions: KAKAO_REST_API_KEY + KAKAO_REFRESH_TOKEN 으로 access token 발급
    로컬: kakao_config.json 에서 토큰 로드 (kakao_sender._get_token 재사용)
    """
    import os, json as _json, urllib.parse, urllib.request

    rest_key      = os.environ.get("KAKAO_REST_API_KEY", "")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN", "")

    if rest_key and refresh_token:
        # GitHub Actions 경로: refresh_token → access_token 발급
        body = urllib.parse.urlencode({
            "grant_type":    "refresh_token",
            "client_id":     rest_key,
            "refresh_token": refresh_token,
        }).encode()
        req = urllib.request.Request(
            "https://kauth.kakao.com/oauth/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = _json.loads(resp.read())
        token = data.get("access_token", "")
        if not token:
            raise RuntimeError(f"Kakao token 발급 실패: {data}")
        return token

    # 로컬 환경 경로: kakao_config.json
    from kakao_sender import _get_token
    return _get_token()


def _send_kakao(result: dict, mode: str) -> None:
    try:
        import json as _json, urllib.parse, urllib.request

        token    = _get_kakao_token()
        msg      = _build_message(result, mode)
        MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        template = _json.dumps({
            "object_type": "text",
            "text":        msg[:2000],
            "link":        {"web_url": "", "mobile_web_url": ""},
        }, ensure_ascii=False)
        body = urllib.parse.urlencode({"template_object": template}).encode()
        req  = urllib.request.Request(
            MEMO_URL, data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/x-www-form-urlencoded;charset=utf-8",
            }
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            resp.read()
        print("✅ KakaoTalk 발송 완료")
    except Exception as e:
        print(f"⚠️  KakaoTalk 발송 실패: {e}", file=sys.stderr)


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="추세 추종 트레이딩 파이프라인")
    parser.add_argument("--mode",      choices=["weekly", "daily"], default="weekly")
    parser.add_argument("--no-kakao",  action="store_true", help="KakaoTalk 발송 스킵")
    args = parser.parse_args()

    run_trend_pipeline(mode=args.mode, send_kakao=not args.no_kakao)
