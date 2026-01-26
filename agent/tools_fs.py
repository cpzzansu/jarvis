from __future__ import annotations
from pathlib import Path
import re

from .config import MAX_WRITE_BYTES, MAX_PATCH_BYTES, MAX_APPEND_BYTES
from .paths import ensure_under_safe_roots, ensure_text_safe

def list_dir(path: str):
    p = ensure_under_safe_roots(path)
    if p.is_file():
        return {"error": "path is a file", "path": str(p)}
    if not p.exists():
        return {"error": "path not found", "path": str(p)}

    items = []
    for child in sorted(p.iterdir()):
        try:
            size = child.stat().st_size
        except Exception:
            size = None
        items.append({
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
            "size": size
        })
    return {"path": str(p), "items": items[:200]}

def read_tail(path: str, lines: int = 200):
    p = ensure_under_safe_roots(path)
    ensure_text_safe(p)
    if not p.exists() or not p.is_file():
        return {"error": "file not found", "path": str(p)}

    lines = max(1, min(int(lines), 500))
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            data = f.readlines()
        tail = data[-lines:]
        return {"path": str(p), "lines": lines, "content": "".join(tail)}
    except Exception as e:
        return {"error": str(e), "path": str(p)}

def mkdir(path: str, parents: bool = True):
    p = ensure_under_safe_roots(path)
    if p.exists() and p.is_file():
        return {"error": "path exists as file", "path": str(p)}
    p.mkdir(parents=bool(parents), exist_ok=True)
    return {"ok": True, "path": str(p)}

def write_file(path: str, content: str, overwrite: bool = True):
    p = ensure_under_safe_roots(path)
    ensure_text_safe(p)

    if p.exists() and p.is_dir():
        return {"error": "path is a directory", "path": str(p)}

    data = (content or "").encode("utf-8", errors="replace")
    if len(data) > MAX_WRITE_BYTES:
        return {"error": "content too large", "max_bytes": MAX_WRITE_BYTES, "size": len(data)}

    if p.exists() and not overwrite:
        return {"error": "file exists and overwrite=false", "path": str(p)}

    p.parent.mkdir(parents=True, exist_ok=True)
    existed_before = p.exists()
    with p.open("w", encoding="utf-8", errors="replace") as f:
        f.write(content or "")

    return {"ok": True, "path": str(p), "bytes": len(data), "overwritten": existed_before}

def append_file(path: str, content: str):
    p = ensure_under_safe_roots(path)
    ensure_text_safe(p)

    data = (content or "").encode("utf-8", errors="replace")
    if len(data) > MAX_APPEND_BYTES:
        return {"error": "content too large", "max_bytes": MAX_APPEND_BYTES, "size": len(data)}

    p.parent.mkdir(parents=True, exist_ok=True)
    existed_before = p.exists()

    with p.open("a", encoding="utf-8", errors="replace") as f:
        f.write(content or "")

    return {"ok": True, "path": str(p), "bytes": len(data), "created": (not existed_before)}

def patch_file(
    path: str,
    op: str,
    content: str,
    anchor: str | None = None,
    start_marker: str | None = None,
    end_marker: str | None = None,
    occurrence: int = 1
):
    p = ensure_under_safe_roots(path)
    ensure_text_safe(p)

    if not p.exists() or not p.is_file():
        return {"error": "file not found", "path": str(p)}

    size = p.stat().st_size
    if size > MAX_PATCH_BYTES:
        return {"error": "file too large to patch safely", "max_bytes": MAX_PATCH_BYTES, "size": size}

    text = p.read_text(encoding="utf-8", errors="replace")
    occurrence = max(1, int(occurrence))

    def find_nth(haystack: str, needle: str, n: int) -> int:
        idx = -1
        start = 0
        for _ in range(n):
            idx = haystack.find(needle, start)
            if idx == -1:
                return -1
            start = idx + len(needle)
        return idx

    if op in ("insert_after", "insert_before"):
        if not anchor:
            return {"error": "anchor required for insert ops"}
        pos = find_nth(text, anchor, occurrence)
        if pos == -1:
            return {"error": "anchor not found", "anchor": anchor, "occurrence": occurrence}

        insert_at = pos + len(anchor) if op == "insert_after" else pos
        new_text = text[:insert_at] + (content or "") + text[insert_at:]

    elif op == "replace_between":
        if not start_marker or not end_marker:
            return {"error": "start_marker and end_marker required"}
        s = find_nth(text, start_marker, occurrence)
        if s == -1:
            return {"error": "start_marker not found", "start_marker": start_marker, "occurrence": occurrence}
        e = text.find(end_marker, s + len(start_marker))
        if e == -1:
            return {"error": "end_marker not found", "end_marker": end_marker}

        inner_start = s + len(start_marker)
        inner_end = e
        new_text = text[:inner_start] + (content or "") + text[inner_end:]

    elif op == "replace_all":
        if not anchor:
            return {"error": "anchor required for replace_all (needle)"}
        new_text = text.replace(anchor, content or "")

    else:
        return {"error": "unknown op", "op": op}

    out_bytes = new_text.encode("utf-8", errors="replace")
    if len(out_bytes) > MAX_WRITE_BYTES:
        return {"error": "patched content too large", "max_bytes": MAX_WRITE_BYTES, "size": len(out_bytes)}

    p.write_text(new_text, encoding="utf-8", errors="replace")
    return {"ok": True, "path": str(p), "op": op, "bytes": len(out_bytes)}

def rename_path(src: str, dst: str | None = None, new_name: str | None = None):
    src_p = ensure_under_safe_roots(src)
    if not src_p.exists():
        return {"error": "source not found", "src": str(src_p)}

    if new_name and dst:
        return {"error": "provide only one of dst or new_name"}

    if new_name:
        dst_p = src_p.parent / new_name
    else:
        if not dst:
            return {"error": "dst or new_name required"}
        dst_p = ensure_under_safe_roots(dst)

    if dst_p.exists():
        return {"error": "destination already exists", "dst": str(dst_p)}

    src_p.rename(dst_p)
    return {"ok": True, "src": str(src_p), "dst": str(dst_p)}
