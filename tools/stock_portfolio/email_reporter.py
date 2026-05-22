"""
일일 포트폴리오 보고서 이메일 발송 (Gmail SMTP / App Password).
설정: tools/stock_portfolio/email_config.json
"""
import json
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "email_config.json"
WEEKDAYS    = "월화수목금토일"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "email_config.json 없음.\n"
            "아래 내용으로 파일 생성 후 실제 값으로 채우세요:\n"
            '{\n  "smtp_server": "smtp.gmail.com",\n  "smtp_port": 587,\n'
            '  "sender": "yrlokdh@gmail.com",\n  "password": "앱 비밀번호 16자리",\n'
            '  "recipient": "yrlokdh@gmail.com"\n}'
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def build_report(result: dict) -> tuple[str, str]:
    """Return (subject, body) plain-text report."""
    now     = datetime.now()
    today   = now.strftime("%Y-%m-%d")
    weekday = WEEKDAYS[now.weekday()]

    phase   = result.get("macro_phase", "?")
    signals = result.get("macro_signals", {})
    rs_cnt  = result.get("rs90_count", "?")
    top10   = result.get("canslim_top10", [])
    final5  = result.get("final5", [])
    rb      = result.get("rebalanced", False)
    trades  = result.get("trades", {})
    next_rb = result.get("next_rebalance", "미설정")

    phase_label = {"RISK_ON": "강세 🟢", "TRANSITIONAL": "중립 🟡", "RISK_OFF": "약세 🔴"}.get(phase, phase)

    sep = "─" * 48

    lines = [
        f"주식 포트폴리오 일일 리포트  {today} ({weekday})",
        sep,
        "",
        "[ 거시경제 ]",
        f"  시장 국면  : {phase_label}",
        f"  VIX       : {signals.get('vix_level', '?')}",
        f"  금리(10Y) : {signals.get('yield10y', '?')}%  ({signals.get('rate_env', '?')})",
        f"  달러 추세  : {signals.get('dollar_trend', '?')}",
        "",
        "[ RS 스크리닝 결과 ]",
        f"  RS ≥ 90 종목: {rs_cnt}개",
        "",
        "[ CANSLIM TOP 10 ]",
        f"  {'순위':<4}  {'종목':<8}  {'점수':>6}  섹터",
    ]
    for i, s in enumerate(top10, 1):
        lines.append(f"  {i:<4}  {s['ticker']:<8}  {s['score']:>3}/70  {s.get('sector','?')}")

    lines += [
        "",
        "[ Best 5 최종 선정 ]",
        f"  {'종목':<8}  {'RS':>6}  {'CANSLIM':>7}  {'최종점수':>8}  섹터",
    ]
    for i, s in enumerate(final5, 1):
        lines.append(
            f"  {i}. {s['ticker']:<6}  {s.get('rs_rating',0):>6.1f}"
            f"  {s.get('canslim_score',0):>5}/70"
            f"  {s.get('final_score',0):>8.2f}"
            f"  {s.get('sector','?')}"
        )

    lines += ["", "[ 리밸런싱 ]"]
    if rb:
        if trades.get("buy"):   lines.append(f"  매수 ▶ {', '.join(trades['buy'])}")
        if trades.get("sell"):  lines.append(f"  매도 ◀ {', '.join(trades['sell'])}")
        if trades.get("hold"):  lines.append(f"  유지 ─ {', '.join(trades['hold'])}")
    else:
        lines.append("  해당 없음 (다음 리밸런싱 대기)")
    lines.append(f"  다음 리밸런싱: {next_rb}")

    lines += ["", sep, f"자동 생성: stock-orchestrator  {now.strftime('%H:%M')}"]

    subject = f"[포트폴리오] {today} ({weekday}) 일일 리포트 — {phase_label}"
    body    = "\n".join(lines)
    return subject, body


def send_email(result: dict) -> bool:
    try:
        cfg = load_config()
        subject, body = build_report(result)

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"]    = cfg["sender"]
        msg["To"]      = cfg["recipient"]

        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"], timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(cfg["sender"], cfg["password"])
            smtp.sendmail(cfg["sender"], cfg["recipient"], msg.as_string())

        print(f"  이메일 발송 성공 → {cfg['recipient']}")
        return True
    except FileNotFoundError as e:
        print(f"  [이메일 설정 필요] {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [이메일 발송 실패] {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    cache = Path(__file__).parent / "cache" / "latest_result.json"
    if not cache.exists():
        print("run_pipeline.py를 먼저 실행하세요")
        sys.exit(1)
    result = json.loads(cache.read_text(encoding="utf-8"))
    send_email(result)
