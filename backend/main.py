import asyncio
import os
import sys
import uuid
from pathlib import Path
from time import time
from typing import AsyncGenerator, Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="Jarvis Agent Bridge")

# ---------- Auth (cookie-based session) ----------
AUTH_COOKIE_NAME = "jarvis_session"
AUTH_SESSION_TTL_SEC = 86400 * 7  # 7 days

_auth_sessions: dict[str, dict] = {}  # token -> { "email": str, "exp": float }


def _auth_credentials() -> tuple[str, str]:
    """환경변수 또는 backend/.env 의 JARVIS_AUTH_EMAIL, JARVIS_AUTH_PASSWORD 사용."""
    email = os.environ.get("JARVIS_AUTH_EMAIL", "")
    password = os.environ.get("JARVIS_AUTH_PASSWORD", "")
    if not email or not password:
        raise ValueError("JARVIS_AUTH_EMAIL, JARVIS_AUTH_PASSWORD 를 .env 또는 환경변수로 설정하세요.")
    return email, password


def _create_session(email: str) -> str:
    token = uuid.uuid4().hex
    _auth_sessions[token] = {"email": email, "exp": time() + AUTH_SESSION_TTL_SEC}
    return token


def _get_session(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    sess = _auth_sessions.get(token)
    if not sess or sess.get("exp", 0) < time():
        if token in _auth_sessions:
            del _auth_sessions[token]
        return None
    return sess


async def require_auth(jarvis_session: Optional[str] = Cookie(None)) -> dict:
    sess = _get_session(jarvis_session)
    if not sess:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return sess


class LoginBody(BaseModel):
    email: str
    password: str

# CORS: allow frontend dev server (Vite default 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://59.1.235.35"],    # allow remote access (IP)
    # NOTE: 필요에 따라 포트/프로토콜을 조정하세요.
    # - Vite dev: http://59.1.235.35:5173
    # - plain http: http://59.1.235.35
    # - https: https://59.1.235.35

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------- Auth routes ----------
@app.post("/api/auth/login")
async def auth_login(body: LoginBody, response: Response):
    email_expected, password_expected = _auth_credentials()
    if body.email.strip().lower() != email_expected.lower() or body.password != password_expected:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = _create_session(body.email.strip())
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=AUTH_SESSION_TTL_SEC,
    )
    return {"ok": True, "email": body.email}


@app.post("/api/auth/logout")
async def auth_logout(response: Response, jarvis_session: Optional[str] = Cookie(None)):
    if jarvis_session and jarvis_session in _auth_sessions:
        del _auth_sessions[jarvis_session]
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(session: dict = Depends(require_auth)):
    return {"ok": True, "email": session["email"]}
LOCAL_AGENT = PROJECT_ROOT / "local_agent.py"

# 프로젝트 루트 venv의 Python으로 서브프로세스 실행 (local_agent.py 의존성 동일 환경)
def _venv_python() -> Path:
    if os.name == "nt":
        candidate = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = PROJECT_ROOT / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else Path(sys.executable)


def _sse_data(data: str) -> bytes:
    """EventSource onmessage는 event가 없거나 event: message 일 때만 호출됨. data만 보냄."""
    return f"data: {data}\n\n".encode("utf-8")


# 세션: session_id -> 프로세스 + 락 (동일 세션 내 요청 직렬화)
class _Session:
    __slots__ = ("proc", "lock")

    def __init__(self, proc: asyncio.subprocess.Process):
        self.proc = proc
        self.lock = asyncio.Lock()


_sessions: dict[str, _Session] = {}


async def _close_session(session_id: str) -> None:
    if session_id not in _sessions:
        return
    sess = _sessions.pop(session_id)
    if sess.proc.returncode is None:
        sess.proc.terminate()
        try:
            await asyncio.wait_for(sess.proc.wait(), timeout=2)
        except Exception:
            sess.proc.kill()


async def _get_or_create_session(session_id: str) -> _Session:
    if session_id in _sessions:
        sess = _sessions[session_id]
        if sess.proc.returncode is not None:
            del _sessions[session_id]
        else:
            return sess

    py = str(_venv_python())
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(PROJECT_ROOT) + (
        os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else ""
    )
    proc = await asyncio.create_subprocess_exec(
        py,
        "-u",
        str(LOCAL_AGENT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    sess = _Session(proc)
    _sessions[session_id] = sess
    return sess


async def _stream_until_marker(
    proc: asyncio.subprocess.Process,
    request: Request,
    marker: str,
) -> AsyncGenerator[bytes, None]:
    yield _sse_data("{\"type\":\"meta\",\"ok\":true}")

    if proc.stdout is None:
        yield _sse_data("{\"type\":\"done\",\"ok\":true,\"code\":0}")
        return

    while True:
        if await request.is_disconnected():
            break
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip("\n")
        if marker in text or text.strip() == marker:
            break
        # CLI 프롬프트 "You>" 라인은 채팅 UI로 보내지 않음
        stripped = text.strip()
        if stripped in ("You>", "You> "):
            continue
        safe = text.replace("\\", "\\\\").replace('"', '\\"')
        yield _sse_data(f"{{\"type\":\"chunk\",\"text\":\"{safe}\"}}")

    yield _sse_data("{\"type\":\"done\",\"ok\":true,\"code\":0}")


@app.get("/api/agent/session/reset")
async def session_reset(
    session_id: str = Query("default", description="Session to close"),
    _: dict = Depends(require_auth),
):
    """해당 세션의 agent 프로세스를 종료합니다. 프론트에서 세션 초기화 시 호출."""
    await _close_session(session_id)
    return {"ok": True}


@app.get("/api/agent/stream")
async def agent_stream(
    request: Request,
    prompt: str = Query("", description="User prompt to send to local_agent.py"),
    workdir: Optional[str] = Query(None, description="Optional project workdir to set inside agent"),
    session_id: str = Query("default", description="Session id to reuse the same agent process"),
    reset: bool = Query(False, description="If true, close the session before this request"),
    _: dict = Depends(require_auth),
):
    if not LOCAL_AGENT.exists():
        return StreamingResponse(
            iter([_sse_data("{\"type\":\"error\",\"ok\":false,\"error\":\"local_agent.py not found\"}")]),
            media_type="text/event-stream",
        )

    if reset:
        await _close_session(session_id)

    sess = await _get_or_create_session(session_id)
    marker = f"__JARVIS_DONE__:{uuid.uuid4().hex}"

    async with sess.lock:
        assert sess.proc.stdin is not None
        if workdir:
            sess.proc.stdin.write(f"__JARVIS_WORKDIR__:{workdir}\n".encode("utf-8"))
            await sess.proc.stdin.drain()
        sess.proc.stdin.write((prompt + "\n").encode("utf-8"))
        sess.proc.stdin.write((marker + "\n").encode("utf-8"))
        await sess.proc.stdin.drain()

        return StreamingResponse(
            _stream_until_marker(sess.proc, request, marker),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
