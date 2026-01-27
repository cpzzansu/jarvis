from __future__ import annotations

from typing import List, Dict, Any, Tuple, Optional

from .tools_cmd import run_whitelisted_cmd

GIT_WRITE_KEYS = {"git_add", "git_commit", "git_push"}


def plan_has_git_write(actions: List[Dict[str, Any]]) -> bool:
    for step in actions:
        if step.get("action") != "run_cmd":
            continue
        params = step.get("params", {}) or {}
        if params.get("cmd_key") in GIT_WRITE_KEYS:
            return True
    return False


def extract_commit_message(actions: List[Dict[str, Any]]) -> Optional[str]:
    for step in actions:
        if step.get("action") != "run_cmd":
            continue
        params = step.get("params", {}) or {}
        if params.get("cmd_key") != "git_commit":
            continue
        args = params.get("args", []) or []
        if len(args) >= 2 and args[0] == "-m":
            return str(args[1])
        if len(args) >= 1:
            return str(args[0])
    return None


def _print_block(title: str, text: str):
    print("\n" + "=" * 80)
    print(title)
    print("-" * 80)
    print((text or "").rstrip() if text else "(empty)")
    print("=" * 80 + "\n")


def show_git_preview() -> Dict[str, Any]:
    """
    승인 전에 유저가 볼 수 있도록 git 상태/차이 출력
    """
    res_status = run_whitelisted_cmd("git_status", [])
    res_diff = run_whitelisted_cmd("git_diff", [])
    res_diff_staged = run_whitelisted_cmd("git_diff_staged", [])

    _print_block("[git status --porcelain]", res_status.get("output") or res_status.get("error", ""))
    _print_block("[git diff (unstaged)]", res_diff.get("output") or res_diff.get("error", ""))
    _print_block("[git diff --staged]", res_diff_staged.get("output") or res_diff_staged.get("error", ""))

    return {
        "git_status": res_status,
        "git_diff": res_diff,
        "git_diff_staged": res_diff_staged,
    }


def ask_yes_no(prompt: str) -> bool:
    while True:
        ans = input(prompt).strip().lower()
        if ans in {"y", "yes"}:
            return True
        if ans in {"n", "no"}:
            return False
        print("입력은 yes/no (또는 y/n)로 해주세요.")


def apply_git_approval_layer(actions: List[Dict[str, Any]]) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Step B 핵심:
    - plan에 git_add/commit/push가 있으면, 실행 전에 diff 보여주고 승인 받기
    - 승인 NO면: git_write 액션 제거(실행 차단)
    - push는 옵션으로 2차 승인
    """
    if not plan_has_git_write(actions):
        return True, actions

    show_git_preview()

    commit_msg = extract_commit_message(actions)
    if commit_msg:
        print(f"[커밋 메시지 후보] {commit_msg}")

    ok = ask_yes_no("이 변경을 적용할까요? (yes/no): ")
    if not ok:
        filtered = []
        for step in actions:
            if step.get("action") == "run_cmd":
                params = step.get("params", {}) or {}
                if params.get("cmd_key") in GIT_WRITE_KEYS:
                    continue
            filtered.append(step)
        print("✅ 변경 적용이 거절되어 git_add/commit/push를 실행하지 않았습니다.")
        return True, filtered

    # push 2차 승인(옵션)
    has_push = any(
        step.get("action") == "run_cmd"
        and (step.get("params", {}) or {}).get("cmd_key") == "git_push"
        for step in actions
    )
    if has_push:
        ok_push = ask_yes_no("⚠️ 원격 push까지 진행할까요? (yes/no): ")
        if not ok_push:
            filtered = []
            for step in actions:
                if step.get("action") == "run_cmd":
                    params = step.get("params", {}) or {}
                    if params.get("cmd_key") == "git_push":
                        continue
                filtered.append(step)
            print("✅ push가 거절되어 git_push는 실행하지 않습니다.")
            return True, filtered

    print("✅ 승인 완료: git_add/commit(및 선택적으로 push) 실행을 진행합니다.")
    return True, actions


# (호환용 별칭: 예전 임포트가 남아있어도 ImportError 안 나게)
def print_git_preview():
    return show_git_preview()


def prompt_yes_no(prompt: str) -> bool:
    return ask_yes_no(prompt)