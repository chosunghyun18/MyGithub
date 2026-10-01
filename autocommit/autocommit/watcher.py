"""폴링 기반 파일 변경 감지 (외부 의존성 없음).

watchdog(FSEvents/inotify)은 Phase 1에서 선택적으로 도입한다. 문서 디렉터리 규모(수천 파일)에서는
1초 간격 mtime 스냅샷 비교로도 충분하고, 에디터별 이벤트 차이를 신경 쓸 필요가 없다.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

Snapshot = dict[str, tuple[float, int]]  # 상대경로 → (mtime, size)

DEFAULT_INCLUDE = ("*.md", "*.markdown", "*.txt", "*.canvas")
DEFAULT_EXCLUDE_DIRS = (".git", ".obsidian", ".trash", "node_modules", ".venv")


def matches(rel_path: str, include: tuple[str, ...]) -> bool:
    name = rel_path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pat) for pat in include)


def take_snapshot(
    root: Path,
    include: tuple[str, ...] = DEFAULT_INCLUDE,
    exclude_dirs: tuple[str, ...] = DEFAULT_EXCLUDE_DIRS,
) -> Snapshot:
    snap: Snapshot = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in exclude_dirs for part in rel.parts):
            continue
        if not p.is_file():
            continue
        rel_s = rel.as_posix()
        if matches(rel_s, include):
            st = p.stat()
            snap[rel_s] = (st.st_mtime, st.st_size)
    return snap


def diff_snapshots(before: Snapshot, after: Snapshot) -> list[str]:
    """추가·수정·삭제된 경로 (정렬)."""
    changed = {p for p in after if before.get(p) != after[p]}
    changed |= set(before) - set(after)
    return sorted(changed)
