"""
GitHub Actions 전용 카카오톡 전송.
환경변수: KAKAO_REST_API_KEY, KAKAO_REFRESH_TOKEN
PC가 꺼져있어도 GitHub Actions 서버에서 실행됨.
"""
import json, os, sys, urllib.parse, urllib.request
from pathlib import Path

REST_API_KEY  = os.environ.get("KAKAO_REST_API_KEY", "")
REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN", "")
TOKEN_URL     = "https://kauth.kakao.com/oauth/token"
MEMO_URL      = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
PRED_PATH     = Path("tools/lotto/data/lotto_prediction.json")
REPORT_DIR    = Path("tools/lotto/reports")

if not REST_API_KEY or not REFRESH_TOKEN:
    print("오류: KAKAO_REST_API_KEY 또는 KAKAO_REFRESH_TOKEN 환경변수 없음")
    print("GitHub Settings > Secrets > Actions 에 두 값을 등록하세요")
    sys.exit(1)

if not PRED_PATH.exists():
    print(f"오류: {PRED_PATH} 없음 — predict.py가 먼저 실행되어야 합니다")
    sys.exit(1)


def _post(url: str, data: dict, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req  = urllib.request.Request(url, data=body, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ── 액세스 토큰 갱신 ─────────────────────────────────────────
result = _post(TOKEN_URL, {
    "grant_type":    "refresh_token",
    "client_id":     REST_API_KEY,
    "refresh_token": REFRESH_TOKEN,
})
ACCESS_TOKEN = result["access_token"]
print(f"토큰 갱신 완료 (만료: {result.get('expires_in', '?')}초 후)")


# ── 예측 데이터 ───────────────────────────────────────────────
pred     = json.loads(PRED_PATH.read_text(encoding="utf-8"))
games    = pred.get("games", [])
draw     = pred["draw"]
best_idx = max(range(len(games)), key=lambda i: games[i]["overall_coherence"]) if games else 0
bg       = games[best_idx] if games else pred
core     = set(bg.get("core_numbers", []))
ind      = bg.get("individual_coherence", {})
lo, hi   = pred.get("sum_range", [100, 175])


# ── 메시지 1: 5게임 목록 ─────────────────────────────────────
lines1 = [f"🎱로또{draw}회예측(3모델합의정합성)"]
for g, gr in enumerate(games):
    nums   = " ".join(f"{n:02d}" for n in gr["numbers"])
    marker = "◀" if g == best_idx else ""
    lines1.append(f"{chr(65+g)}:{nums} 합{gr['sum']} {gr['overall_coherence']:.0f}%{marker}")
msg1 = "\n".join(lines1)[:200]


# ── 메시지 2: 대표 게임 상세 ──────────────────────────────────
nums_detail = " ".join(
    f"{'★' if n in core else ''}{n}:{ind.get(str(n), 0):.0f}%"
    for n in bg["numbers"]
)
msg2 = (
    f"🎱로또{draw}회 대표(Game{chr(65+best_idx)}) 상세\n"
    f"{nums_detail}\n"
    f"핵심{len(core)}개 전체정합성{bg['overall_coherence']:.0f}%\n"
    f"합계{bg['sum']}(유효{lo}~{hi})\n"
    f"⚠️정합성=모델일치도,당첨확률아님"
)[:200]


# ── 전송 함수 ──────────────────────────────────────────────────
def _send(text: str) -> None:
    template = json.dumps({
        "object_type": "text",
        "text":        text,
        "link":        {"web_url": "", "mobile_web_url": ""},
    }, ensure_ascii=False)
    _post(MEMO_URL, {"template_object": template}, {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type":  "application/x-www-form-urlencoded;charset=utf-8",
    })


_send(msg1)
print(f"메시지1 전송: {draw}회 5게임 목록")
_send(msg2)
print(f"메시지2 전송: 대표 게임 상세")


# ── 리포트 저장 ────────────────────────────────────────────────
from datetime import date

REPORT_DIR.mkdir(parents=True, exist_ok=True)
today    = date.today().isoformat()
rpt_path = REPORT_DIR / f"{today}.md"

rows = []
for g, gr in enumerate(games):
    marker = " ◀대표" if g == best_idx else ""
    rows.append(
        f"| {chr(65+g)}{marker} | {gr['numbers']} | {gr['sum']} "
        f"| {gr['odd_count']}홀{6-gr['odd_count']}짝 | {gr['overall_coherence']:.1f}% |"
    )

detail_rows = [
    f"| {n} | {ind.get(str(n), 0):.1f}% | {'★핵심' if n in core else '보조'} |"
    for n in bg["numbers"]
]

bt = pred.get("backtest", {})
content = "\n".join([
    f"# 로또 예측 — 제{draw}회 ({today})",
    f"방법: {pred.get('method', '')}",
    "",
    "## 5게임",
    "| 게임 | 번호 | 합계 | 홀짝 | 정합성 |",
    "|------|------|------|------|--------|",
    *rows,
    "",
    f"## 대표 게임 (Game {chr(65+best_idx)}) 상세",
    "| 번호 | 정합성 | 구분 |",
    "|------|--------|------|",
    *detail_rows,
    "",
    "## 백테스트",
    f"TOP12 평균 {bt.get('avg_hits', 0)}개 적중 / {bt.get('n_test', 0)}회 검증",
])
rpt_path.write_text(content, encoding="utf-8")
print(f"리포트 저장: {rpt_path}")
