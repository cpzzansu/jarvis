import json
import requests

from agent.config import OLLAMA_URL, MODEL, SAFE_ROOTS, GIT_WRITE_KEYS
from agent.prompt import build_system_prompt
from agent.plan import parse_json_object, normalize_to_plan, optimize_plan
from agent.state import state_line, set_current_workdir, get_current_workdir
from agent.paths import ensure_under_safe_roots
from agent.project_resolver import resolve_project_dir

from agent.tools_fs import (
    list_dir, read_tail, mkdir, write_file, append_file, patch_file, rename_path
)
from agent.tools_cmd import run_whitelisted_cmd, resolve_git_cwd
from agent.approval import print_git_preview, prompt_yes_no
from agent.fallback import maybe_fallback_for_patch


# =========================
# LLM
# =========================
def ollama_chat(messages):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()["message"]["content"]


# =========================
# set_project tool (✅ fuzzy resolver 적용)
# =========================
def tool_set_project(workdir: str):
    p, info = resolve_project_dir(workdir)
    if p is None:
        return {"error": "workdir not found or not a directory", **info}

    set_current_workdir(p)

    git_dir = p / ".git"
    if not git_dir.exists():
        return {"warning": "workdir has no .git directory (still set)", "current_workdir": str(p), **info}

    return {"ok": True, "current_workdir": str(p), **info}


# =========================
# executor
# =========================
def execute_one_action(action: str, params: dict):
    if action == "set_project":
        return tool_set_project(params.get("workdir", ""))

    if action == "list_dir":
        return list_dir(params.get("path", "."))

    if action == "read_tail":
        return read_tail(params.get("path", ""), params.get("lines", 200))

    if action == "mkdir":
        return mkdir(params.get("path", ""), params.get("parents", True))

    if action == "write_file":
        return write_file(params.get("path", ""), params.get("content", ""), params.get("overwrite", True))

    if action == "append_file":
        return append_file(params.get("path", ""), params.get("content", ""))

    if action == "patch_file":
        return patch_file(
            path=params.get("path", ""),
            op=params.get("op", ""),
            content=params.get("content", ""),
            anchor=params.get("anchor"),
            start_marker=params.get("start_marker"),
            end_marker=params.get("end_marker"),
            occurrence=params.get("occurrence", 1),
        )

    if action == "rename_path":
        return rename_path(
            src=params.get("src", ""),
            dst=params.get("dst"),
            new_name=params.get("new_name"),
        )

    if action == "run_cmd":
        return run_whitelisted_cmd(params.get("cmd_key", ""), params.get("args", []))

    return {"error": f"unknown action: {action}"}


