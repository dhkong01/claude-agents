"""카카오 토큰 자동 발급 (비대화형) — REST API 키를 인자로 받음"""
import json, sys, urllib.parse, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import os
REST_KEY = (sys.argv[1] if len(sys.argv) > 1
            else os.environ.get("KAKAO_REST_API_KEY", ""))
if not REST_KEY:
    print("사용법: python kakao_auth_quick.py <REST_API_KEY>")
    print("또는 환경변수: set KAKAO_REST_API_KEY=<키값>")
    sys.exit(1)
PORT         = 8765
REDIRECT_URI = f"http://localhost:{PORT}/callback"
CONFIG_PATH  = Path(__file__).parent / "kakao_config.json"
TOKEN_URL    = "https://kauth.kakao.com/oauth/token"

_code = []

class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in p:
            _code.append(p["code"][0])
            self.send_response(200); self.send_header("Content-type","text/html;charset=utf-8"); self.end_headers()
            self.wfile.write("<html><body><h2>✅ 인증 완료! 이 창 닫으세요.</h2></body></html>".encode())
        else:
            self.send_response(400); self.end_headers()
    def log_message(self, *a): pass

auth_url = (f"https://kauth.kakao.com/oauth/authorize?client_id={REST_KEY}"
            f"&redirect_uri={urllib.parse.quote(REDIRECT_URI,safe='')}"
            "&response_type=code&scope=talk_message")

print("브라우저가 열립니다 - 카카오 로그인 후 동의하기 클릭하세요.")
webbrowser.open(auth_url)

srv = HTTPServer(("localhost", PORT), _H)
srv.timeout = 120
srv.handle_request()

if not _code:
    print("ERR: 인증 코드 수신 실패 (120초 초과)")
    sys.exit(1)

print(f"인증 코드 수신 완료. 토큰 교환 중...")
body = urllib.parse.urlencode({
    "grant_type":"authorization_code","client_id":REST_KEY,
    "redirect_uri":REDIRECT_URI,"code":_code[0]
}).encode()

try:
    resp = urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body), timeout=15)
    res  = json.loads(resp.read())
except urllib.error.HTTPError as e:
    err_body = e.read().decode("utf-8", errors="ignore")
    print(f"\n❌ 토큰 교환 실패 (HTTP {e.code})")
    print(f"   오류 내용: {err_body}")
    print(f"\n원인 해결책:")
    if "KOE101" in err_body or "invalid_client" in err_body:
        print("  → REST API 키가 틀렸습니다. developers.kakao.com에서 다시 확인하세요.")
    elif "KOE320" in err_body or "talk_message" in err_body:
        print("  → 동의항목 미설정: 카카오 로그인 → 동의항목 → 카카오톡 메시지 전송 → 선택 동의 설정")
    elif "KOE303" in err_body or "redirect_uri" in err_body:
        print("  → Redirect URI 불일치: 플랫폼 → Web → http://localhost:8765/callback 등록 확인")
    else:
        print("  → 개발자 콘솔에서 앱 설정을 확인하세요.")
    sys.exit(1)

if "refresh_token" not in res:
    print(f"\n❌ refresh_token 없음. 응답: {res}")
    sys.exit(1)

cfg = {"rest_api_key": REST_KEY, "refresh_token": res["refresh_token"],
       "access_token": res["access_token"]}
CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n✅ 성공!")
print(f"   refresh_token : {res['refresh_token'][:30]}...")
print(f"   저장 위치     : {CONFIG_PATH}")
print(f"\n--- GitHub Secret 등록값 ---")
print(f"KAKAO_REST_API_KEY  = {REST_KEY}")
print(f"KAKAO_REFRESH_TOKEN = {res['refresh_token']}")
