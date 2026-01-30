# agent/tools_fs.py
from __future__ import annotations

import os
import py_compile
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .state import get_current_workdir
from .paths import ensure_under_safe_roots
from .recovery import make_backup_for_file, record_last, BackupEntry


def _validate_python_syntax(path: Path) -> Tuple[bool, str]:
    """Python 파일이면 py_compile 검사. (성공, '') 또는 (실패, 에러메시지)."""
    if path.suffix.lower() != ".py":
        return True, ""
    try:
        py_compile.compile(str(path), doraise=True)
        return True, ""
    except py_compile.PyCompileError as e:
        return False, str(e)


# -------------------------
# path helpers
# -------------------------
def _abs_path(path: str) -> Path:
    cwd = get_current_workdir()
    if cwd is None:
        raise PermissionError("no current project. run set_project first")

    p = Path(path)
    if not p.is_absolute():
        p = (cwd / p).resolve()

    ensure_under_safe_roots(p)  # SAFE_ROOTS 밖 접근 방지
    return p


def _read_text_safe(p: Path) -> str:
    if not p.exists() or not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _write_text_safe(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# -------------------------
# list/read tools
# -------------------------
def list_dir(path: str = ".") -> Dict[str, Any]:
    p = _abs_path(path)
    if not p.exists() or not p.is_dir():
        return {"error": "not_a_dir", "path": str(p)}
    items = []
    for child in sorted(p.iterdir(), key=lambda x: x.name.lower()):
        items.append({
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
            "size": child.stat().st_size if child.exists() else 0,
        })
    return {"path": str(p), "items": items}


def read_tail(path: str, lines: int = 200) -> Dict[str, Any]:
    p = _abs_path(path)
    if not p.exists() or not p.is_file():
        return {"error": "file not found", "path": str(p)}
    txt = _read_text_safe(p)
    arr = txt.splitlines()
    tail = arr[-max(1, int(lines)):]
    return {"path": str(p), "lines": len(tail), "content": "\n".join(tail)}


# -------------------------
# preview helpers (Step D)
# -------------------------
def preview_write_file(path: str, content: str, overwrite: bool = True) -> Dict[str, Any]:
    p = _abs_path(path)
    before = _read_text_safe(p)
    if p.exists() and (not overwrite):
        return {"error": "file_exists", "path": str(p)}
    after = content
    return {"kind": "write", "path": str(p), "before": before, "after": after}


def preview_append_file(path: str, content: str) -> Dict[str, Any]:
    p = _abs_path(path)
    before = _read_text_safe(p)
    after = before + content
    return {"kind": "append", "path": str(p), "before": before, "after": after}


def _normalize_patch_content(content: str, op: str) -> str:
    """insert_after/insert_before/replace_between 시 content 앞뒤 개행 보장 (붙어서 SyntaxError 방지)."""
    if op == "replace_all":
        return content
    c = content if content is not None else ""
    if c and not c.startswith("\n"):
        c = "\n" + c
    if c and not c.endswith("\n"):
        c = c + "\n"
    return c


def preview_patch_file(
    path: str,
    op: str,
    content: str,
    anchor: Optional[str] = None,
    start_marker: Optional[str] = None,
    end_marker: Optional[str] = None,
    occurrence: int = 1,
) -> Dict[str, Any]:
    p = _abs_path(path)
    before = _read_text_safe(p)
    content = _normalize_patch_content(content or "", op)

    # patch 로직은 실제 patch_file과 동일해야 함
    txt = before

    if op == "replace_all":
        after = content

    elif op in ("insert_after", "insert_before"):
        if not anchor:
            return {"error": "anchor_required", "path": str(p)}
        idx = -1
        start = 0
        for _ in range(max(1, int(occurrence))):
            idx = txt.find(anchor, start)
            if idx < 0:
                break
            start = idx + len(anchor)
        if idx < 0:
            return {"error": "anchor_not_found", "path": str(p), "anchor": anchor}
        if op == "insert_after":
            pos = idx + len(anchor)
        else:
            pos = idx
        after = txt[:pos] + content + txt[pos:]

    elif op == "replace_between":
        if not (start_marker and end_marker):
            return {"error": "markers_required", "path": str(p)}
        a = txt.find(start_marker)
        if a < 0:
            return {"error": "start_marker_not_found", "path": str(p)}
        b = txt.find(end_marker, a + len(start_marker))
        if b < 0:
            return {"error": "end_marker_not_found", "path": str(p)}
        after = txt[: a + len(start_marker)] + content + txt[b:]

    else:
        return {"error": "unsupported_patch_op", "op": op, "path": str(p)}

    return {"kind": "patch", "path": str(p), "before": before, "after": after}


def preview_rename_path(src: str, dst: Optional[str] = None, new_name: Optional[str] = None) -> Dict[str, Any]:
    s = _abs_path(src)
    if not s.exists():
        return {"error": "src_not_found", "src": str(s)}

    if dst:
        d = _abs_path(dst)
    elif new_name:
        d = s.with_name(new_name)
        ensure_under_safe_roots(d)
    else:
        return {"error": "dst_or_new_name_required"}

    return {"kind": "rename", "src": str(s), "dst": str(d)}


def preview_mkdir(path: str, parents: bool = True) -> Dict[str, Any]:
    p = _abs_path(path)
    if p.exists():
        return {"kind": "mkdir", "path": str(p), "note": "already exists"}
    return {"kind": "mkdir", "path": str(p), "note": "will create"}


# -------------------------
# mutating tools (Step E: backup)
# -------------------------
def mkdir(path: str, parents: bool = True) -> Dict[str, Any]:
    p = _abs_path(path)
    if p.exists():
        return {"ok": True, "path": str(p), "note": "already exists"}
    p.mkdir(parents=bool(parents), exist_ok=True)
    return {"ok": True, "path": str(p)}


def _apply_then_validate_py(p: Path, backups: List[BackupEntry]) -> Optional[Dict[str, Any]]:
    """
    .py 파일이면 적용 후 py_compile 검증. 실패 시 백업 복원(또는 신규 파일 삭제) 후 에러 반환.
    반환값이 None이면 검증 통과.
    """
    if p.suffix.lower() != ".py":
        return None
    ok, err_msg = _validate_python_syntax(p)
    if ok:
        return None
    if backups:
        shutil.copy2(backups[0].backup, p)
    else:
        p.unlink(missing_ok=True)
    return {"error": "py_compile_failed", "detail": err_msg, "rolled_back": bool(backups), "path": str(p)}


def write_file(path: str, content: str, overwrite: bool = True) -> Dict[str, Any]:
    p = _abs_path(path)

    backups: list[BackupEntry] = []
    be = make_backup_for_file(p)  # 존재하면 백업
    if be:
        backups.append(be)

    if p.exists() and (not overwrite):
        return {"error": "file exists", "path": str(p)}

    _write_text_safe(p, content)

    err = _apply_then_validate_py(p, backups)
    if err:
        return err

    record_last(backups)
    return {"ok": True, "path": str(p), "backup_count": len(backups)}


def append_file(path: str, content: str) -> Dict[str, Any]:
    p = _abs_path(path)

    backups: list[BackupEntry] = []
    be = make_backup_for_file(p)
    if be:
        backups.append(be)

    before = _read_text_safe(p)
    after = before + content
    _write_text_safe(p, after)

    err = _apply_then_validate_py(p, backups)
    if err:
        return err

    record_last(backups)
    return {"ok": True, "path": str(p), "backup_count": len(backups)}


def patch_file(
    path: str,
    op: str,
    content: str,
    anchor: Optional[str] = None,
    start_marker: Optional[str] = None,
    end_marker: Optional[str] = None,
    occurrence: int = 1,
) -> Dict[str, Any]:
    prev = preview_patch_file(
        path=path,
        op=op,
        content=content,
        anchor=anchor,
        start_marker=start_marker,
        end_marker=end_marker,
        occurrence=occurrence,
    )
    if prev.get("error"):
        return prev

    p = Path(prev["path"])
    before = prev["before"]
    after = prev["after"]

    backups: list[BackupEntry] = []
    be = make_backup_for_file(p)
    if be:
        backups.append(be)

    _write_text_safe(p, after)

    err = _apply_then_validate_py(p, backups)
    if err:
        return err

    record_last(backups)
    return {"ok": True, "path": str(p), "backup_count": len(backups)}


def rename_path(src: str, dst: Optional[str] = None, new_name: Optional[str] = None) -> Dict[str, Any]:
    prev = preview_rename_path(src=src, dst=dst, new_name=new_name)
    if prev.get("error"):
        return prev

    s = Path(prev["src"])
    d = Path(prev["dst"])

    backups: list[BackupEntry] = []
    # ✅ rename은 “원본 파일”을 백업(복구는 원래 경로로 되살리는 방식)
    be = make_backup_for_file(s)
    if be:
        backups.append(be)

    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))

    record_last(backups)
    return {"ok": True, "src": str(s), "dst": str(d), "backup_count": len(backups)}