# agent/recovery.py
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state import get_current_workdir


STATE_FILENAME = "recovery_state.json"


@dataclass
class BackupEntry:
    original: str
    backup: str
    ts: str


def _project_data_dir() -> Path:
    cwd = get_current_workdir()
    if cwd is None:
        raise RuntimeError("no current project. run set_project first")
    d = cwd / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path() -> Path:
    return _project_data_dir() / STATE_FILENAME


def _now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_state() -> Dict[str, Any]:
    p = _state_path()
    if not p.exists():
        return {"last": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"last": []}


def save_state(state: Dict[str, Any]) -> None:
    p = _state_path()
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def make_backup_for_file(abs_path: Path, *, ts: Optional[str] = None) -> Optional[BackupEntry]:
    """
    abs_path가 존재할 때만 백업을 만든다.
    backup 파일명: <name>.bak.<timestamp>
    """
    if not abs_path.exists() or not abs_path.is_file():
        return None

    ts = ts or _now_ts()
    bak = abs_path.with_name(f"{abs_path.name}.bak.{ts}")

    # 덮어쓰기 방지: 같은 ts로 이미 있으면 suffix 증가
    if bak.exists():
        i = 2
        while True:
            cand = abs_path.with_name(f"{abs_path.name}.bak.{ts}.{i}")
            if not cand.exists():
                bak = cand
                break
            i += 1

    shutil.copy2(abs_path, bak)
    return BackupEntry(original=str(abs_path), backup=str(bak), ts=ts)


def record_last(entries: List[BackupEntry]) -> None:
    state = load_state()
    state["last"] = [e.__dict__ for e in entries]
    save_state(state)


def get_last_entries() -> List[BackupEntry]:
    state = load_state()
    out: List[BackupEntry] = []
    for item in state.get("last", []) or []:
        try:
            out.append(BackupEntry(**item))
        except Exception:
            pass
    return out


def undo_last() -> Dict[str, Any]:
    """
    마지막 백업을 original 위치로 복원한다.
    - original이 없더라도 그대로 덮어써서 복원(파일을 되살림)
    - 복원이 끝나면 last를 비운다.
    """
    entries = get_last_entries()
    if not entries:
        return {"ok": False, "error": "no_backup", "detail": "되돌릴 백업이 없습니다."}

    restored = []
    missing = []

    for e in entries:
        bak = Path(e.backup)
        orig = Path(e.original)

        if not bak.exists():
            missing.append({"original": e.original, "backup": e.backup})
            continue

        orig.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bak, orig)
        restored.append({"original": e.original, "backup": e.backup})

    # 성공/부분성공 여부와 관계없이 last는 비움 (원하면 유지로 바꿀 수 있음)
    record_last([])

    return {"ok": True, "restored": restored, "missing": missing}