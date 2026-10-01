import io
import random
from pathlib import Path

import pytest

from bigstore.backend import LocalBackend, MemoryBackend
from bigstore.chunker import CdcChunker, FixedChunker
from bigstore.manifest import Manifest, Pointer, chunk_key, manifest_key
from bigstore.store import gc, restore_file, restore_to_stream, store_file, store_stream

KiB = 1024
CDC = CdcChunker(min_size=1 * KiB, avg_size=4 * KiB, max_size=16 * KiB)


def rand_bytes(n: int, seed: int = 0) -> bytes:
    return random.Random(seed).randbytes(n)


def roundtrip(data: bytes, backend, chunker=CDC) -> bytes:
    r = store_stream(io.BytesIO(data), backend, chunker)
    out = io.BytesIO()
    restore_to_stream(r.pointer, backend, out)
    return out.getvalue()


@pytest.mark.parametrize("chunker", [CDC, FixedChunker(4 * KiB)])
def test_roundtrip(chunker):
    data = rand_bytes(150 * KiB)
    assert roundtrip(data, MemoryBackend(), chunker) == data


def test_roundtrip_empty_file():
    assert roundtrip(b"", MemoryBackend()) == b""


def test_dedupe_identical_store_uploads_nothing():
    be = MemoryBackend()
    data = rand_bytes(100 * KiB)
    r1 = store_stream(io.BytesIO(data), be, CDC)
    puts = be.puts
    r2 = store_stream(io.BytesIO(data), be, CDC)
    assert r2.pointer == r1.pointer
    assert r2.chunks_new == 0 and be.puts == puts


def test_dedupe_across_versions():
    """v2 = v1 중간 수정 → 신규 청크는 소수, 나머지 재사용."""
    be = MemoryBackend()
    v1 = rand_bytes(300 * KiB, seed=7)
    v2 = v1[:150 * KiB] + b"patch" * 100 + v1[150 * KiB + 500:]
    r1 = store_stream(io.BytesIO(v1), be, CDC)
    r2 = store_stream(io.BytesIO(v2), be, CDC)
    assert r1.pointer.oid != r2.pointer.oid
    assert r2.chunks_new <= 3
    assert r2.chunks_reused >= r2.chunks_total - 3
    assert r2.bytes_new < len(v2) * 0.2
    # 두 버전 모두 복원 가능
    for r, data in [(r1, v1), (r2, v2)]:
        out = io.BytesIO()
        restore_to_stream(r.pointer, be, out)
        assert out.getvalue() == data


def test_pointer_roundtrip_and_validation():
    p = Pointer(oid="a" * 64, size=123, manifest="b" * 64)
    text = p.dumps()
    assert text.startswith("version ")
    assert Pointer.loads(text) == p
    with pytest.raises(ValueError):
        Pointer.loads("hello world")
    with pytest.raises(ValueError):
        Pointer.loads(text.replace("a" * 64, "zz"))


def test_manifest_bytes_are_canonical():
    m = Manifest(oid="c" * 64, size=3, chunker="cdc", chunks=(("d" * 64, 1), ("e" * 64, 2)))
    assert Manifest.from_bytes(m.to_bytes()) == m
    assert m.digest == Manifest.from_bytes(m.to_bytes()).digest
    bad = m.to_bytes().replace(b'"size":3', b'"size":4')
    with pytest.raises(ValueError):
        Manifest.from_bytes(bad)


def test_corrupted_chunk_detected():
    be = MemoryBackend()
    r = store_stream(io.BytesIO(rand_bytes(50 * KiB)), be, CDC)
    m = Manifest.from_bytes(be.get(manifest_key(r.pointer.manifest)))
    key = chunk_key(m.chunks[0][0])
    be.data[key] = b"X" + be.data[key][1:]
    with pytest.raises(ValueError, match="청크 손상"):
        restore_to_stream(r.pointer, be, io.BytesIO())


def test_local_backend_file_restore_and_gc(tmp_path: Path):
    be = LocalBackend(tmp_path / "objects")
    src = tmp_path / "big.bin"
    v1 = rand_bytes(80 * KiB, seed=1)
    src.write_bytes(v1)
    r1 = store_file(src, be, CDC)
    src.write_bytes(rand_bytes(80 * KiB, seed=2))  # 완전히 다른 v2
    r2 = store_file(src, be, CDC)

    dest = tmp_path / "out" / "big.bin"
    restore_file(r1.pointer, be, dest)
    assert dest.read_bytes() == v1

    # v1 포인터만 살아있다고 가정 → v2 전용 오브젝트 삭제
    dm, dc = gc(be, [r1.pointer])
    assert dm == 1 and dc == r2.chunks_new
    restore_file(r1.pointer, be, dest)  # v1은 여전히 복원 가능
    with pytest.raises(FileNotFoundError):
        restore_file(r2.pointer, be, dest)
    assert dest.read_bytes() == v1  # 실패한 복원이 기존 파일을 망가뜨리지 않음


def test_local_backend_rejects_path_traversal(tmp_path: Path):
    be = LocalBackend(tmp_path)
    with pytest.raises(ValueError):
        be.put("../evil", b"x")
