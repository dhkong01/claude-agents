"""
로또 예측 알림 전송 (CI + 로컬 공용).
Telegram(우선) 또는 Kakao(폴백) 중 설정된 방식으로 자동 선택.

자격증명 우선순위:
  1. 환경변수 (CI: GitHub Secrets)
     - TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID  → Telegram
     - KAKAO_REST_API_KEY + KAKAO_REFRESH_TOKEN → Kakao
  2. tools/lotto/notify_config.json (로컬, gitignore됨)
     - telegram_bot_token / telegram_chat_id
     - kakao_rest_api_key / kakao_refresh_token
"""
import json, os, sys
from pathlib import Path
from datetime import date

ROOT       = Path(__file__).resolve().parents[3]   # repo 루트
PRED_PATH  = ROOT / "tools/lotto/data/lotto_prediction.json"
REPORT_DIR = ROOT / "tools/lotto/reports"

# ── 로컬 config 폴백 — 환경변수 없으면 notify_config.json에서 로드 ──
_cfg_path = ROOT / "tools/lotto/notify_config.json"
if _cfg_path.exists():
    try:
        _cfg = json.loads(_cfg_path.read_text(encoding="utf-8"))
        _map = {
            "TELEGRAM_BOT_TOKEN":  "telegram_bot_token",
            "TELEGRAM_CHAT_ID":    "telegram_chat_id",
            "KAKAO_REST_API_KEY":  "kakao_rest_api_key",
            "KAKAO_REFRESH_TOKEN": "kakao_refresh_token",
        }
        for env_k, cfg_k in _map.items():
            if not os.environ.get(env_k) and _cfg.get(cfg_k):
                os.environ[env_k] = str(_cfg[cfg_k])
    except Exception as e:
        print(f"[경고] notify_config.json 로드 실패: {e}")

if not PRED_PATH.exists():
    print("오류: lotto_prediction.json 없음"); sys.exit(1)

pred     = json.loads(PRED_PATH.read_text(encoding="utf-8"))
games    = pred.get("games", [])
draw     = pred["draw"]
best_idx = max(range(len(games)), key=lambda i: games[i].get("combined_score", games[i]["overall_coherence"])) if games else 0
bg       = games[best_idx] if games else pred
core     = set(bg.get("core_numbers", []))
ind      = bg.get("individual_coherence", {})
lo, hi   = pred.get("sum_range", [100, 175])
bt       = pred.get("backtest", {})


# ── 메시지 조립 ───────────────────────────────────────────────
_m = pred.get("method", "")
method_short = ("Lift+트리플렛" if "Lift" in _m
                else "트리플렛+쌍확률" if "트리플렛" in _m
                else "정합성+쌍확률" if "쌍" in _m
                else "3모델합의정합성")
lines1 = [f"🎱 로또 {draw}회 예측 ({method_short})"]
for g, gr in enumerate(games):
    nums     = " ".join(f"{n:02d}" for n in gr["numbers"])
    marker   = " ◀대표" if g == best_idx else ""
    combined = gr.get("combined_score", gr["overall_coherence"])
    lines1.append(f"{chr(65+g)}: {nums}  합{gr['sum']}  통합{combined:.0f}%{marker}")
msg1 = "\n".join(lines1)

pair_lines = ""
if bg.get("pair_detail"):
    top_pairs = sorted(bg["pair_detail"].items(), key=lambda x: -x[1])[:3]
    pair_lines = "\n" + "\n".join(f"  {p}: {v:.1f}%" for p, v in top_pairs)

