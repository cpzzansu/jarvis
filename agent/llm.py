# agent/llm.py
"""단일 진입점: 현재 provider(openai|ollama)에 따라 chat_text/chat_json 디스패치."""
from __future__ import annotations

from . import llm_state
from . import llm_openai
from . import llm_ollama


def get_provider() -> str:
    return llm_state.get_provider()


def get_model() -> str:
    return llm_state.get_model()


def set_llm(provider: str, model: str) -> None:
    llm_state.set_llm(provider, model)


def chat_text(messages, temperature=0.2) -> str:
    provider, model = llm_state.get_llm()
    if provider == "ollama":
        return llm_ollama.chat_text(messages, model=model, temperature=temperature)
    return llm_openai.chat_text(messages, model=model, temperature=temperature)


def chat_json(messages, temperature=0):
    provider, model = llm_state.get_llm()
    if provider == "ollama":
        return llm_ollama.chat_json(messages, model=model, temperature=temperature)
    return llm_openai.chat_json(messages, model=model, temperature=temperature)
