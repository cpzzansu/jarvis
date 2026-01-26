from __future__ import annotations
import subprocess
from pathlib import Path

def prompt_yes_no(msg: str) -> bool:
    while True:
        ans = input(msg).strip().lower()
        if ans in ("y", "yes", "ㅇ", "ㅇㅇ"):
            return True
        if ans in ("n", "no", "ㄴ", "ㄴㄴ"):
            return False
        print("  -> y / n 로 입력해줘")

def print_git_preview(cwd_path: Path):
    st = subprocess.check_output(["git", "status", "--porcelain"], text=True, cwd=str(cwd_path))
    print("\n[git status --porcelain]\n" + (st.strip() if st.strip() else "(no changes)"))

    df = subprocess.check_output(["git", "diff"], text=True, cwd=str(cwd_path))
    print("\n[git diff]\n" + (df.strip() if df.strip() else "(no diff)"))

    dfs = subprocess.check_output(["git", "diff", "--staged"], text=True, cwd=str(cwd_path))
    print("\n[git diff --staged]\n" + (dfs.strip() if dfs.strip() else "(no staged diff)"))

    return {"status": st[:8000], "diff": df[:8000], "diff_staged": dfs[:8000]}
