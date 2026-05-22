"""
KakaoTalk "나에게 보내기" — 포트폴리오 일일 요약 전송.
토큰 자동 갱신 | 설정: kakao_config.json
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "kakao_config.json"
MY_PORT     = Path(__file__).parent / "my_portfolio.json"
CACHE_DIR   = Path(__file__).parent / "cache"
TOKEN_URL   = "https://kauth.kakao.com/oauth/token"
MEMO_URL    = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
WEEKDAYS    = "월화수목금토일"


# ── 토큰 관리 ─────────────────────────────────────────────

def _load_cfg() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "kakao_config.json 없음.\n"
            "kakao_setup.py를 먼저 실행해 인증을 완료하세요."
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _save_cfg(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def _post(url: str, data: dict, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req  = urllib.request.Request(url, data=body, headers=headers or {})
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read())


def _get_token() -> str:
    cfg = _load_cfg()
    exp = cfg.get("token_expires_at")
    if exp and datetime.fromisoformat(exp) > datetime.now():
        return cfg["access_token"]
    # 토큰 갱신
    result = _post(TOKEN_URL, {
        "grant_type":    "refresh_token",
        "client_id":     cfg["rest_api_key"],
        "refresh_token": cfg["refresh_token"],
    })
    cfg["access_token"] = result["access_token"]
    if "refresh_token" in result:
        cfg["refresh_token"] = result["refresh_token"]
    cfg["token_expires_at"] = (
        datetime.now() + timedelta(seconds=result.get("expires_in", 21599) - 60)
    ).isoformat()
    _save_cfg(cfg)
    return cfg["access_token"]


# ── 포트폴리오 데이터 ─────────────────────────────────────

def _fetch_prices(tickers: list[str]) -> dict[str, dict]:
    import yfinance as yf
    result: dict[str, dict] = {}
    for t in tickers:
        try:
            fi    = yf.Ticker(t).fast_info
            price = float(getattr(fi, "last_price", 0) or 0)
            prev  = float(getattr(fi, "previous_close", price) or price)
            result[t] = {
                "price": price,
                "pct":   (price - prev) / prev * 100 if prev else 0,
            }
        except Exception:
            result[t] = {"price": 0.0, "pct": 0.0}
    return result


def _load_user_rs() -> dict[str, float]:
    f = CACHE_DIR / "user_portfolio_rs.json"
    if f.exists():
        return {t: float(r) for t, r in
                json.loads(f.read_text(encoding="utf-8")).get("ratings", {}).items()}
    return {}


def _portfolio_lines() -> list[str]:
    if not MY_PORT.exists():
        return ["(my_portfolio.json 없음)"]
    holdings = json.loads(MY_PORT.read_text(encoding="utf-8")).get("holdings", [])
    if not holdings:
        return ["(보유 종목 없음)"]
    tickers  = [h["ticker"] for h in holdings]
    prices   = _fetch_prices(tickers)
    user_rs  = _load_user_rs()
    lines    = []
    total_val = total_cost = 0.0
    for h in holdings:
        t     = h["ticker"]
        d     = prices[t]
        cost  = h.get("avg_cost", d["price"])
        pnl   = (d["price"] - cost) / cost * 100 if cost else 0
        rs    = user_rs.get(t, 0)
        dir_  = "▲" if d["pct"] >= 0 else "▼"
        sig   = "🟢" if rs >= 90 else ("🔵" if rs >= 80 else ("🟡" if rs >= 60 else "🔴"))
        lines.append(
            f"{sig}{t:<5} ${d['price']:.1f} {dir_}{abs(d['pct']):.1f}%"
            f"  RS{rs:.0f}  손익{pnl:+.1f}%"
        )
        shares = h.get("shares", 0)
        total_val  += d["price"] * shares
        total_cost += cost * shares
    total_pnl = (total_val - total_cost) / total_cost * 100 if total_cost else 0
    lines.append(f"──────────────────────")
    lines.append(f"총평가 ${total_val:,.0f}  수익률 {total_pnl:+.1f}%")
    return lines


# ── 메시지 포맷 ───────────────────────────────────────────

def format_message(result: dict) -> str:
    now     = datetime.now()
    today   = now.strftime("%Y-%m-%d")
    weekday = WEEKDAYS[now.weekday()]

    phase   = result.get("macro_phase", "?")
    signals = result.get("macro_signals", {})
    vix     = signals.get("vix_level", "?")
    y10     = signals.get("yield10y", "?")
    rs_cnt  = result.get("rs90_count", "?")
    final5  = result.get("final5", [])
    rb      = result.get("rebalanced", False)
    trades  = result.get("trades", {})
    port_file = Path(__file__).parent / "portfolio.json"
    next_rb = result.get("next_rebalance")
    if not next_rb and port_file.exists():
        next_rb = json.loads(port_file.read_text(encoding="utf-8")).get("next_rebalance", "미설정")
    next_rb = next_rb or "미설정"

    icon = {"RISK_ON": "🟢 강세장", "TRANSITIONAL": "🟡 혼조세", "RISK_OFF": "🔴 약세장"}.get(phase, phase)

    lines = [
        f"📊 포트폴리오 일일 리포트",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"📅 {today} ({weekday})",
        f"",
        f"[시장 국면]",
        f"{icon}  VIX {vix}  금리 {y10}%  RS≥90: {rs_cnt}개",
        f"",
        f"[내 포트폴리오]",
    ]

    port_lines = _portfolio_lines()
    lines.extend(port_lines)

    lines += [
        f"",
        f"[Best 5 추천]",
    ]
    for i, s in enumerate(final5, 1):
        lines.append(
            f"{i}. {s['ticker']:<5} RS {s.get('rs_rating',0):.0f}"
            f"  CANSLIM {s.get('canslim_score',0)}/70"
        )

    lines.append("")
    if rb and trades:
        lines.append("[리밸런싱 실행]")
        if trades.get("buy"):  lines.append(f"▶ 매수: {', '.join(trades['buy'])}")
        if trades.get("sell"): lines.append(f"◀ 매도: {', '.join(trades['sell'])}")
        if trades.get("hold"): lines.append(f"─ 유지: {', '.join(trades['hold'])}")
    else:
        lines.append("[리밸런싱] 해당 없음 — 유지")

    lines.append(f"다음 리밸런싱: {next_rb}")

    return "\n".join(lines)


# ── 전송 ──────────────────────────────────────────────────

def _send_raw(text: str) -> bool:
    token    = _get_token()
    template = json.dumps({
        "object_type": "text",
        "text":        text[:2000],
        "link":        {"web_url": "", "mobile_web_url": ""},
    }, ensure_ascii=False)
    _post(MEMO_URL, {"template_object": template}, {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/x-www-form-urlencoded;charset=utf-8",
    })
    return True


def send_portfolio_result(result: dict) -> bool:
    try:
        msg = format_message(result)
        ok  = _send_raw(msg)
        print("  KakaoTalk 발송: 성공")
        return ok
    except FileNotFoundError as e:
        print(f"  [카카오 설정 필요] {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [KakaoTalk 발송 실패] {e}", file=sys.stderr)
        return False


def test_connection() -> bool:
    """연결 테스트 — 짧은 메시지 발송."""
    now  = datetime.now()
    text = (
        f"✅ KakaoTalk 연결 테스트\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {now.strftime('%Y-%m-%d')} ({WEEKDAYS[now.weekday()]})"
        f" {now.strftime('%H:%M')}\n\n"
        f"포트폴리오 알림 시스템이 정상 연결되었습니다.\n"
        f"매일 오전 7시에 리포트가 자동 전송됩니다."
    )
    try:
        ok = _send_raw(text)
        print("  ✅ 테스트 메시지 전송 성공 — 카카오톡을 확인하세요.")
        return ok
    except FileNotFoundError as e:
        print(f"  ❌ 설정 필요: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  ❌ 전송 실패: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_connection()
    else:
        cache = CACHE_DIR / "latest_result.json"
        if not cache.exists():
            print("run_pipeline.py를 먼저 실행하세요")
            sys.exit(1)
        result = json.loads(cache.read_text(encoding="utf-8"))
        send_portfolio_result(result)
