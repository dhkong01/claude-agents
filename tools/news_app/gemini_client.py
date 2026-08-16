"""
Gemini API 공용 클라이언트 (무료 티어)
Interactions API(https://ai.google.dev/gemini-api/docs)를 requests로 직접 호출.
SDK 없이 REST 직접 호출 (저장소 의존성 최소화 컨벤션 유지).
"""
import json
import os
import re
import sys

import requests

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

# 지역 에이전트(가벼운 요약)는 Flash-Lite, 섹터매퍼/오케스트레이터(교차 분석)는 Flash
MODEL_LIGHT = os.environ.get("GEMINI_MODEL_LIGHT", "gemini-2.5-flash-lite")
MODEL_HEAVY = os.environ.get("GEMINI_MODEL_HEAVY", "gemini-2.5-flash")


def call_gemini(system_prompt: str, user_prompt: str, model: str = MODEL_LIGHT) -> str | None:
    """Gemini Interactions API 호출. 실패 시 None 반환 (예외를 던지지 않음)."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[gemini_client] GEMINI_API_KEY 미설정 — 호출 생략", file=sys.stderr)
        return None

    try:
        resp = requests.post(
            API_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "model": model,
                "system_instruction": system_prompt,
                "input": user_prompt,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"[gemini_client] API 오류 {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
            return None
        data = resp.json()
        texts = [
            block.get("text", "")
            for step in data.get("steps", [])
            if step.get("type") == "model_output"
            for block in step.get("content", [])
            if block.get("type") == "text"
        ]
        text = "".join(texts)
        return text or None
    except Exception as e:
        print(f"[gemini_client] 호출 실패: {e}", file=sys.stderr)
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