nums_detail = "  ".join(
    f"{'★' if n in core else ''}{n}번:{ind.get(str(n), 0):.0f}%"
    for n in bg["numbers"]
)
combined_s = bg.get("combined_score", bg["overall_coherence"])
pair_vs    = bg.get("pair_vs_random", "")
pair_info  = f"쌍확률 {bg.get('pair_score',0):.1f}% (무작위대비{pair_vs}배)\n" if pair_vs else ""
pop_s      = bg.get("popularity_avoid_score")
pop_info   = f"비인기도 {pop_s:.0f}% (분할위험 낮음)\n" if pop_s is not None else ""
msg2 = (
    f"📊 대표 Game {chr(65+best_idx)} 상세\n"
    f"{nums_detail}\n"
    f"핵심 {len(core)}개  정합성 {bg['overall_coherence']:.0f}%  통합 {combined_s:.0f}%\n"
    f"{pair_info}"
    f"{pop_info}"
    f"상위쌍{pair_lines}\n"
    f"합계 {bg['sum']} (유효범위 {lo}~{hi})\n"
    f"백테스트 TOP12 평균 {bt.get('avg_hits', 0)}개 적중\n"
    f"⚠️ 정합성=모델일치도, 당첨 확률 아님 / 비인기도=분할인원 축소용, 적중확률과 무관"
)
full_msg = msg1 + "\n\n" + msg2


# ── 전송 (stock_portfolio/notify.py 공용 로직 재사용) ───────────
# 예전엔 자체 구현이 실패를 조용히 삼켜서(exit 0 고정) Kakao 토큰 만료 +
# Telegram 시크릿 미설정 상태가 몇 주째 감지되지 않았다. 주식 쪽에서 이미
# 검증된 채널별 상세 진단(send_message_detailed)을 그대로 재사용한다.
sys.path.insert(0, str(ROOT / "tools" / "stock_portfolio"))
from notify import send_message_detailed  # noqa: E402

_notify_ok, _notify_detail = send_message_detailed(full_msg)
if _notify_ok:
    print(f"[notify] 전송 완료 ({_notify_detail}): 로또 {draw}회")
else:
    # ::error:: 는 continue-on-error(step) 여부와 무관하게 Actions
    # Annotations 탭에 항상 남아 다음 실행 때 로그인 없이 원인을 알 수 있다.
    print(f"::error::로또 {draw}회 알림이 발송되지 않았습니다 — {_notify_detail}")


# ── 리포트 저장 ───────────────────────────────────────────────
REPORT_DIR.mkdir(parents=True, exist_ok=True)
today    = date.today().isoformat()
rpt_path = REPORT_DIR / f"{today}.md"

rows = [
    f"| {chr(65+g)}{' ◀대표' if g==best_idx else ''} "
    f"| {gr['numbers']} | {gr['sum']} "
    f"| {gr['odd_count']}홀{6-gr['odd_count']}짝 | {gr['overall_coherence']:.1f}% |"
    for g, gr in enumerate(games)
]
detail = [
    f"| {n} | {ind.get(str(n),0):.1f}% | {'★핵심' if n in core else '보조'} |"
    for n in bg["numbers"]
]
rpt_path.write_text("\n".join([
    f"# 로또 예측 — 제{draw}회 ({today})",
    f"방법: {pred.get('method','')}",
    "", "## 5게임",
    "| 게임 | 번호 | 합계 | 홀짝 | 정합성 |",
    "|------|------|------|------|--------|", *rows,
    "", f"## 대표 게임 (Game {chr(65+best_idx)}) 상세",
    "| 번호 | 정합성 | 구분 |", "|------|--------|------|", *detail,
    "", "## 백테스트",
    f"TOP12 평균 {bt.get('avg_hits',0)}개 적중 / {bt.get('n_test',0)}회 검증",
]), encoding="utf-8")
print(f"리포트 저장: {rpt_path}")

# 리포트는 항상 저장(위) — 커밋 단계가 계속 진행되도록.
# 전송 자체가 실패했으면 여기서 비정상 종료해 Annotations에 표시되게 한다.
# (워크플로 스텝은 continue-on-error: true 라 history.json 커밋은 막히지 않음)
sys.exit(0 if _notify_ok else 1)
