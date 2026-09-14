"""
통합 알림 전송 — Telegram(우선) + Kakao(폴백).

카카오 "나에게 보내기"는 refresh_token이 주기적으로 만료되고(KOE322),
개발자 콘솔 설정도 쉽게 깨져서(KOE006) 자동화에 부적합했다.
Telegram 봇 토큰은 만료가 없고 콘솔 설정도 불필요하다.

환경변수:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (우선 채널)
  KAKAO_REST_API_KEY, KAKAO_REFRESH_TOKEN (폴백 채널)

사용:
  from notify import send_message
  ok = send_message("본문", title="선택 제목")
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def _post(url: str, data: dict, headers: dict | None = None, timeout: int = 15) -> tuple[int, str]:
    body = urllib.parse.urlencode(data).encode()
    req  = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")
    except Exception as e:
        return 0, str(e)


# ── Telegram ─────────────────────────────────────────────────

def _send_telegram(text: str) -> tuple[bool, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat  = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat):
        missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat)) if not v]
        detail = f"Telegram 시크릿 미설정: {', '.join(missing)}"
        print(f"[notify] {detail}")
        return False, detail
    # Telegram 메시지 최대 4096자
    status, resp = _post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"},
    )
    ok     = status == 200
    detail = "OK" if ok else f"Telegram FAIL {status}: {resp[:200]}"
    print(f"[notify] {detail}")
    return ok, detail


# ── Kakao (폴백) ─────────────────────────────────────────────

def _kakao_token() -> tuple[str, str]:
    rest_key      = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN", "").strip()
    if not (rest_key and refresh_token):
        missing = [n for n, v in (("KAKAO_REST_API_KEY", rest_key), ("KAKAO_REFRESH_TOKEN", refresh_token)) if not v]
        return "", f"Kakao 시크릿 미설정: {', '.join(missing)}"
    status, resp = _post("https://kauth.kakao.com/oauth/token", {
        "grant_type":    "refresh_token",
        "client_id":     rest_key,
        "refresh_token": refresh_token,
    })
    if status != 200:
        detail = f"Kakao 토큰 갱신 실패 {status}: {resp[:200]}"
        print(f"[notify] {detail}")
        return "", detail
    try:
        token = json.loads(resp).get("access_token", "")
        return (token, "") if token else ("", f"Kakao 토큰 갱신 응답에 access_token 없음: {resp[:200]}")
    except Exception as e:
        return "", f"Kakao 토큰 응답 파싱 실패: {e}"


def _send_kakao(text: str) -> tuple[bool, str]:
    token, detail = _kakao_token()
    if not token:
        return False, detail
    template = json.dumps({
        "object_type": "text",
        "text":        text[:1900],
        "link":        {"web_url": "", "mobile_web_url": ""},
    }, ensure_ascii=False)
    status, resp = _post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        {"template_object": template},
        {"Authorization": f"Bearer {token}"},
    )
    ok     = status == 200
    detail = "OK" if ok else f"Kakao FAIL {status}: {resp[:200]}"
    print(f"[notify] {detail}")
    return ok, detail


# ── 공개 API ────────────────────────────────────────────────

def send_message_detailed(text: str, title: str | None = None) -> tuple[bool, str]:
    """Telegram 우선, 실패 시 Kakao 폴백. (성공여부, 진단상세) 반환.
    성공 시 detail은 어떤 채널로 보냈는지, 실패 시 두 채널 각각의 실패 사유를 담는다."""
    body = f"{title}\n\n{text}" if title else text
    ok_tg, detail_tg = _send_telegram(body)
    if ok_tg:
        return True, "Telegram"
    ok_kk, detail_kk = _send_kakao(body)
    if ok_kk:
        return True, "Kakao"
    combined = f"Telegram({detail_tg}) / Kakao({detail_kk})"
    print(f"[notify] 모든 알림 채널 전송 실패 — {combined}")
    return False, combined


def send_message(text: str, title: str | None = None) -> bool:
    """Telegram 우선, 실패 시 Kakao 폴백. 하나라도 성공하면 True.
    실패 사유를 알아야 하면 send_message_detailed()를 사용할 것."""
    ok, _ = send_message_detailed(text, title)
    return ok


if __name__ == "__main__":
    import sys
    msg = sys.argv[1] if len(sys.argv) > 1 else "[테스트] notify.py 동작 확인"
    ok, detail = send_message_detailed(msg)
    print("전송 결과:", ok, "-", detail)
    sys.exit(0 if ok else 1)
