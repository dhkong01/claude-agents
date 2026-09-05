"""카카오 수동 인증 — 브라우저에서 직접 code를 복사해서 붙여넣기"""
import json, sys, urllib.parse, urllib.request
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "kakao_config.json"
cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
REST_KEY = cfg.get("rest_api_key", "")
if not REST_KEY:
    print("kakao_config.json에 rest_api_key가 없습니다.")
    sys.exit(1)

REDIRECT_URI = "https://example.com"
auth_url = (
    f"https://kauth.kakao.com/oauth/authorize?client_id={REST_KEY}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
    "&response_type=code&scope=talk_message"
)

print("\n" + "=" * 60)
print("STEP 1. 아래 URL을 브라우저에 복사해서 여세요:")
print()
print(auth_url)
print()
print("STEP 2. 카카오 로그인 → '동의하기' 클릭")
print()
print("STEP 3. https://example.com/?code=XXXX... 로 이동됨")
print("        주소창에서 code= 뒤의 값을 전부 복사하세요")
print("=" * 60)
print()

code = input("STEP 4. 복사한 code 붙여넣기: ").strip()
if not code:
    print("code가 없습니다.")
    sys.exit(1)

# code → token 교환
print("\n토큰 교환 중...")
body = urllib.parse.urlencode({
    "grant_type": "authorization_code",
    "client_id": REST_KEY,
    "redirect_uri": REDIRECT_URI,
    "code": code,
}).encode()

try:
    resp = urllib.request.urlopen(
        urllib.request.Request("https://kauth.kakao.com/oauth/token", data=body),
        timeout=15,
    )
    res = json.loads(resp.read())
except urllib.error.HTTPError as e:
    body_err = e.read().decode("utf-8", errors="ignore")
    print(f"토큰 교환 실패 (HTTP {e.code}): {body_err}")
    sys.exit(1)

if "refresh_token" not in res:
    print(f"refresh_token 없음. 응답: {res}")
    sys.exit(1)

cfg["access_token"] = res["access_token"]
cfg["refresh_token"] = res["refresh_token"]
CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

print("\n인증 성공!")
print(f"  access_token  : {res['access_token'][:20]}...")
print(f"  refresh_token : {res['refresh_token'][:20]}...")
print(f"\n--- GitHub Secrets 등록값 ---")
print(f"KAKAO_REST_API_KEY  = {REST_KEY}")
print(f"KAKAO_REFRESH_TOKEN = {res['refresh_token']}")
