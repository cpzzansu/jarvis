from __future__ import annotations
from pathlib import Path
from typing import Optional

# 세션 상태(단일 프로세스 기준)
_CURRENT_WORKDIR: Optional[Path] = None


def set_current_workdir(p: Path) -> None:
    global _CURRENT_WORKDIR
    _CURRENT_WORKDIR = p


def get_current_workdir() -> Optional[Path]:
    return _CURRENT_WORKDIR


def state_line() -> str:
    """
    매 턴 LLM에 주입할 상태 문자열.
    """
    cwd = _CURRENT_WORKDIR
    if cwd is None:
        return "STATE: current_project=None"
    return f"STATE: current_project={cwd}"