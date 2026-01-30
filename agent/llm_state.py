# agent/llm_state.py
"""현재 LLM provider(openai|ollama)와 model을 저장. 에이전트가 '모델 바꿔줘' 시 set_llm으로 변경."""
from __future__ import annotations

import os
from typing import Tuple

_DEFAULT_PROVIDER = (os.environ.get("JARVIS_LLM_PROVIDER") or "openai").strip().lower()
if _DEFAULT_PROVIDER not in ("openai", "ollama"):
    _DEFAULT_PROVIDER = "openai"

_DEFAULT_MODEL_OPENAI = os.environ.get("JARVIS_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
_DEFAULT_MODEL_OLLAMA = os.environ.get("JARVIS_LLM_OLLAMA_MODEL") or "gemma3:12b"

_current: Tuple[str, str] = (_DEFAULT_PROVIDER, _DEFAULT_MODEL_OPENAI if _DEFAULT_PROVIDER == "openai" else _DEFAULT_MODEL_OLLAMA)


def get_llm() -> Tuple[str, str]:
    """(provider, model) 반환. provider는 'openai' 또는 'ollama'."""
    return _current[0], _current[1]


def set_llm(provider: str, model: str) -> None:
    global _current
    p = (provider or "").strip().lower() or "openai"
    if p not in ("openai", "ollama"):
        p = "openai"
    m = (model or "").strip()
    if not m:
        m = _DEFAULT_MODEL_OPENAI if p == "openai" else _DEFAULT_MODEL_OLLAMA
    _current = (p, m)


def get_provider() -> str:
    return get_llm()[0]


def get_model() -> str:
    return get_llm()[1]
