# agent/llm_ollama.py
"""Ollama /api/chat 호출로 chat_text, chat_json 제공."""
from __future__ import annotations

import json
import re
import urllib.request
import urllib.error

from .config import OLLAMA_URL


def _extract_json(text: str) -> dict | None:
    """응답에서 JSON 객체 추출. 마크다운/앞뒤 문장이 있어도 {...} 또는 ```json ... ``` 파싱 시도."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # ```json ... ``` 또는 ``` ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # 첫 번째 { ~ 마지막 }
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def _ollama_chat(messages: list, model: str, stream: bool = False) -> dict:
    """Ollama /api/chat 호출. stream=False면 한 번에 응답."""
    url = (OLLAMA_URL or "http://localhost:11434/api/chat").strip()
    body = json.dumps({"model": model, "messages": messages, "stream": stream}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read().decode("utf-8"))
            return out
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {e.code}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"Ollama request failed: {e}") from e


def chat_text(messages: list, model: str, temperature: float = 0.2) -> str:
    """Ollama로 텍스트 응답. messages는 [{"role":"user","content":"..."}, ...]."""
    resp = _ollama_chat(messages, model=model, stream=False)
    msg = resp.get("message") or {}
    return (msg.get("content") or "").strip()


def chat_json(messages: list, model: str, temperature: float = 0, max_retries: int = 3) -> dict:
    """Ollama로 JSON 응답. 파싱 실패 시 응답에서 JSON 추출 시도 후 재시도."""
    for attempt in range(max_retries):
        resp = _ollama_chat(messages, model=model, stream=False)
        msg = resp.get("message") or {}
        content = (msg.get("content") or "").strip()
        obj = _extract_json(content)
        if obj is not None and isinstance(obj, dict):
            return obj
        messages = list(messages) + [{"role": "system", "content": "REMINDER: Output ONLY valid JSON, no other text."}]
    raise RuntimeError("Ollama failed to return valid JSON after retries")
