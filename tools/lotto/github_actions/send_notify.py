"""
GitHub Actions 전용 알림 전송.
Telegram 또는 Kakao 중 설정된 방식으로 자동 선택.
환경변수:
  - TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID  → Telegram
  - KAKAO_REST_API_KEY + KAKAO_REFRESH_TOKEN → Kakao
"""
import json, os, sys, urllib.parse, urllib.request
from pathlib import Path
from datetime import date

PRED_PATH  = Path("tools/lotto/data/lotto_prediction.json")
REPORT_DIR = Path("tools/lotto/reports")

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


def _post(url, data=None, headers=None, as_json=False):
    if as_json:
        body = json.dumps(data).encode()
        headers = {"Content-Type": "application/json", **(headers or {})}
    else:
        body = urllib.parse.urlencode(data or {}).encode()
        headers = headers or {}
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


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
msg2 = (
    f"📊 대표 Game {chr(65+best_idx)} 상세\n"
    f"{nums_detail}\n"
    f"핵심 {len(core)}개  정합성 {bg['overall_coherence']:.0f}%  통합 {combined_s:.0f}%\n"
    f"{pair_info}"
    f"상위쌍{pair_lines}\n"
    f"합계 {bg['sum']} (유효범위 {lo}~{hi})\n"
    f"백테스트 TOP12 평균 {bt.get('avg_hits', 0)}개 적중\n"
    f"⚠️ 정합성=모델일치도, 당첨 확률 아님"
)
full_msg = msg1 + "\n\n" + msg2


# ── Telegram 전송 ─────────────────────────────────────────────
def send_telegram():
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    _post(url, {"chat_id": chat_id, "text": full_msg}, as_json=True)
    print(f"Telegram 전송 완료: 로또 {draw}회")


# ── Kakao 전송 ────────────────────────────────────────────────
def send_kakao():
    rest_key = os.environ["KAKAO_REST_API_KEY"]
    refresh  = os.environ["KAKAO_REFRESH_TOKEN"]
    res = _post("https://kauth.kakao.com/oauth/token", {
        "grant_type": "refresh_token", "client_id": rest_key, "refresh_token": refresh,
    })
    token = res["access_token"]

    # ── refresh_token 만료 감지 ───────────────────────────────
    # 카카오는 refresh_token 만료 1개월 미만 시 새 토큰을 함께 반환
    if res.get("refresh_token"):
        print("=" * 50)
        print("⚠️  KAKAO_REFRESH_TOKEN 갱신 필요!")
        print("   GitHub Settings > Secrets > KAKAO_REFRESH_TOKEN")
        print("   새 토큰을 수동으로 업데이트하세요 (60일 연장)")
        print("=" * 50)

    def _kakao_send(text):
        tmpl = json.dumps({"object_type":"text","text":text[:2000],
                           "link":{"web_url":"","mobile_web_url":""}}, ensure_ascii=False)
        _post("https://kapi.kakao.com/v2/api/talk/memo/default/send",
              {"template_object": tmpl},
              {"Authorization": f"Bearer {token}",
               "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})

    _kakao_send(msg1)
    _kakao_send(msg2)
    print(f"Kakao 전송 완료: 로또 {draw}회")


# ── 자동 선택 ─────────────────────────────────────────────────
if os.environ.get("TELEGRAM_BOT_TOKEN"):
    send_telegram()
elif os.environ.get("KAKAO_REST_API_KEY"):
    send_kakao()
else:
    print("오류: TELEGRAM_BOT_TOKEN 또는 KAKAO_REST_API_KEY 환경변수 필요")
    sys.exit(1)


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