# =========================
# Main loop
# =========================
def main():
    print("SAFE_ROOTS:")
    for r in SAFE_ROOTS:
        print(" -", r)

    print("\nExamples:")
    print(" - 'suppoter_hub 프로젝트로 설정해줘'")
    print(" - 'TASKS.md 맨 아래에 진행상태 5줄 추가해줘'")
    print(" - 'test_projec 폴더 이름 test_project로 바꿔줘'")
    print(" - 'git status 보여줘'")
    print(" - '변경사항 stage 하고 커밋해줘: 메시지=...'\n")

    SYSTEM_PROMPT = build_system_prompt()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        user = input("You> ").strip()
        if not user:
            continue

        # ✅ STATE 주입(매 턴 최신 cwd를 LLM이 보게 함)
        messages.append({"role": "system", "content": state_line()})

        messages.append({"role": "user", "content": user})
        raw = ollama_chat(messages)

        try:
            cmd = parse_json_object(raw)
        except Exception:
            print("Agent> (LLM JSON parse failed)\n", raw, "\n")
            continue

        cmd = normalize_to_plan(cmd)
        cmd = optimize_plan(cmd)

        if cmd.get("action") == "final":
            print(f"Agent> {cmd.get('final_answer','')}\n")
            continue

        if cmd.get("action") != "plan":
            print("Agent> (invalid schema: expected action=plan or final)\n", json.dumps(cmd, ensure_ascii=False, indent=2), "\n")
            continue

        actions = cmd.get("actions", [])
        reason = cmd.get("reason", "")
        if not isinstance(actions, list) or len(actions) == 0:
            print("Agent> (plan has no actions)\n", json.dumps(cmd, ensure_ascii=False, indent=2), "\n")
            continue

        print(f"\n[LLM plan] reason={reason} steps={len(actions)}")

        results = []
        aborted = False

        for i, step in enumerate(actions, start=1):
            step_action = step.get("action")
            step_params = step.get("params", {}) or {}

            print(f"\n[Step {i}/{len(actions)}] action={step_action} params={step_params}")

            # ✅ Step B: git write(add/commit/push)는 실행 전 승인 받기
            if step_action == "run_cmd":
                cmd_key = (step_params or {}).get("cmd_key", "")
                if cmd_key in GIT_WRITE_KEYS:
                    args = (step_params or {}).get("args", []) or []
                    git_cwd, _, err = resolve_git_cwd(args)
                    if err is None and git_cwd is not None:
                        print("\n=== APPROVAL REQUIRED (git write) ===")
                        preview = print_git_preview(git_cwd)

                        has_any_change = (
                            (preview.get("status") or "").strip() != "" or
                            (preview.get("diff") or "").strip() != "" or
                            (preview.get("diff_staged") or "").strip() != ""
                        )
                        if has_any_change:
                            ok = prompt_yes_no("이 변경을 계속 진행할까요? (y/n): ")
                            if not ok:
                                result = {
                                    "skipped": True,
                                    "reason": "user denied approval for git write",
                                    "cmd_key": cmd_key,
                                    "cwd": str(git_cwd),
                                }
                                print("[Tool result]\n", json.dumps(result, ensure_ascii=False, indent=2))
                                results.append({"step": i, "action": step_action, "params": step_params, "result": result})
                                continue
                        else:
                            print("변경사항이 없어서 승인 없이 진행합니다.")

            try:
                result = execute_one_action(step_action, step_params)
            except PermissionError as e:
                result = {"error": "permission_denied", "detail": str(e)}
            except Exception as e:
                result = {"error": "tool_exception", "detail": str(e)}

            print("[Tool result]\n", json.dumps(result, ensure_ascii=False, indent=2))

            # ✅ 핵심: set_project 실패하면 남은 step 즉시 중단 (연쇄 실패 방지)
            if step_action == "set_project" and isinstance(result, dict) and result.get("error"):
                results.append({"step": i, "action": step_action, "params": step_params, "result": result})
                print("\n[Abort] set_project failed. Stop remaining steps in this plan.\n")
                aborted = True
                break

            fb = maybe_fallback_for_patch(step_action, step_params, result, user_request=user)
            if fb is not None:
                print("\n[Fallback triggered]\n", json.dumps(fb, ensure_ascii=False, indent=2))
                results.append({"step": i, "action": step_action, "params": step_params, "result": result, "fallback": fb})
            else:
                results.append({"step": i, "action": step_action, "params": step_params, "result": result})

        # aborted여도 결과는 LLM에게 전달해서 요약/다음 액션 정리 유도
        messages.append({"role": "user", "content": f"TOOL_RESULTS (json): {json.dumps(results, ensure_ascii=False)}"})
        raw2 = ollama_chat(messages)

        try:
            cmd2 = parse_json_object(raw2)
            cmd2 = normalize_to_plan(cmd2)

            if cmd2.get("action") == "final":
                print(f"\nAgent> {cmd2.get('final_answer','')}\n")
            elif cmd2.get("action") == "plan":
                print("\nAgent> (non-final plan)\n", json.dumps(cmd2, ensure_ascii=False, indent=2), "\n")
            else:
                print("\nAgent> (LLM output)\n", raw2, "\n")
        except Exception:
            print("\nAgent> (LLM output)\n", raw2, "\n")


if __name__ == "__main__":
    main()
