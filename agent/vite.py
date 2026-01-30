# agent/vite.py
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal, Dict, Any

from .tools_cmd import run_whitelisted_cmd


Template = Literal["react", "react-ts"]


def _validate_template(template: str) -> Template:
    t = (template or "").strip()
    if t not in ("react", "react-ts"):
        raise ValueError("template must be one of: react | react-ts")
    return t  # type: ignore[return-value]


def _validate_path_under_project(project_root: Path, rel_path: str) -> Path:
    if not rel_path or not str(rel_path).strip():
        raise ValueError("path is required")

    rel = Path(rel_path)

    # disallow traversal
    if ".." in rel.parts:
        raise ValueError("path must not contain '..'")

    root = project_root.resolve()
    target = (root / rel).resolve()

    # must be under project root (and not equal to root)
    if target == root or root not in target.parents:
        raise ValueError("path must be under the project root")

    return target


def _print_cmd_preview(project_root: Path, rel_path: str, template: str, target: Path) -> list[list[str]]:
    cmd1 = ["npm", "create", "vite@latest", rel_path, "--", "--template", template]
    cmd2 = ["npm", "install"]

    print("\n[Command preview]")
    print(" ".join(cmd1))
    print(f"(cwd: {project_root})")
    print(" ".join(cmd2))
    print(f"(cwd: {target})\n")

    print("NOTE: node_modules는 자동으로 .gitignore에 추가하지 않습니다. 필요하면 직접 추가하세요.")

    return [cmd1, cmd2]


def create_vite_app(
    *,
    project_root: Path,
    path: str,
    template: str,
    ask_yes_no,
) -> Dict[str, Any]:
    """Create Vite app (npm only; NO npx)

    - npm create vite@latest <path> -- --template <react|react-ts>
    - npm install (cwd=<path>)
    - path validation: under project root + reject '..'
    - approval: command preview + Apply? (y/n)
    - git visibility: run_whitelisted_cmd('git_status',[]) before/after
    """

    t = _validate_template(template)
    target = _validate_path_under_project(project_root, path)

    # 0) 안전 가드: 타겟 디렉토리가 이미 있고, 비어있지 않으면 생성 시도하지 않음
    if target.exists():
        try:
            has_any = any(target.iterdir())
        except Exception:
            has_any = True
        if has_any:
            return {
                "ok": False,
                "error": "target_not_empty",
                "detail": "target directory already exists and is not empty; remove or empty it first.",
                "project_root": str(project_root),
                "path": str(Path(path)),
            }

    # git status before
    try:
        print("\n[git status before]")
        st_before = run_whitelisted_cmd("git_status", [])
        print((st_before.get("output") or st_before.get("error") or "").rstrip())
    except Exception:
        st_before = {"error": "git_status preview failed"}

    preview = _print_cmd_preview(project_root, str(Path(path)), t, target)

    if not ask_yes_no("Apply? (y/n): "):
        return {
            "ok": False,
            "error": "user declined",
            "path": str(Path(path)),
            "template": t,
            "preview": preview,
        }

    # execute: npm create (cwd=project_root) — 진행상황을 터미널에 바로 출력
    try:
        print("\n[진행] npm create vite@latest ... (진행상황이 아래에 출력됩니다)\n")
        p1 = subprocess.run(
            ["npm", "create", "vite@latest", str(Path(path)), "--", "--template", t],
            cwd=str(project_root),
            text=True,
        )
        if p1.returncode != 0:
            return {
                "ok": False,
                "error": "npm create vite failed",
                "returncode": p1.returncode,
                "path": str(Path(path)),
                "template": t,
                "preview": preview,
            }

        # 2) 스캐폴딩 최소 검증: package.json 없으면 install 단계로 가지 않음
        pkg = target / "package.json"
        if not pkg.exists():
            return {
                "ok": False,
                "error": "vite_scaffold_failed",
                "reason": "package.json not found after npm create; target may have been pre-existing or create step failed silently.",
                "path": str(Path(path)),
                "template": t,
                "returncode": p1.returncode,
                "preview": preview,
            }

        # 3) execute: npm install (cwd=target) — 진행상황을 터미널에 바로 출력
        print("\n[진행] npm install ... (진행상황이 아래에 출력됩니다)\n")
        p2 = subprocess.run(
            ["npm", "install"],
            cwd=str(target),
            text=True,
        )
        if p2.returncode != 0:
            return {
                "ok": False,
                "error": "npm install failed",
                "returncode": p2.returncode,
                "path": str(Path(path)),
                "template": t,
                "preview": preview,
            }

    except FileNotFoundError as e:
        return {"ok": False, "error": f"command not found: {e}", "path": str(Path(path)), "template": t}
    except Exception as e:
        return {"ok": False, "error": "exception", "detail": str(e), "path": str(Path(path)), "template": t}

    # git status after
    try:
        print("\n[git status after]")
        st_after = run_whitelisted_cmd("git_status", [])
        print((st_after.get("output") or st_after.get("error") or "").rstrip())
    except Exception:
        st_after = {"error": "git_status preview failed"}

    return {
        "ok": True,
        "path": str(Path(path)),
        "template": t,
        "preview": preview,
        "git_status_before": st_before,
        "git_status_after": st_after,
    }
