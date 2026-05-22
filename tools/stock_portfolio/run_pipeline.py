#!/usr/bin/env python3
"""
주식 포트폴리오 파이프라인
RS>=90 → CANSLIM Top10 → 거시경제 → Best 5 + 분기 리밸런싱
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from canslim_analyzer import analyze_canslim
from macro_analyzer import analyze_macro
from portfolio_manager import apply_rebalance, load, rebalance_due, save, summary
from rs_screener import screen_rs90

try:
    from kakao_sender import send_portfolio_result as _kakao_send  # type: ignore[import]
    _KAKAO_AVAILABLE = True
except Exception:
    _KAKAO_AVAILABLE = False
    _kakao_send = None  # type: ignore[assignment]

try:
    from email_reporter import send_email as _email_send  # type: ignore[import]
    _EMAIL_AVAILABLE = True
except Exception:
    _EMAIL_AVAILABLE = False
    _email_send = None  # type: ignore[assignment]

try:
    from report_writer import save_report as _save_report  # type: ignore[import]
    _REPORT_AVAILABLE = True
except Exception:
    _REPORT_AVAILABLE = False
    _save_report = None  # type: ignore[assignment]

try:
    from portfolio_analysis import run_portfolio_analysis as _port_analysis  # type: ignore[import]
    _PORT_AVAILABLE = True
except Exception:
    _PORT_AVAILABLE = False
    _port_analysis = None  # type: ignore[assignment]

CACHE_DIR = Path(__file__).parent / "cache"


def select_final5(canslim_top10: list[dict], macro: dict) -> list[dict]:
    phase = macro.get("phase", "TRANSITIONAL")
    m_score = macro.get("m_score", 7)
    rec_sectors = set(macro.get("recommended_sectors", []))

    for s in canslim_top10:
        s["scores"]["M"] = m_score
        s["canslim_score"] = sum(s["scores"].values())
        sector_bonus = 5.0 if s.get("sector") in rec_sectors else 0.0
        s["final_score"] = round(
            s["canslim_score"] * 0.50
            + s.get("rs_rating", 80) * 0.30
            + sector_bonus * 0.20,
            2,
        )

    candidates = (
        [s for s in canslim_top10 if s["canslim_score"] >= 50]
        if phase == "RISK_OFF"
        else canslim_top10
    )
    candidates.sort(key=lambda x: x["final_score"], reverse=True)
    return candidates[:5]


def print_banner(text: str) -> None:
    print(f"\n{'─'*55}")
    print(f"  {text}")
    print(f"{'─'*55}")


def run_pipeline(force_rebalance: bool = False) -> dict:
    print_banner(f"주식 포트폴리오 파이프라인  {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    portfolio = load()

    print("\n[1/4] RS 상대강도 스크리닝 (>= 90)...")
    rs90 = screen_rs90()
    print(f"  → {len(rs90)}개 종목 선별")

    print("\n[2/4] CANSLIM 분석 중 (잠시 소요)...")
    top10 = analyze_canslim(rs90, top_n=10)
    print(f"  → TOP 10 선정 완료")

    print("\n[3/4] 거시경제 분석...")
    macro = analyze_macro()
    print(
        f"  → 시장 국면: {macro['phase']}"
        f"  VIX={macro['signals'].get('vix_level','?')}"
        f"  금리={macro['signals'].get('yield10y','?')}%"
    )

    print("\n[4/4] 최종 5종목 선정...")
    final5 = select_final5(top10, macro)

    print_banner("Best 5 최종 선정 종목")
    for i, s in enumerate(final5, 1):
        print(
            f"  {i}. {s['ticker']:8s}"
            f"  CANSLIM={s['canslim_score']:3d}/70"
            f"  RS={s.get('rs_rating',0):5.1f}"
            f"  점수={s.get('final_score',0):6.2f}"
            f"  {s.get('sector','?')}"
        )

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "rs90_count": len(rs90),
        "macro_phase": macro["phase"],
        "macro_signals": macro["signals"],
        "canslim_top10": [
            {"ticker": s["ticker"], "score": s["canslim_score"], "sector": s.get("sector")}
            for s in top10
        ],
        "final5": final5,
        "rebalanced": False,
    }

    if force_rebalance or rebalance_due(portfolio):
        print("\n[리밸런싱 실행]")
        rb = apply_rebalance(portfolio, final5)
        save(rb["portfolio"])
        trades = rb["trades"]
        if trades["sell"]:  print(f"  매도: {', '.join(trades['sell'])}")
        if trades["buy"]:   print(f"  매수: {', '.join(trades['buy'])}")
        if trades["hold"]:  print(f"  유지: {', '.join(trades['hold'])}")
        result["rebalanced"] = True
        result["trades"] = trades
        result["next_rebalance"] = rb["portfolio"]["next_rebalance"]
    else:
        print(f"\n리밸런싱 예정: {portfolio.get('next_rebalance', '미설정')}")
        print(summary(portfolio))

    (CACHE_DIR / "latest_result.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"\n결과 저장: tools/stock_portfolio/cache/latest_result.json")

    if _KAKAO_AVAILABLE and _kakao_send and "--no-kakao" not in sys.argv:
        print("\n[카카오톡 발송]")
        _kakao_send(result)

    if _REPORT_AVAILABLE and _save_report and "--no-report" not in sys.argv:
        print("\n[Word 리포트 저장]")
        _save_report(result)

    if _PORT_AVAILABLE and _port_analysis and "--no-analysis" not in sys.argv:
        print("\n[포트폴리오 분석 리포트]")
        _port_analysis(result)

    if _EMAIL_AVAILABLE and _email_send and "--no-email" not in sys.argv:
        print("\n[이메일 발송]")
        _email_send(result)

    print()
    return result


if __name__ == "__main__":
    run_pipeline(force_rebalance="--rebalance" in sys.argv)
