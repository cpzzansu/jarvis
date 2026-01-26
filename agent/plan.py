from __future__ import annotations
import json
from typing import Any

from .state import get_current_workdir
from .paths import ensure_under_safe_roots

def parse_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found")
    return json.loads(text[start:end + 1])

def normalize_to_plan(cmd: dict) -> dict:
    if cmd.get("action") == "final":
        return cmd
    if cmd.get("action") == "plan":
        return cmd
    if isinstance(cmd.get("action"), str) and isinstance(cmd.get("params", {}), dict):
        return {
            "action": "plan",
            "reason": cmd.get("reason", "단일 액션 실행(호환)"),
            "actions": [{"action": cmd.get("action"), "params": cmd.get("params", {})}],
        }
    return cmd

def optimize_plan(plan: dict) -> dict:
    """
    - CURRENT_WORKDIR가 이미 있는데 같은 set_project를 또 하면 제거
    - 연속 set_project 중복 제거
    """
    if plan.get("action") != "plan":
        return plan

    actions = plan.get("actions", [])
    if not isinstance(actions, list):
        return plan

    cwd = get_current_workdir()
    new_actions = []

    for step in actions:
        if not isinstance(step, dict):
            continue

        if step.get("action") == "set_project":
            workdir = (step.get("params", {}) or {}).get("workdir")

            # 1) 이미 같은 cwd면 제거
            if cwd is not None and workdir:
                try:
                    wp = ensure_under_safe_roots(workdir)
                    if wp == cwd:
                        continue
                except Exception:
                    pass

            # 2) 직전 step도 set_project이고 workdir이 같으면 제거
            if new_actions and new_actions[-1].get("action") == "set_project":
                prev = (new_actions[-1].get("params", {}) or {}).get("workdir")
                if prev == workdir:
                    continue

        new_actions.append(step)

    plan["actions"] = new_actions
    return plan
