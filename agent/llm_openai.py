# agent/llm_openai.py
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# ✅ jarvis 루트의 .env 강제 로드 (agent 폴더 기준 상위)
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=False)

_client: OpenAI | None = None

MODEL_DEFAULT = "gpt-4o-mini"


def _get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(f"OPENAI_API_KEY not set. Put it in {ENV_PATH} or switch to Ollama (set_llm ollama <model>).")
    _client = OpenAI(api_key=api_key)
    return _client


def _get_cli_model() -> str | None:
    """CLI 인자에서 모델을 읽습니다.
    지원:
      - --model <name>
      - --model=<name>
    """
    import sys

    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--model" and i + 1 < len(argv):
            v = (argv[i + 1] or "").strip()
            return v or None
        if a.startswith("--model="):
            v = a.split("=", 1)[1].strip()
            return v or None
    return None


def get_model() -> str:
    """모델 선택 우선순위: CLI 인자 > 환경변수 > .env(=load_dotenv로 이미 반영) > 기본값"""
    cli = _get_cli_model()
    if cli:
        return cli

    env = (os.getenv("JARVIS_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "").strip()
    if env:
        return env

    return MODEL_DEFAULT


SYSTEM_GUARD = """
You are an execution planner.
You MUST output ONLY ONE valid JSON object.
Never output text outside JSON.
"""

def chat_text(messages, model: str | None = None, temperature=0.2) -> str:
    """model이 None이면 get_model() 사용 (CLI/env 기본값)."""
    m = (model or "").strip() or get_model()
    msgs = [{"role": "system", "content": SYSTEM_GUARD}] + (messages or [])
    resp = _get_client().chat.completions.create(
        model=m,
        messages=msgs,
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()


def chat_json(messages, model: str | None = None, temperature=0):
    """model이 None이면 get_model() 사용."""
    m = (model or "").strip() or get_model()
    msgs = [{"role": "system", "content": SYSTEM_GUARD}] + (messages or [])

    for _ in range(3):
        resp = _get_client().chat.completions.create(
            model=m,
            messages=msgs,
            temperature=temperature,
        )
        content = (resp.choices[0].message.content or "").strip()
        try:
            return json.loads(content)
        except Exception:
            msgs.append({"role": "system", "content": "REMINDER: Output ONLY JSON."})

    raise RuntimeError("LLM failed to return valid JSON after 3 attempts")