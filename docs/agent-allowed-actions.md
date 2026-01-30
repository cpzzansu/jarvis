# Jarvis 에이전트 허용 액션 목록

에이전트가 사용할 수 있는 step action 목록입니다.  
`plan has no actions` 가 나오면 LLM이 이 중 하나 이상을 `actions[]` 에 넣어야 합니다.

## 파일/디렉터리

| action       | 설명                    | params 예시 |
|-------------|-------------------------|-------------|
| list_dir    | 디렉터리 목록           | `{"path": "."}` |
| read_tail   | 파일 끝 N줄 읽기 (파일 열기용) | `{"path": "src/App.tsx", "lines": 500}` |
| write_file  | 파일 전체 쓰기          | `{"path": "...", "content": "...", "overwrite": true}` |
| append_file | 파일 끝에 추가          | `{"path": "...", "content": "..."}` |
| patch_file  | 앵커/마커 기준 편집     | `{"path": "...", "op": "insert_after|insert_before|replace_between|replace_all", ...}` |
| rename_path | 파일/폴더 이름 변경     | `{"src": "...", "new_name": "..."}` |
| mkdir       | 디렉터리 생성           | `{"path": "...", "parents": true}` |

## 프로젝트/실행

| action         | 설명                    |
|----------------|-------------------------|
| set_project    | 현재 작업 디렉터리 설정 (workdir) |
| index_project  | RAG 인덱싱 (명시적 요청 시만) |
| undo_last      | 마지막 백업 복구 (되돌리기) |
| create_vite_app| Vite 프로젝트 생성 (frontend 등) |

## 명령 실행 (run_cmd)

| cmd_key           | 설명        |
|-------------------|-------------|
| pwd, ls, whoami, date | 기본 셸 |
| git_status, git_diff, git_diff_staged | Git 읽기 |
| git_add, git_commit, git_push | Git 쓰기 (승인 필요) |
| docker_ps, docker_logs_tail, systemctl_status, journalctl_tail | 운영 명령 |

## 기타

| action  | 설명                    |
|---------|-------------------------|
| set_llm | LLM provider/모델 변경 (openai \| ollama) |

---

## 액션 생성 규칙 (plan has no actions 방지)

- **한 줄 가드**: 사용자가 파일/코드 확인을 요구하면, 수정 여부와 무관하게 `actions[0]`에 `read_tail`을 반드시 넣고 시작한다.
- **조회/찾기**: "찾아봐", "있는지 확인", "어떤 코드인지", "열어서 봐줘" → `read_tail(path, lines=500~1200)` 첫 액션. 조회-only라도 최소 1개 read_tail 수행.
- **읽기 후 판단**: read_tail 결과를 받은 뒤에만 patch_file/write_file 추가 또는 요약만 final_answer.
- **경로 모름**: `list_dir(".")` → `list_dir("src")` 등으로 후보 확인 후 `read_tail` 반복.
- **읽기+수정**: "파일 열어서 수정해줘", "찾아서 diff 만들어줘" → read_tail 첫 액션, 이어서 patch_file/write_file. read_tail 없이 수정만 내면 안 됨.
- **조회 전용 가드**: "찾아줘", "검색해줘"만 있고 "수정/만들어줘" 등이 없으면 write 액션은 차단되고, 그때 plan이 비면 LLM에게 "조회 전용 plan만 내라"고 재요청함.
