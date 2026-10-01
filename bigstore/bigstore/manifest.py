"""매니페스트(청크 목록)와 포인터 파일.

포인터 파일(git에 커밋되는 작은 텍스트, Git LFS 포인터와 같은 발상)::

    version https://github.com/chosunghyun18/MyGithub/bigstore/v1
    oid sha256:<원본 파일 전체 해시>
    size <바이트>
    manifest sha256:<매니페스트 오브젝트 해시>

매니페스트(백엔드에 저장되는 JSON, content-addressed)::

    {"version": 1, "size": N, "oid": "<sha>", "chunker": "cdc",
     "chunks": [["<sha>", <len>], ...]}

git이 포인터의 히스토리를 관리하므로 버전 관리(log/diff/branch/revert)는 git 그대로 쓴다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

POINTER_VERSION = "https://github.com/chosunghyun18/MyGithub/bigstore/v1"
POINTER_SUFFIX = ".bsp"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def chunk_key(digest: str) -> str:
    return f"chunks/{digest[:2]}/{digest}"


def manifest_key(digest: str) -> str:
    return f"manifests/{digest[:2]}/{digest}"


@dataclass(frozen=True)
class Manifest:
    oid: str
    size: int
    chunker: str
    chunks: tuple[tuple[str, int], ...] = field(default_factory=tuple)

    def to_bytes(self) -> bytes:
        # 정렬·공백 고정 → 같은 내용이면 같은 해시
        return json.dumps(
            {
                "version": 1,
                "oid": self.oid,
                "size": self.size,
                "chunker": self.chunker,
                "chunks": [list(c) for c in self.chunks],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    @property
    def digest(self) -> str:
        return sha256_hex(self.to_bytes())

    @classmethod
    def from_bytes(cls, data: bytes) -> "Manifest":
        d = json.loads(data)
        if d.get("version") != 1:
            raise ValueError(f"지원하지 않는 매니페스트 버전: {d.get('version')}")
        m = cls(
            oid=d["oid"],
            size=d["size"],
            chunker=d["chunker"],
            chunks=tuple((h, n) for h, n in d["chunks"]),
        )
        if sum(n for _, n in m.chunks) != m.size:
            raise ValueError("매니페스트 크기 불일치")
        return m


@dataclass(frozen=True)
class Pointer:
    oid: str
    size: int
    manifest: str

    def dumps(self) -> str:
        return (
            f"version {POINTER_VERSION}\n"
            f"oid sha256:{self.oid}\n"
            f"size {self.size}\n"
            f"manifest sha256:{self.manifest}\n"
        )

    @classmethod
    def loads(cls, text: str) -> "Pointer":
        fields: dict[str, str] = {}
        for line in text.splitlines():
            if not line.strip():
                continue
            k, _, v = line.partition(" ")
            fields[k] = v
        if fields.get("version") != POINTER_VERSION:
            raise ValueError("bigstore 포인터 파일이 아님")
        try:
            oid = fields["oid"].removeprefix("sha256:")
            manifest = fields["manifest"].removeprefix("sha256:")
            size = int(fields["size"])
        except (KeyError, ValueError) as e:
            raise ValueError(f"손상된 포인터 파일: {e}") from e
        for h in (oid, manifest):
            if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
                raise ValueError(f"잘못된 해시: {h}")
        return cls(oid=oid, size=size, manifest=manifest)
