from __future__ import annotations
from pathlib import Path

from .config import SAFE_ROOTS, ALLOWED_TEXT_EXTS
from .state import get_current_workdir

def _is_under(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False

def ensure_under_safe_roots(input_path: str) -> Path:
    """
    - absolute path: validate
    - relative path:
      - if CURRENT_WORKDIR is set -> resolve relative to it
      - else -> resolve relative to SAFE_ROOTS[0]
    """
    p = Path(input_path).expanduser()

    if not p.is_absolute():
        base = get_current_workdir() or SAFE_ROOTS[0]
        p = base / p

    rp = p.resolve()

    for root in SAFE_ROOTS:
        if _is_under(root, rp):
            return rp

    roots_str = ", ".join(str(r) for r in SAFE_ROOTS)
    raise PermissionError(f"Path outside SAFE_ROOTS: {rp} (allowed roots: {roots_str})")

def _is_text_path(p: Path) -> bool:
    return p.suffix.lower() in ALLOWED_TEXT_EXTS

def ensure_text_safe(p: Path) -> None:
    if not _is_text_path(p):
        raise PermissionError(f"Disallowed file extension: {p.suffix} (text only)")
    if "\x00" in str(p):
        raise PermissionError("Invalid path")
