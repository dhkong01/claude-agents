"""
Gemini API 공용 클라이언트 (무료 티어)
generateContent 엔드포인트(https://ai.google.dev/api/generate-content)를 requests로 직접 호출.
SDK 없이 REST 직접 호출 (저장소 의존성 최소화 컨벤션 유지).
"""
import json
import os
import re
import sys
import time

import requests

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# 지역 에이전트(가벼운 요약)는 Flash-Lite, 섹터매퍼/오케스트레이터(교차 분석)는 Flash.
# Google이 모델을 수시로 폐기(404 "no longer available to new users")하므로
# 핀 고정 모델 → -latest 별칭 → 구세대 안정 모델 순으로 폴백. env var로도 override 가능.
MODEL_LIGHT = os.environ.get("GEMINI_MODEL_LIGHT", "gemini-3.5-flash-lite")
MODEL_HEAVY = os.environ.get("GEMINI_MODEL_HEAVY", "gemini-3.5-flash")

_FALLBACKS = {
    MODEL_LIGHT: [MODEL_LIGHT, "gemini-flash-lite-latest", "gemini-2.0-flash"],
    MODEL_HEAVY: [MODEL_HEAVY, "gemini-flash-latest", "gemini-2.0-flash"],
}

_RETRY_STATUS = {429, 500, 502, 503, 504}


def _post_once(model: str, api_key: str, system_prompt: str, user_prompt: str):
    return requests.post(
        f"{API_BASE}/{model}:generateContent",
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
        },
        timeout=60,
    )


def call_gemini(system_prompt: str, user_prompt: str, model: str = MODEL_LIGHT) -> str | None:
    """Gemini generateContent API 호출. 일시적 오류는 재시도, 모델 폐기 시 폴백. 실패 시 None."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[gemini_client] GEMINI_API_KEY 미설정 — 호출 생략", file=sys.stderr)
        return None

    # 중복 제거하며 폴백 후보 구성
    candidates_models: list[str] = []
    for m in _FALLBACKS.get(model, [model]):
        if m not in candidates_models:
            candidates_models.append(m)

    for mi, m in enumerate(candidates_models):
        for attempt in range(3):
            try:
                resp = _post_once(m, api_key, system_prompt, user_prompt)
            except Exception as e:
                print(f"[gemini_client] {m} 요청 예외(시도 {attempt+1}/3): {e}", file=sys.stderr)
                time.sleep(2 * (attempt + 1))
                continue

            if resp.status_code == 200:
                data = resp.json()
                cand = data.get("candidates", [])
                if not cand:
                    print(f"[gemini_client] {m} 응답에 candidates 없음: {json.dumps(data)[:200]}", file=sys.stderr)
                    return None
                parts = cand[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                return text or None

            if resp.status_code in _RETRY_STATUS:
                print(f"[gemini_client] {m} 일시적 오류 {resp.status_code} (시도 {attempt+1}/3)", file=sys.stderr)
                time.sleep(2 * (attempt + 1))
                continue

            # 404/400 등 → 이 모델은 폐기/미지원. 다음 폴백 모델로.
            print(f"[gemini_client] {m} 사용 불가 {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            if mi < len(candidates_models) - 1:
                print(f"[gemini_client] → 폴백 모델 {candidates_models[mi+1]} 시도", file=sys.stderr)
            break

    return None


def call_gemini_json(system_prompt: str, user_prompt: str, model: str = MODEL_LIGHT) -> dict | None:
    """Gemini 호출 후 응답에서 JSON 객체를 파싱. 실패 시 None."""
    text = call_gemini(system_prompt, user_prompt, model=model)
    if not text:
        return None
    return _extract_json(text)


def _extract_json(text: str) -> dict | None:
    """응답이 코드펜스(```json ... ```)로 감싸져 있거나 앞뒤에 설명이 붙어도 JSON 객체를 추출."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    try:
        return json.loads(text)
    except Exception as e:
        print(f"[gemini_client] JSON 파싱 실패: {e}", file=sys.stderr)
        return None
