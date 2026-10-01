"""파일 저장/복원/정리 — chunker + backend + manifest 조합."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable

from .backend import Backend
from .chunker import Chunker
from .manifest import Manifest, Pointer, chunk_key, manifest_key, sha256_hex


@dataclass(frozen=True)
class StoreResult:
    pointer: Pointer
    chunks_total: int
    chunks_new: int
    bytes_new: int

    @property
    def chunks_reused(self) -> int:
        return self.chunks_total - self.chunks_new


def store_stream(stream: BinaryIO, backend: Backend, chunker: Chunker) -> StoreResult:
    """스트림을 청크로 나눠 저장. 이미 있는 청크는 업로드하지 않는다(dedupe)."""
    whole = hashlib.sha256()
    chunks: list[tuple[str, int]] = []
    new = 0
    bytes_new = 0
    size = 0
    for block in chunker.chunks(stream):
        whole.update(block)
        size += len(block)
        h = sha256_hex(block)
        chunks.append((h, len(block)))
        key = chunk_key(h)
        if not backend.has(key):
            backend.put(key, block)
            new += 1
            bytes_new += len(block)
    manifest = Manifest(oid=whole.hexdigest(), size=size, chunker=chunker.name, chunks=tuple(chunks))
    mkey = manifest_key(manifest.digest)
    if not backend.has(mkey):
        backend.put(mkey, manifest.to_bytes())
    return StoreResult(
        pointer=Pointer(oid=manifest.oid, size=size, manifest=manifest.digest),
        chunks_total=len(chunks),
        chunks_new=new,
        bytes_new=bytes_new,
    )


def store_file(path: Path, backend: Backend, chunker: Chunker) -> StoreResult:
    with open(path, "rb") as f:
        return store_stream(f, backend, chunker)


def load_manifest(pointer: Pointer, backend: Backend) -> Manifest:
    data = backend.get(manifest_key(pointer.manifest))
    if sha256_hex(data) != pointer.manifest:
        raise ValueError("매니페스트 해시 불일치 (손상)")
    m = Manifest.from_bytes(data)
    if m.oid != pointer.oid or m.size != pointer.size:
        raise ValueError("포인터와 매니페스트 불일치")
    return m


def restore_to_stream(pointer: Pointer, backend: Backend, out: BinaryIO) -> None:
    """청크를 이어 붙여 복원. 청크별·전체 해시를 모두 검증한다."""
    m = load_manifest(pointer, backend)
    whole = hashlib.sha256()
    for h, n in m.chunks:
        block = backend.get(chunk_key(h))
        if len(block) != n or sha256_hex(block) != h:
            raise ValueError(f"청크 손상: {h}")
        whole.update(block)
        out.write(block)
    if whole.hexdigest() != pointer.oid:
        raise ValueError("복원 결과 해시 불일치")


def restore_file(pointer: Pointer, backend: Backend, dest: Path) -> None:
    """임시 파일에 복원 후 rename — 검증 실패 시 기존 파일을 건드리지 않는다."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            restore_to_stream(pointer, backend, f)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def file_oid(path: Path, bufsize: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(bufsize):
            h.update(block)
    return h.hexdigest()


def gc(backend: Backend, live: Iterable[Pointer]) -> tuple[int, int]:
    """살아있는 포인터(보통 git 전체 히스토리의 모든 .bsp)가 참조하지 않는 오브젝트 삭제.

    반환: (삭제된 매니페스트 수, 삭제된 청크 수)
    """
    live_manifests: set[str] = set()
    live_chunks: set[str] = set()
    for p in live:
        live_manifests.add(manifest_key(p.manifest))
        live_chunks.update(chunk_key(h) for h, _ in load_manifest(p, backend).chunks)
    dm = dc = 0
    for k in list(backend.keys("manifests/")):
        if k not in live_manifests:
            backend.delete(k)
            dm += 1
    for k in list(backend.keys("chunks/")):
        if k not in live_chunks:
            backend.delete(k)
            dc += 1
    return dm, dc
