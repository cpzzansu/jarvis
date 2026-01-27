# agent/rag.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import chromadb
from chromadb.config import Settings
from tqdm import tqdm

from .config import OLLAMA_URL, MODEL  # 너 config.py에 있는 값 사용(없으면 아래 주석 참고)
import requests

# ✅ 인덱싱 대상 확장자(코드/설정/문서)
INCLUDE_EXTS = {
    ".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini", ".env",
    ".js", ".ts", ".tsx", ".jsx", ".css", ".scss", ".html",
    ".java", ".kt", ".gradle", ".groovy", ".properties",
    ".sql", ".sh", ".xml"
}

# ✅ 제외 디렉토리
EXCLUDE_DIRS = {
    ".git", ".idea", ".vscode", ".gradle", "build", "dist", "node_modules",
    ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache"
}

# ✅ 인덱스 저장 위치(프로젝트별 분리)
BASE_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INDEXES_DIR = BASE_DATA_DIR / "indexes"

# ✅ Chunking (문자 단위로 안전하게)
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200

# ✅ Ollama 임베딩 모델(없으면 pull 필요)
EMBED_MODEL = "nomic-embed-text"
OLLAMA_BASE = "http://localhost:11434"

__all__ = [
    "RagHit",
    "build_or_update_index",
    "retrieve",
    "format_hits_for_prompt",
]


@dataclass(frozen=True)
class RagHit:
    path: str
    start: int
    end: int
    text: str
    score: float


def _project_slug(project_root: Path) -> str:
    h = hashlib.sha1(str(project_root).encode("utf-8")).hexdigest()[:10]
    # ✅ embed 모델까지 포함: 모델 바뀌면 인덱스 디렉토리도 새로 생성됨
    mh = hashlib.sha1(EMBED_MODEL.encode("utf-8")).hexdigest()[:6]
    return f"{project_root.name}_{h}_{mh}"


def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in INCLUDE_EXTS:
            continue
        # 제외 디렉토리 필터
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        yield p


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _chunk_text(text: str) -> List[Tuple[int, int, str]]:
    chunks = []
    n = len(text)
    i = 0
    while i < n:
        j = min(n, i + CHUNK_SIZE)
        chunk = text[i:j]
        chunks.append((i, j, chunk))
        if j == n:
            break
        i = max(0, j - CHUNK_OVERLAP)
    return chunks


def _ollama_embed(text: str, model: str = EMBED_MODEL) -> list[float]:
    if not isinstance(text, str):
        raise TypeError(f"_ollama_embed expects str, got {type(text)}")

    r = requests.post(
        f"{OLLAMA_BASE}/api/embed",
        json={"model": model, "input": text},
        timeout=120,
    )
    if r.status_code == 404:
        r = requests.post(
            f"{OLLAMA_BASE}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=120,
        )

    r.raise_for_status()
    data = r.json()

    if "embeddings" in data:
        v = data["embeddings"][0]
    else:
        v = data["embedding"]

    if not (isinstance(v, list) and v and isinstance(v[0], (int, float))):
        raise RuntimeError(f"invalid embedding shape: {type(v)} len={len(v) if isinstance(v, list) else 'NA'}")

    return v

