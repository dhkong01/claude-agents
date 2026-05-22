"""
KakaoTalk "나에게 보내기" 초기 인증 설정.
최초 1회 실행 후 토큰 자동 갱신.

사전 준비:
  1. https://developers.kakao.com → 내 애플리케이션 → 앱 생성
  2. 앱 → 카카오 로그인 → 활성화 ON
  3. 앱 → 카카오 로그인 → Redirect URI: https://example.com/oauth
  4. 앱 → 동의항목 → "카카오톡 메시지 전송" 동의 ON
  5. 앱 → 앱 키 → REST API 키 복사
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG_PATH  = Path(__file__).parent / "kakao_config.json"
TOKEN_URL    = "https://kauth.kakao.com/oauth/token"
AUTH_BASE    = "https://kauth.kakao.com/oauth/authorize"
REDIRECT_URI = "https://example.com/oauth"


def _post(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req  = urllib.request.Request(url, data=body)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def setup():
    print("=" * 55)
    print("  KakaoTalk 나에게 보내기 초기 설정")
    print("=" * 55)

    rest_key = input("\n① REST API 키 입력: ").strip()
    if not rest_key:
        print("키가 없습니다. 종료.")
        sys.exit(1)

    auth_url = (
        f"{AUTH_BASE}?client_id={rest_key}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        "&response_type=code"
        "&scope=talk_message"
    )
    print(f"\n② 아래 URL을 브라우저에서 열어 카카오 로그인 후 동의하세요:")
    print(f"\n  {auth_url}\n")
    print("③ 동의 후 리다이렉트된 URL의 ?code= 값을 복사하세요.")
    print("   예: https://example.com/oauth?code=XXXXXXXX")

    code = input("\n인증 코드 입력: ").strip()
    if not code:
        print("코드가 없습니다. 종료.")
        sys.exit(1)

    print("\n토큰 발급 중...")
    try:
        result = _post(TOKEN_URL, {
            "grant_type":   "authorization_code",
            "client_id":    rest_key,
            "redirect_uri": REDIRECT_URI,
            "code":         code,
        })
    except Exception as e:
        print(f"토큰 발급 실패: {e}")
        sys.exit(1)

    if "access_token" not in result:
        print(f"오류: {result}")
        sys.exit(1)

    from datetime import datetime, timedelta
    expires_in = result.get("expires_in", 21599)
    cfg = {
        "rest_api_key":    rest_key,
        "access_token":    result["access_token"],
        "refresh_token":   result.get("refresh_token", ""),
        "token_expires_at": (datetime.now() + timedelta(seconds=expires_in - 60)).isoformat(),
    }
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✓ 설정 저장 완료: {CONFIG_PATH}")

    # 테스트 메시지 발송
    test = input("\n테스트 메시지를 나에게 보낼까요? (y/n): ").strip().lower()
    if test == "y":
        import urllib.request as req_lib
        template = json.dumps({
            "object_type": "text",
            "text": "✅ KakaoTalk 주식 포트폴리오 알림 설정 완료!\n매일 리밸런싱 결과를 받아보실 수 있습니다.",
            "link": {"web_url": "", "mobile_web_url": ""},
        }, ensure_ascii=False)
        body = urllib.parse.urlencode({"template_object": template}).encode()
        r = req_lib.Request(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            data=body,
            headers={"Authorization": f"Bearer {cfg['access_token']}",
                     "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        )
        try:
            with req_lib.urlopen(r, timeout=10) as resp:
                print(f"✓ 테스트 메시지 발송 성공! 카카오톡을 확인하세요.")
        except Exception as e:
            print(f"✗ 발송 실패: {e}")


if __name__ == "__main__":
    setup()
