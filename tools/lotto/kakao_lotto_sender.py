"""
로또 예측 결과를 카카오톡 나에게 보내기로 전송.
stock_portfolio/kakao_sender.py의 토큰 관리 재사용.
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# 카카오 설정은 stock_portfolio와 공유
CONFIG_PATH = Path(__file__).parent.parent / "stock_portfolio" / "kakao_config.json"
PRED_PATH   = Path(__file__).parent / "data" / "lotto_prediction.json"
REPORT_DIR  = Path(__file__).parent / "reports"
TOKEN_URL   = "https://kauth.kakao.com/oauth/token"
MEMO_URL    = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
WEEKDAYS    = "월화수목금토일"


def _load_cfg() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"kakao_config.json 없음: {CONFIG_PATH}\n"
            "tools/stock_portfolio/kakao_setup.py를 먼저 실행하세요."
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


def format_lotto_message(pred: dict) -> str:
    now     = datetime.now()
    today   = now.strftime("%Y-%m-%d")
    weekday = WEEKDAYS[now.weekday()]

    draw    = pred["draw"]
    games   = pred.get("games", [])
    best    = pred  # 대표 게임 데이터
    method  = pred.get("method", "")
    bt      = pred.get("backtest", {})
    sum_lo, sum_hi = pred.get("sum_range", [100, 175])

    # 대표 게임 인덱스
    best_idx = max(range(len(games)),
                   key=lambda i: games[i].get("combined_score", games[i]["overall_coherence"])) if games else 0

    lines = [
        f"🎱 로또 예측 — 제{draw}회",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"📅 {today} ({weekday})",
        f"방법: {method}",
        f"",
        f"[5게임 예측]",
    ]

    for g, gr in enumerate(games):
        nums = " ".join(f"{n:02d}" for n in gr["numbers"])
        marker = " ◀대표" if g == best_idx else ""
        lines.append(
            f"{chr(65+g)}  {nums}"
            f"  합:{gr['sum']}"
            f"  홀{gr['odd_count']}짝{6-gr['odd_count']}"
            f"  {gr['overall_coherence']:.1f}%{marker}"
        )

    # 대표 게임 상세
    bg = games[best_idx] if games else best
    lines += [
        f"",
        f"[대표 (Game {chr(65+best_idx)}) 상세]",
    ]
    ind_coh = bg.get("individual_coherence", {})
    core    = set(bg.get("core_numbers", []))
    for n in bg["numbers"]:
        tag = "★" if n in core else " "
        lines.append(f"  {tag} {n:2d}번: {ind_coh.get(str(n), 0):.1f}%")

    lines += [
        f"",
        f"핵심({len(core)}개): {sorted(core)}",
        f"전체 정합성: {bg['overall_coherence']:.1f}%",
        f"합계 유효범위: {sum_lo}~{sum_hi}",
    ]

    # 백테스트
    if bt:
        lines += [
            f"",
            f"[백테스트] TOP12 평균 {bt.get('avg_hits',0)}개 적중"
            f" (최대 {bt.get('max_hits',0)}개, {bt.get('n_test',0)}회 검증)",
        ]

    lines += [
        f"",
        f"⚠️ 로또는 무작위 추첨. 정합성은 모델 일치도이며 당첨 확률이 아닙니다.",
    ]

    return "\n".join(lines)


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


def send_lotto_prediction() -> bool:
    if not PRED_PATH.exists():
        print("lotto_prediction.json 없음. predict.py를 먼저 실행하세요.", file=sys.stderr)
        return False
    pred = json.loads(PRED_PATH.read_text(encoding="utf-8"))
    try:
        msg = format_lotto_message(pred)
        ok  = _send_raw(msg)
        print(f"  카카오톡 발송 성공: 제{pred['draw']}회 예측")
        return ok
    except FileNotFoundError as e:
        print(f"  [카카오 설정 필요] {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [KakaoTalk 발송 실패] {e}", file=sys.stderr)
        return False


def save_report(pred: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    path  = REPORT_DIR / f"{today}.md"

    games   = pred.get("games", [])
    best_idx = max(range(len(games)),
                   key=lambda i: games[i].get("combined_score", games[i]["overall_coherence"])) if games else 0
    bg = games[best_idx] if games else pred
    core = set(bg.get("core_numbers", []))
    ind  = bg.get("individual_coherence", {})

    lines = [
        f"# 로또 예측 — 제{pred['draw']}회 ({today})",
        f"방법: {pred.get('method', '')}",
        f"",
        f"## 5게임",
        f"| 게임 | 번호 | 합계 | 홀짝 | 정합성 |",
        f"|------|------|------|------|--------|",
    ]
    for g, gr in enumerate(games):
        nums = str(gr["numbers"])
        marker = " ◀대표" if g == best_idx else ""
        lines.append(
            f"| {chr(65+g)}{marker} | {nums} | {gr['sum']} "
            f"| {gr['odd_count']}홀{6-gr['odd_count']}짝 | {gr['overall_coherence']:.1f}% |"
        )

    lines += [
        f"",
        f"## 대표 게임 (Game {chr(65+best_idx)}) 상세",
        f"| 번호 | 정합성 | 구분 |",
        f"|------|--------|------|",
    ]
    for n in bg["numbers"]:
        tag = "★핵심" if n in core else "보조"
        lines.append(f"| {n} | {ind.get(str(n), 0):.1f}% | {tag} |")

    bt = pred.get("backtest", {})
    lines += [
        f"",
        f"## 백테스트",
        f"TOP12 평균 {bt.get('avg_hits',0)}개 적중 / {bt.get('n_test',0)}회 검증",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  리포트 저장: {path}")
    return path


if __name__ == "__main__":
    if not PRED_PATH.exists():
        print("lotto_prediction.json 없음. predict.py를 먼저 실행하세요.")
        sys.exit(1)
    pred = json.loads(PRED_PATH.read_text(encoding="utf-8"))
    save_report(pred)
    send_lotto_prediction()
