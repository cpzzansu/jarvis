from __future__ import annotations

import re
from typing import List, Dict, Any, Tuple


# 한자(중국어/일본어 한자 포함) 대충 감지용
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
# 영어 알파벳 감지(원하면 끌 수 있음)
_LATIN_RE = re.compile(r"[A-Za-z]")


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def contains_latin(text: str) -> bool:
    return bool(_LATIN_RE.search(text or ""))


def _walk_strings(obj: Any) -> List[str]:
    """
    dict/list 내부의 모든 문자열을 수집
    """
    out: List[str] = []
    if obj is None:
        return out
    if isinstance(obj, str):
        out.append(obj)
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_walk_strings(k))
            out.extend(_walk_strings(v))
        return out
    if isinstance(obj, list):
        for x in obj:
            out.extend(_walk_strings(x))
        return out
    # 기타 타입은 무시
    return out


def is_language_ok(cmd_obj: Dict[str, Any], forbid_latin: bool = False) -> Tuple[bool, Dict[str, Any]]:
    """
    JSON 오브젝트 내부(reason/final_answer 포함 전체)을 검사해서
    - 한자(CJK)가 있으면 실패
    - (옵션) 알파벳도 막고 싶으면 forbid_latin=True

    반환: (ok, detail)
    """
    strings = _walk_strings(cmd_obj)
    cjk_hits = [s for s in strings if contains_cjk(s)]
    latin_hits = [s for s in strings if forbid_latin and contains_latin(s)]

    ok = (len(cjk_hits) == 0) and (len(latin_hits) == 0)
    detail = {
        "has_cjk": len(cjk_hits) > 0,
        "has_latin": len(latin_hits) > 0,
        "cjk_samples": cjk_hits[:3],
        "latin_samples": latin_hits[:3],
    }
    return ok, detail


def build_rewrite_request(forbid_latin: bool = False) -> str:
    """
    LLM에게 다시 출력하라고 강제하는 메시지.
    """
    if forbid_latin:
        return (
            "방금 출력에 한국어가 아닌 문자가 포함됐습니다(중국어/영어). "
            "반드시 한국어만 사용해서 동일한 내용으로 다시 출력하세요. "
            "JSON 객체 1개만 출력하세요."
        )
    return (
        "방금 출력에 중국어(한자)가 포함됐습니다. "
        "반드시 한국어만 사용해서 동일한 내용으로 다시 출력하세요. "
        "JSON 객체 1개만 출력하세요."
    )