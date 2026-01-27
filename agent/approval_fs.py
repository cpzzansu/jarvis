# agent/approval_fs.py
from __future__ import annotations

import difflib
from typing import Any, Dict, Tuple

from .tools_fs import (
    preview_write_file,
    preview_append_file,
    preview_patch_file,
    preview_rename_path,
    preview_mkdir,
)
from .approval import prompt_yes_no


# local_agent.py에서 체크할 "파일을 바꾸는 액션" 목록
FS_WRITE_ACTIONS = {"write_file", "append_file", "patch_file", "rename_path", "mkdir"}


def _unified_diff(before: str, after: str, path: str) -> str:
    before_lines = (before or "").splitlines(keepends=True)
    after_lines = (after or "").splitlines(keepends=True)
    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"{path} (before)",
        tofile=f"{path} (after)",
        lineterm="",
    )
    return "".join(diff)


def _print_preview(preview: Dict[str, Any]) -> None:
    kind = preview.get("kind")
    if kind == "mkdir":
        print("\n=== DRY-RUN (mkdir) ===")
        print("path:", preview.get("path"))
        print("note:", preview.get("note"))
        return

    if kind == "rename":
        print("\n=== DRY-RUN (rename) ===")
        print("src:", preview.get("src"))
        print("dst:", preview.get("dst"))
        return

    path = preview.get("path", "")
    before = preview.get("before", "")
    after = preview.get("after", "")

    print(f"\n=== DRY-RUN ({kind}) ===")
    print("path:", path)

    # 너무 긴 파일은 터미널 폭발하니까 diff만 보여주고,
    # before/after 원문은 필요하면 다음 단계에서 옵션으로 확장 가능
    diff = _unified_diff(before, after, path)
    if diff.strip():
        print("\n--- unified diff ---")
        print(diff)
    else:
        print("\n(no diff) - 내용 변화가 감지되지 않았습니다.")


def approve_fs_action(action: str, params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    실행 직전에 preview를 만들고, diff를 출력하고, 사용자 승인 받기.
    return:
      (True, preview)  -> 승인됨
      (False, {error/detail}) -> 거부 또는 preview 실패
    """
    try:
        if action == "write_file":
            preview = preview_write_file(
                path=params.get("path", ""),
                content=params.get("content", ""),
                overwrite=params.get("overwrite", True),
            )
        elif action == "append_file":
            preview = preview_append_file(
                path=params.get("path", ""),
                content=params.get("content", ""),
            )
        elif action == "patch_file":
            preview = preview_patch_file(
                path=params.get("path", ""),
                op=params.get("op", ""),
                content=params.get("content", ""),
                anchor=params.get("anchor"),
                start_marker=params.get("start_marker"),
                end_marker=params.get("end_marker"),
                occurrence=params.get("occurrence", 1),
            )
        elif action == "rename_path":
            preview = preview_rename_path(
                src=params.get("src", ""),
                dst=params.get("dst"),
                new_name=params.get("new_name"),
            )
        elif action == "mkdir":
            preview = preview_mkdir(
                path=params.get("path", ""),
                parents=params.get("parents", True),
            )
        else:
            return False, {"error": "not_fs_write_action", "action": action}

        if preview.get("error"):
            return False, preview

        _print_preview(preview)

        ok = prompt_yes_no("Apply? (y/n): ")
        if not ok:
            return False, {"error": "user_denied", "action": action, "preview": preview}

        return True, preview

    except Exception as e:
        return False, {"error": "fs_approval_exception", "detail": str(e), "action": action}