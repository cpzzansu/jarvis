from pathlib import Path
import os

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b-instruct"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "120"))

def require_openai_key() -> None:
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY가 비어있습니다. jarvis/.env 또는 환경변수에 OPENAI_API_KEY를 설정하세요."
        )

SAFE_ROOTS = [
    Path("/Users/daallcntdevelop/workSpace"),
]
SAFE_ROOTS = [p.expanduser().resolve() for p in SAFE_ROOTS]

# size limits
MAX_WRITE_BYTES = 300_000
MAX_PATCH_BYTES = 300_000
MAX_APPEND_BYTES = 300_000
FALLBACK_READ_LINES = 500

ALLOWED_TEXT_EXTS = {
    ".txt", ".md", ".json", ".yml", ".yaml", ".xml", ".properties", ".env",
    ".java", ".kt", ".gradle", ".groovy",
    ".js", ".ts", ".tsx", ".jsx", ".css", ".scss", ".html",
    ".sql", ".sh", ".py"
}

ALLOWED_CMDS = {
    "pwd": ["pwd"],
    "ls": ["ls", "-la"],
    "whoami": ["whoami"],
    "date": ["date"],
    "docker_ps": ["docker", "ps"],
    "docker_logs_tail": ["docker", "logs", "--tail"],  # + [lines, container]
    "systemctl_status": ["systemctl", "status"],       # + [service]
    "journalctl_tail": ["journalctl", "-n"],           # + [lines, service]

    # Git
    "git_status": ["git", "status", "--porcelain"],
    "git_diff": ["git", "diff"],
    "git_diff_staged": ["git", "diff", "--staged"],
    "git_add": ["git", "add"],                         # + [path]
    "git_commit": ["git", "commit", "-m"],             # + [message]
    "git_push": ["git", "push"],                       # + [remote, branch]
}

GIT_KEYS = {"git_status", "git_diff", "git_diff_staged", "git_add", "git_commit", "git_push"}
GIT_WRITE_KEYS = {"git_add", "git_commit", "git_push"}  # Step B approval required


