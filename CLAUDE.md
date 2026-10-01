# MyGithub

GitHub 사용 불편 3가지를 해결하는 개인 도구 모음 (모노레포).

- `web/` — 레포 정리 보드: 드래그앤드롭 폴더/컬럼 (React + Vite + TS, @dnd-kit)
- `autocommit/` — 문서 저장 시 자동 커밋 CLI (Python, 의존성 없음)
- `bigstore/` — 2GB 초과 파일 청크 저장 + git 포인터 버전 관리 CLI (Python, 의존성 없음)

## 설계 SSOT

설계 SSOT는 Obsidian `Projects/work/MyGithub/` (`MyGithub Design Spec.md`, `task/todo.md`).
코드와 문서가 충돌하면 **문서 우선**. 설계 변경은 문서를 먼저 고친다.

## 컨벤션

- 문서·주석은 한국어, 식별자는 영어.
- 순수 로직(그룹핑/재정렬, 디바운스, 메시지 생성, 청킹, 매니페스트)은 I/O와 분리하고 반드시 테스트.
  - web: `src/lib/*.ts` (React 비의존) → vitest
  - Python: 시간·파일·git은 주입/래퍼로 분리 → pytest
- GitHub 권한은 읽기 전용(fine-grained PAT, Metadata: read)만. 쓰기 스코프 요구 기능은 문서에서 먼저 합의.
- Python 의존성은 최소화(표준 라이브러리 우선). 선택 기능(watchdog, boto3, LLM)은 optional extra.
- `.venv`, `node_modules`, 캐시, 대용량 테스트 파일은 커밋 금지.

## 테스트

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
(cd autocommit && ../.venv/bin/pytest -q)
(cd bigstore && ../.venv/bin/pytest -q)
(cd web && npm install && npm test)
```
