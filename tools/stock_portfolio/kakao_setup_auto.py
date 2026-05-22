"""
카카오톡 나에게 보내기 — 자동 인증 설정
로컬 콜백 서버로 OAuth 코드 자동 캡처 → 토큰 발급 → 저장 → 테스트까지 자동
사용자 액션: REST API 키 입력 + 브라우저 동의하기 클릭 1회
"""
import json
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT         = 8765
REDIRECT_URI = f"http://localhost:{PORT}/callback"
CONFIG_PATH  = Path(__file__).parent / "kakao_config.json"
TOKEN_URL    = "https://kauth.kakao.com/oauth/token"
AUTH_BASE    = "https://kauth.kakao.com/oauth/authorize"
DEV_URL      = "https://developers.kakao.com/console/app"

_auth_code: list[str] = []   # thread-safe shared state

HTML_OK = (
    "<html><head><meta charset='utf-8'>"
    "<style>body{font-family:sans-serif;text-align:center;margin-top:80px;background:#f0f8ff}"
    "h2{color:#1B3A6B}p{color:#555}</style></head>"
    "<body><h2>&#10003; 카카오 인증 완료!</h2>"
    "<p>이 창을 닫고 터미널로 돌아가세요.</p></body></html>"
).encode("utf-8")
HTML_ERR = (
    "<html><head><meta charset='utf-8'></head>"
    "<body><h2>&#10007; 인증 실패</h2><p>다시 시도해 주세요.</p></body></html>"
).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            _auth_code.append(params["code"][0])
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_OK)
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(HTML_ERR)

    def log_message(self, *args):
        pass  # 로그 억제


def _wait_for_code(timeout: int = 180) -> str | None:
    srv = HTTPServer(("localhost", PORT), _Handler)
    srv.timeout = timeout
    srv.handle_request()
    return _auth_code[0] if _auth_code else None


def _post(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req  = urllib.request.Request(url, data=body)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def setup():
    print("\n" + "=" * 55)
    print("  KakaoTalk 나에게 보내기  자동 설정")
    print("=" * 55)

    # ─ 1. 개발자 앱 준비 안내 ─────────────────────────
    print("\n[1단계]  카카오 개발자 콘솔이 열립니다.")
    print("         앱이 없으면 '애플리케이션 추가하기'로 생성하세요.")
    print("         앱 설정 시 아래를 확인하세요:\n")
    print("  ① 카카오 로그인  →  활성화  ON")
    print("  ② 동의항목  →  카카오톡 메시지 전송  →  동의 ON")
    print(f"  ③ Redirect URI 추가:  {REDIRECT_URI}")
    print("  ④ 앱 키  →  REST API 키  복사")
    input("\n  준비되면 Enter ▶ (브라우저가 자동으로 열립니다)")
    webbrowser.open(DEV_URL)

    # ─ 2. REST API 키 입력 ────────────────────────────
    rest_key = input("\nREST API 키 붙여넣기: ").strip()
    if not rest_key:
        print("키가 없습니다. 종료.")
        sys.exit(1)

    # ─ 3. 인증 URL 자동 오픈 → 로컬 서버 대기 ─────────
    auth_url = (
        f"{AUTH_BASE}?client_id={rest_key}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        "&response_type=code&scope=talk_message"
    )
    print("\n[2단계]  브라우저에서 카카오 로그인 후 '동의하기'를 클릭하세요.")
    print("         (이미 로그인 상태면 클릭 한 번으로 완료됩니다)")
    webbrowser.open(auth_url)
    print("         인증 대기 중... (최대 3분)")

    code = _wait_for_code(timeout=180)
    if not code:
        print("\n인증 시간 초과. 다시 시도하세요.")
        sys.exit(1)
    print("  ✓ 인증 코드 수신 완료")

    # ─ 4. 토큰 교환 ───────────────────────────────────
    print("\n[3단계]  토큰 발급 중...")
    try:
        result = _post(TOKEN_URL, {
            "grant_type":   "authorization_code",
            "client_id":    rest_key,
            "redirect_uri": REDIRECT_URI,
            "code":         code,
        })
    except Exception as e:
        print(f"  토큰 발급 실패: {e}")
        sys.exit(1)

    if "access_token" not in result:
        print(f"  오류 응답: {result}")
        sys.exit(1)

    # ─ 5. 저장 ────────────────────────────────────────
    expires_in = result.get("expires_in", 21599)
    cfg = {
        "rest_api_key":    rest_key,
        "access_token":    result["access_token"],
        "refresh_token":   result.get("refresh_token", ""),
        "token_expires_at": (
            datetime.now() + timedelta(seconds=expires_in - 60)
        ).isoformat(),
    }
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ 설정 저장: {CONFIG_PATH}")

    # ─ 6. 테스트 메시지 발송 ──────────────────────────
    print("\n[4단계]  테스트 메시지 발송...")
    try:
        from kakao_sender import test_connection  # type: ignore[import]
        test_connection()
        print("\n  카카오톡 '나에게 보내기' 채팅을 확인하세요!")
        print("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  설정 완료. 매일 run_pipeline.py 실행 시 자동 발송됩니다.")
    except Exception as e:
        print(f"  테스트 발송 실패: {e}")


if __name__ == "__main__":
    setup()
