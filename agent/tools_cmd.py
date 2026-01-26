from __future__ import annotations
import subprocess
from pathlib import Path

from .config import ALLOWED_CMDS, GIT_KEYS
from .paths import ensure_under_safe_roots
from .state import get_current_workdir

def resolve_git_cwd(args: list[str]) -> tuple[Path | None, list[str] | None, str | None]:
    """
    git_* cwd 결정:
    - args[0]가 디렉토리면 cwd로 사용하고 args에서 제거
    - 아니면 CURRENT_WORKDIR 사용
    - 둘 다 없으면 에러
    """
    if args and isinstance(args[0], str):
        try:
            cand = ensure_under_safe_roots(args[0])
            if cand.exists() and cand.is_dir():
                return cand, args[1:], None
        except Exception:
            pass

    cwd = get_current_workdir()
    if cwd is None:
        return None, None, "no current project set; run set_project first (or pass workdir as first arg)"
    return cwd, args, None

def run_whitelisted_cmd(cmd_key: str, args: list[str] | None):
    if cmd_key not in ALLOWED_CMDS:
        return {"error": "cmd_key not allowed", "cmd_key": cmd_key}

    base = ALLOWED_CMDS[cmd_key][:]
    args = args or []
    if not all(isinstance(a, str) for a in args):
        return {"error": "args must be list of strings"}

    cwd = None
    cmd = None

    if cmd_key == "docker_logs_tail":
        if len(args) != 2:
            return {"error": "docker_logs_tail needs [lines, container]"}
        if not args[0].isdigit():
            return {"error": "lines must be numeric string"}
        cmd = base + [args[0], args[1]]

    elif cmd_key == "systemctl_status":
        if len(args) != 1:
            return {"error": "systemctl_status needs [service]"}
        cmd = base + [args[0]]

    elif cmd_key == "journalctl_tail":
        if len(args) != 2:
            return {"error": "journalctl_tail needs [lines, service]"}
        if not args[0].isdigit():
            return {"error": "lines must be numeric string"}
        cmd = base + [args[0], "-u", args[1], "--no-pager"]

    elif cmd_key in GIT_KEYS:
        git_cwd, rest_args, err = resolve_git_cwd(args)
        if err:
            return {"error": err, "cmd_key": cmd_key}
        cwd = git_cwd

        if cmd_key in {"git_status", "git_diff", "git_diff_staged"}:
            cmd = base

        elif cmd_key == "git_add":
            path_arg = rest_args[0] if rest_args and len(rest_args) >= 1 else "."
            if path_arg != ".":
                try:
                    ensure_under_safe_roots(str(cwd / path_arg))
                except Exception as e:
                    return {"error": f"git_add path validation failed: {e}"}
            cmd = base + [path_arg]

        elif cmd_key == "git_commit":
            if not rest_args:
                return {"error": "git_commit needs [message] (or [-m, message])"}
            if rest_args[0] == "-m":
                if len(rest_args) != 2:
                    return {"error": "git_commit needs [-m, message]"}
                message = rest_args[1].strip()
            else:
                message = rest_args[0].strip()
            if not message:
                return {"error": "git_commit message cannot be empty"}
            cmd = base + [message]

        elif cmd_key == "git_push":
            remote = "origin"
            branch = "main"
            if rest_args and len(rest_args) == 2:
                remote, branch = rest_args[0], rest_args[1]
            elif rest_args and len(rest_args) == 1:
                remote = rest_args[0]
            elif rest_args and len(rest_args) > 2:
                return {"error": "git_push args must be [] or [remote] or [remote, branch] (or pass workdir first)"}
            cmd = base + [remote, branch]

    else:
        cmd = base

    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, cwd=str(cwd) if cwd else None)
        return {"cmd": cmd, "cwd": str(cwd) if cwd else None, "output": out[:8000]}
    except subprocess.CalledProcessError as e:
        return {"cmd": cmd, "cwd": str(cwd) if cwd else None, "error": e.output[:8000]}
