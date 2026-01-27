from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from .config import ALLOWED_CMDS
from .paths import ensure_under_safe_roots
from .state import get_current_workdir

# git 관련 cmd_key 모음 (여기만 git 전용 cwd 해석)
GIT_KEYS = {
    "git_status",
    "git_diff",
    "git_diff_staged",
    "git_add",
    "git_commit",
    "git_push",
}

# 시스템/도커 계열은 cwd 영향 필요 없음(그대로 None)
NO_CWD_KEYS = {
    "docker_ps",
    "docker_logs_tail",
    "systemctl_status",
    "journalctl_tail",
}


def _resolve_git_cwd(args: List[str]) -> Tuple[Optional[Path], List[str], Optional[str]]:
    """
    git_* 실행 시 cwd 결정:
    1) args[0]이 디렉토리면 workdir로 취급하고 args에서 제거
    2) 아니면 CURRENT_WORKDIR 사용
    """
    args = args or []
    if args and isinstance(args[0], str):
        try:
            cand = ensure_under_safe_roots(args[0])
            if cand.exists() and cand.is_dir():
                return cand, args[1:], None
        except Exception:
            pass

    cwd = get_current_workdir()
    if cwd is None:
        return None, args, "현재 프로젝트가 설정되지 않았습니다. 먼저 set_project를 실행하세요."

    return cwd, args, None


def resolve_git_cwd(args: List[str]) -> Tuple[Optional[Path], List[str], Optional[str]]:
    """
    local_agent.py에서 승인 레이어 프리뷰용으로도 쓰려고 공개 함수로 둠.
    """
    return _resolve_git_cwd(args)


def run_whitelisted_cmd(cmd_key: str, args: List[str] | None) -> Dict[str, Any]:
    """
    ✅ 핵심 개선:
    - git_* 뿐 아니라 일반 명령(ls/pwd 등)도 기본 cwd를 CURRENT_WORKDIR로 실행
    - 단, docker/systemctl/journalctl 같은 건 cwd 영향 없으니 None 유지
    """
    if cmd_key not in ALLOWED_CMDS:
        return {"error": "cmd_key not allowed", "cmd_key": cmd_key}

    base = ALLOWED_CMDS[cmd_key][:]
    args = args or []

    if not all(isinstance(a, str) for a in args):
        return {"error": "args must be list of strings"}

    cmd: List[str] = []
    cwd: Optional[Path] = None

    # -------------------------
    # docker/system 계열
    # -------------------------
    if cmd_key == "docker_logs_tail":
        # docker logs --tail <N> <container>
        if len(args) != 2:
            return {"error": "docker_logs_tail needs [lines, container]"}
        if not args[0].isdigit():
            return {"error": "lines must be numeric string"}
        cmd = base + [args[0], args[1]]
        cwd = None

    elif cmd_key == "systemctl_status":
        if len(args) != 1:
            return {"error": "systemctl_status needs [service]"}
        cmd = base + [args[0]]
        cwd = None

    elif cmd_key == "journalctl_tail":
        # journalctl -n <N> -u <service> --no-pager
        if len(args) != 2:
            return {"error": "journalctl_tail needs [lines, service]"}
        if not args[0].isdigit():
            return {"error": "lines must be numeric string"}
        cmd = base + [args[0], "-u", args[1], "--no-pager"]
        cwd = None

    # -------------------------
    # git 계열 (프로젝트 고정)
    # -------------------------
    elif cmd_key in GIT_KEYS:
        git_cwd, rest_args, err = _resolve_git_cwd(args)
        if err:
            return {"error": err, "cmd_key": cmd_key}

        cwd = git_cwd

        if cmd_key in {"git_status", "git_diff", "git_diff_staged"}:
            cmd = base

        elif cmd_key == "git_add":
            # rest_args: [path] or default "."
            path_arg = rest_args[0] if len(rest_args) >= 1 else "."
            if path_arg != ".":
                try:
                    ensure_under_safe_roots(str(cwd / path_arg))
                except Exception as e:
                    return {"error": f"git_add path validation failed: {e}"}
            cmd = base + [path_arg]

        elif cmd_key == "git_commit":
            # rest_args: [message] 또는 [-m, message]
            if len(rest_args) == 0:
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
            # rest_args: [] or [remote] or [remote, branch]
            remote = "origin"
            branch = "main"
            if len(rest_args) == 2:
                remote, branch = rest_args[0], rest_args[1]
            elif len(rest_args) == 1:
                remote = rest_args[0]
            elif len(rest_args) == 0:
                pass
            else:
                return {"error": "git_push args must be [] or [remote] or [remote, branch] (or pass workdir first)"}

            cmd = base + [remote, branch]

    # -------------------------
    # 일반 명령 (pwd/ls/whoami/date 등)
    # -------------------------
    else:
        cmd = base

        # ✅ 여기 핵심: 일반 명령도 기본 cwd를 CURRENT_WORKDIR로!
        # 단, NO_CWD_KEYS는 제외(보통 여기로 안 오지만 방어)
        if cmd_key in NO_CWD_KEYS:
            cwd = None
        else:
            cwd = get_current_workdir()

    # -------------------------
    # 실행
    # -------------------------
    effective_cwd = cwd  # 이미 위에서 결정됨

    try:
        out = subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(effective_cwd) if effective_cwd else None
        )
        return {
            "cmd": cmd,
            "cwd": str(effective_cwd) if effective_cwd else None,
            "output": out[:8000]
        }
    except subprocess.CalledProcessError as e:
        return {
            "cmd": cmd,
            "cwd": str(effective_cwd) if effective_cwd else None,
            "error": (e.output or "")[:8000]
        }