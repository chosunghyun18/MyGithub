# MyGithub

GitHub를 쓰면서 겪는 세 가지 불편을 해결하는 개인 도구 모음.

| 문제 | 모듈 | 해결 방식 |
|---|---|---|
| 레포가 너무 많아 한눈에 안 보이고 정리할 방법이 없다 | `web/` | 레포를 폴더(컬럼)에 **드래그앤드롭**으로 배치하는 보드. 언어·활동성·종류 기준 자동 1차 분류 |
| 문서를 고칠 때마다 "Commit changes" 버튼을 눌러야 한다 | `autocommit/` | 문서 디렉터리 감시 → 저장이 멈추면 **diff 요약 메시지로 자동 커밋** |
| 2GB가 넘는 파일은 GitHub(LFS 포함)에 못 올린다 | `bigstore/` | 파일을 청크로 쪼개 SHA-256 content-addressed 저장소(로컬/S3/R2)에 두고, git에는 **포인터 파일만 커밋** |

설계 SSOT: Obsidian `Projects/work/MyGithub/MyGithub Design Spec.md` (코드와 충돌 시 문서 우선)

## 구조

```
MyGithub/
├── web/                     # 레포 정리 보드 (React + Vite + TS)
│   ├── src/lib/board.ts     #   그룹핑·재정렬·동기화 순수 로직 (+ board.test.ts)
│   ├── src/lib/github.ts    #   GitHub REST 읽기 전용 클라이언트 (+ github.test.ts)
│   └── src/App.tsx          #   @dnd-kit 보드 UI, localStorage 저장 + JSON 내보내기
├── autocommit/              # 저장 시 자동 커밋 CLI (Python)
│   ├── autocommit/batcher.py   # 디바운스 배치 (quiet / max-wait)
│   ├── autocommit/message.py   # numstat 파싱 + 메시지 생성 (MessageGenerator 인터페이스)
│   ├── autocommit/watcher.py   # 폴링 스냅샷 diff
│   ├── autocommit/gitops.py    # git add/diff/commit 래퍼
│   └── autocommit/cli.py
├── bigstore/                # 대용량 파일 버전 관리 CLI (Python)
│   ├── bigstore/chunker.py     # fixed / CDC(Gear hash) 청킹
│   ├── bigstore/manifest.py    # 매니페스트 + 포인터 파일 포맷
│   ├── bigstore/backend.py     # Backend 인터페이스, LocalBackend
│   ├── bigstore/store.py       # 저장(dedupe)·복원(검증)·gc
│   └── bigstore/cli.py
├── CLAUDE.md
└── README.md
```

## 실행 방법

### 준비

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
(cd web && npm install)
```

### web — 레포 정리 보드

```bash
cd web && npm run dev     # http://localhost:5173
```

1. GitHub → Settings → Developer settings → Fine-grained token 생성
   (Repository access: All repositories, Permissions: **Metadata: Read-only**만)
2. 토큰 입력 → "레포 불러오기" → 컬럼(폴더) 추가 후 카드를 드래그
3. 배치는 브라우저 localStorage에 저장. "JSON 내보내기"로 백업

### autocommit — 저장 시 자동 커밋

```bash
cd autocommit
../.venv/bin/python -m autocommit.cli once  ~/notes --dry-run   # 메시지 미리보기
../.venv/bin/python -m autocommit.cli watch ~/notes --quiet 5 --max-wait 120
# → [commit] docs: update X.md (+12/-3)
```

push는 하지 않는다(로컬 커밋만). 원격 반영은 Phase 1에서 옵션으로 추가.

### bigstore — 2GB 초과 파일

```bash
cd <내 git 레포>
python -m bigstore.cli init --backend ~/bigstore-objects   # --chunker cdc 선택 가능
python -m bigstore.cli add data/huge.mov    # → data/huge.mov.bsp 생성, 원본은 .gitignore
git add data/huge.mov.bsp .gitignore .bigstore && git commit -m "data: add huge.mov"
python -m bigstore.cli status               # ok / modified / missing
python -m bigstore.cli checkout             # 포인터 → 원본 복원 (다른 머신, 과거 커밋 checkout 후)
```

(`PYTHONPATH=<MyGithub>/bigstore` 또는 `pip install -e bigstore` 필요)

### 테스트

```bash
(cd autocommit && ../.venv/bin/pytest -q)
(cd bigstore   && ../.venv/bin/pytest -q)
(cd web        && npm test)
```

## 로드맵

| Phase | 내용 | 완료 기준 |
|---|---|---|
| **0** | 스캐폴드 + 핵심 순수 로직 + 테스트 | 세 모듈 테스트 통과, 설계 문서 확정 ← 현재 |
| **1** | 실사용 MVP | web: 내 실제 레포 전체로 보드 정리 / autocommit: Obsidian 볼트에서 1주 상시 운용 / bigstore: 실제 >2GB 파일 add→clone→checkout 왕복 |
| **2** | 동기화·원격 | web: 보드를 private Gist로 동기화 / autocommit: 자동 push·LLM 메시지(옵트인) / bigstore: S3·R2 백엔드, 네이티브 CDC, `git` clean/smudge 필터 연동 |
| **3** | 편의 | web: 태그·검색·아카이브 일괄 작업(쓰기 권한 옵트인) / autocommit: launchd 상주 / bigstore: 히스토리 기반 gc, 부분(range) 복원 |
