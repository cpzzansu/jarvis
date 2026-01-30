# Backend (FastAPI SSE bridge)

`local_agent.py`를 subprocess로 실행하고 stdout을 SSE로 스트리밍합니다.

## Endpoints
- `GET /api/agent/stream?prompt=...` : SSE 스트림

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8787
```

## Notes
- 현재는 `local_agent.py`의 인터랙티브 출력(예: `You>` 프롬프트)도 그대로 스트리밍됩니다.
- 필요하면 `chunk` 필터링/정규화(프롬프트 라인 제거 등)를 추가하세요.
