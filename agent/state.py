from __future__ import annotations
from pathlib import Path
from typing import Optional

_CURRENT_WORKDIR: Optional[Path] = None

def get_current_workdir() -> Optional[Path]:
    return _CURRENT_WORKDIR

def set_current_workdir(p: Optional[Path]) -> None:
    global _CURRENT_WORKDIR
    _CURRENT_WORKDIR = p

def state_line() -> str:
    cwd = get_current_workdir()
    return f"STATE: current_workdir={str(cwd) if cwd else 'None'}"
