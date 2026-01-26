from __future__ import annotations

import difflib
from pathlib import Path
from typing import Optional, Tuple, Dict, List

from .config import SAFE_ROOTS
from .paths import ensure_under_safe_roots


def list_projects() -> List[Path]:
    """
    SAFE_ROOTS[0] 바로 아래 하위 폴더들을 "프로젝트 후보"로 취급.
    (숨김 폴더 제외)
    """
    root = SAFE_ROOTS[0]
    if not root.exists():
        return []
    return [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]


def resolve_project_dir(workdir: str) -> Tuple[Optional[Path], Dict]:
    """
    workdir 입력을 실제 프로젝트 폴더로 해석/보정한다.

    우선순위:
    1) workdir를 경로(absolute/relative)로 해석 → SAFE_ROOTS 내부면 OK
    2) 단순 이름이면 SAFE_ROOTS[0] 아래에서
       - exact match
       - fuzzy match(difflib)
    """
    info: Dict = {"input": workdir}

    # 1) 경로로 해석 시도
    try:
        p = ensure_under_safe_roots(workdir)
        if p.exists() and p.is_dir():
            info["resolved_by"] = "path"
            return p, info
    except Exception as e:
        info["path_parse_error"] = str(e)

    # 2) 이름 fuzzy match
    candidates = list_projects()
    names = [c.name for c in candidates]
    info["candidate_count"] = len(names)

    if not names:
        info["resolved_by"] = "not_found"
        return None, info

    # exact
    if workdir in names:
        idx = names.index(workdir)
        info["resolved_by"] = "exact_name"
        info["matched_name"] = workdir
        return candidates[idx], info

    # fuzzy (오타/철자 차이 보정)
    close = difflib.get_close_matches(workdir, names, n=1, cutoff=0.55)
    if close:
        chosen = close[0]
        idx = names.index(chosen)
        info["resolved_by"] = "fuzzy"
        info["matched_name"] = chosen
        return candidates[idx], info

    # 못 찾음
    info["resolved_by"] = "not_found"
    # 너무 길면 일부만
    info["candidates_preview"] = names[:50]
    return None, info