def _ollama_embed_batch(texts: list[str], model: str = EMBED_MODEL) -> list[list[float]]:
    """
    texts 길이 N -> embeddings 길이 N 보장
    - new: /api/embed  {"model":..., "input":[...]}  -> {"embeddings":[[...],[...]]}
    - old: /api/embeddings {"model":..., "prompt":"..."} -> {"embedding":[...]} (단건만)
    """
    texts = [t for t in (texts or []) if isinstance(t, str) and t.strip()]
    if not texts:
        return []

    # ✅ new endpoint (batch 가능)
    r = requests.post(
        f"{OLLAMA_BASE}/api/embed",
        json={"model": model, "input": texts},
        timeout=120,
    )

    # ✅ fallback (old endpoint: single only → loop)
    if r.status_code == 404:
        out: list[list[float]] = []
        for t in texts:
            rr = requests.post(
                f"{OLLAMA_BASE}/api/embeddings",
                json={"model": model, "prompt": t},
                timeout=120,
            )
            rr.raise_for_status()
            out.append(rr.json()["embedding"])
        return out

    r.raise_for_status()
    data = r.json()

    embs = data.get("embeddings")
    if not isinstance(embs, list):
        raise RuntimeError(f"unexpected embed response: {data}")

    # ✅ 길이 체크 (여기서 바로 터뜨리면 원인 찾기 쉬움)
    if len(embs) != len(texts):
        raise RuntimeError(f"embed length mismatch: texts={len(texts)} embeddings={len(embs)}")

    return embs


def _get_chroma(project_root: Path):
    INDEXES_DIR.mkdir(parents=True, exist_ok=True)
    slug = _project_slug(project_root)
    persist_dir = (INDEXES_DIR / slug)
    persist_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(persist_dir),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(name="code_chunks")
    return client, collection, persist_dir


def build_or_update_index(project_root: Path) -> Dict[str, Any]:
    """
    프로젝트 루트 기준으로 파일을 chunking해서 Chroma에 저장.
    - id = sha1(path + start + end)
    - meta에 path/start/end 저장
    """
    _, col, persist_dir = _get_chroma(project_root)

    files = list(_iter_files(project_root))
    added = 0

    for fp in tqdm(files, desc=f"Indexing {project_root.name}", unit="file"):
        rel = str(fp.relative_to(project_root))
        text = _read_text(fp)
        chunks = _chunk_text(text)

        # batch embed (너무 크면 나눠도 됨)
        batch_texts = [c[2] for c in chunks]

        embs = _ollama_embed_batch(batch_texts)  # ← _ollama_embed가 아니라 배치용으로!

        if len(embs) != len(batch_texts):
            raise RuntimeError(
                f"embed length mismatch: texts={len(batch_texts)} embs={len(embs)} file={rel}"
            )

        ids = []
        metas = []
        docs = []
        for (start, end, chunk_text), emb in zip(chunks, embs):
            _id = hashlib.sha1(f"{rel}:{start}:{end}".encode("utf-8")).hexdigest()
            ids.append(_id)
            metas.append({"path": rel, "start": start, "end": end})
            docs.append(chunk_text)

        # ✅ upsert (길이 동일 보장)
        col.upsert(ids=ids, documents=docs, embeddings=embs, metadatas=metas)
        added += len(ids)

    return {"ok": True, "project_root": str(project_root), "persist_dir": str(persist_dir), "chunks_upserted": added}


def retrieve(project_root: Path, query: str, top_k: int = 8) -> List[RagHit]:
    _, col, _ = _get_chroma(project_root)

    # ✅ 버그 수정: _ollama_embed는 str -> list[float]
    q_emb = _ollama_embed(query)

    res = col.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    hits: List[RagHit] = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, dists):
        score = float(1.0 / (1.0 + float(dist)))
        hits.append(
            RagHit(
                path=str(meta.get("path")),
                start=int(meta.get("start", 0)),
                end=int(meta.get("end", 0)),
                text=str(doc),
                score=score,
            )
        )
    return hits


def format_hits_for_prompt(hits: List[RagHit], project_root: Path) -> str:
    """
    LLM에 넣을 컨텍스트 문자열(경로/범위/본문) 생성
    """
    if not hits:
        return "NO_CONTEXT_FOUND"

    parts = []
    parts.append(f"[PROJECT_ROOT]\n{project_root}\n")
    parts.append("[RETRIEVED_CONTEXT]\n")
    for i, h in enumerate(hits, start=1):
        parts.append(f"--- hit #{i} score={h.score:.3f} file={h.path} range={h.start}:{h.end} ---\n")
        parts.append(h.text.rstrip() + "\n")
    return "".join(parts)