from __future__ import annotations
import re

from .config import FALLBACK_READ_LINES
from .llm_state import get_provider, get_model
from .paths import ensure_under_safe_roots, ensure_text_safe
from .tools_fs import read_tail, write_file

PATCH_NOT_FOUND_ERRORS = {"anchor not found", "start_marker not found", "end_marker not found"}

def _upsert_md_project_description(existing_md: str, bullets: list[str]) -> str:
    header = "## Project Description"
    if header not in existing_md:
        base = existing_md.rstrip() + "\n\n"
        return base + header + "\n" + "\n".join(f"- {b}" for b in bullets) + "\n"

    pattern = r"(## Project Description\s*\n)(.*?)(\n## |\Z)"
    m = re.search(pattern, existing_md, flags=re.DOTALL)
    if not m:
        base = existing_md.rstrip() + "\n\n"
        return base + header + "\n" + "\n".join(f"- {b}" for b in bullets) + "\n"

    prefix = existing_md[:m.start(1)]
    hdr = m.group(1)
    suffix = existing_md[m.start(3):]
    return prefix + hdr + "\n".join(f"- {b}" for b in bullets) + "\n" + suffix.lstrip("\n")

def maybe_fallback_for_patch(step_action: str, step_params: dict, result: dict, user_request: str):
    if step_action != "patch_file":
        return None

    err = (result or {}).get("error")
    if err not in PATCH_NOT_FOUND_ERRORS:
        return None

    path = step_params.get("path", "")
    try:
        p = ensure_under_safe_roots(path)
        ensure_text_safe(p)
    except Exception as e:
        return {"fallback_error": str(e)}

    tail = read_tail(str(p), FALLBACK_READ_LINES)
    if tail.get("error"):
        return {"fallback_error": "read_tail_failed", "detail": tail}

    content_now = tail.get("content", "")
    is_md = p.suffix.lower() == ".md"
    if not is_md:
        return {
            "fallback": "read_tail_only",
            "reason": "패치 앵커/마커가 없어서 파일 내용을 확인했습니다(코드 파일 자동 덮어쓰기 금지).",
            "read_tail": tail
        }

    wants_desc = ("설명" in user_request) and ("프로젝트" in user_request)
    wants_lines = ("줄" in user_request) or ("라인" in user_request)
    if not (wants_desc or wants_lines):
        return {"fallback": "read_tail_only", "reason": "요청이 설명 작성이 아니어서 자동 덮어쓰기를 생략합니다.", "read_tail": tail}

    bullets = [
        "개발 목표: 기본 구조와 에이전트 워크플로우를 검증하는 테스트 프로젝트입니다.",
        "주요 기능: 파일 생성/수정 및 Git 상태 확인을 자동화합니다.",
        f"사용 기술: Python 실행기 + LLM(provider={get_provider()}, model={get_model()}).",
        "사용 방법: set_project로 작업 폴더 고정 후 변경→diff 확인→commit/push 순서로 진행합니다.",
        "향후 계획: unified diff 기반 패치와 테스트/빌드 루프를 추가합니다.",
    ]

    new_md = _upsert_md_project_description(content_now, bullets)
    w = write_file(str(p), new_md, overwrite=True)
    return {"fallback": "md_upsert_project_description", "reason": "패치 앵커가 없어 README를 안전하게 갱신했습니다.", "write_result": w}
