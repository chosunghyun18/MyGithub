"""저장소 백엔드 — 키/값 오브젝트 스토어 인터페이스.

키는 ``chunks/ab/<sha256>`` / ``manifests/cd/<sha256>`` 형식. 오브젝트는 불변(immutable)이라
같은 키에 다시 쓰지 않는다 → S3/R2 같은 eventual consistency 스토어에서도 안전.

- LocalBackend: 로컬 디렉터리 (외장 디스크·NAS 마운트 포함)  ← Phase 0
- S3Backend   : S3 / Cloudflare R2 (S3 호환, egress 무료)   ← Phase 2, boto3 선택 의존성
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterator, Protocol


class Backend(Protocol):
    def has(self, key: str) -> bool: ...
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def keys(self, prefix: str = "") -> Iterator[str]: ...
    def delete(self, key: str) -> None: ...


class LocalBackend:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"잘못된 키: {key}")
        return self.root / key

    def has(self, key: str) -> bool:
        return self._path(key).is_file()

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        # 원자적 쓰기: 중간에 죽어도 반쯤 쓴 오브젝트가 남지 않는다
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, p)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def keys(self, prefix: str = "") -> Iterator[str]:
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and not p.name.startswith(".tmp-"):
                k = p.relative_to(self.root).as_posix()
                if k.startswith(prefix):
                    yield k

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class MemoryBackend:
    """테스트용."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.puts = 0

    def has(self, key: str) -> bool:
        return key in self.data

    def put(self, key: str, data: bytes) -> None:
        self.puts += 1
        self.data[key] = data

    def get(self, key: str) -> bytes:
        return self.data[key]

    def keys(self, prefix: str = "") -> Iterator[str]:
        return iter(sorted(k for k in self.data if k.startswith(prefix)))

    def delete(self, key: str) -> None:
        self.data.pop(key, None)
