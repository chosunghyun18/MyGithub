import io
import random

import pytest

from bigstore.chunker import CdcChunker, FixedChunker, make_chunker

KiB = 1024


def rand_bytes(n: int, seed: int = 0) -> bytes:
    return random.Random(seed).randbytes(n)


def test_fixed_chunks_reassemble():
    data = rand_bytes(10 * KiB + 7)
    chunks = list(FixedChunker(size=4 * KiB).chunks(io.BytesIO(data)))
    assert [len(c) for c in chunks] == [4 * KiB, 4 * KiB, 2 * KiB + 7]
    assert b"".join(chunks) == data


def test_empty_stream_has_no_chunks():
    assert list(FixedChunker(4).chunks(io.BytesIO(b""))) == []
    assert list(CdcChunker(64, 256, 1024).chunks(io.BytesIO(b""))) == []


@pytest.mark.parametrize("size", [1, 100, 4 * KiB, 64 * KiB + 3])
def test_cdc_reassemble_and_bounds(size):
    c = CdcChunker(min_size=1 * KiB, avg_size=4 * KiB, max_size=16 * KiB)
    data = rand_bytes(size, seed=size)
    chunks = list(c.chunks(io.BytesIO(data)))
    assert b"".join(chunks) == data
    assert all(len(x) <= c.max_size for x in chunks)
    assert all(len(x) >= c.min_size for x in chunks[:-1])  # 마지막만 짧을 수 있음


def test_cdc_is_deterministic():
    c = CdcChunker(min_size=1 * KiB, avg_size=4 * KiB, max_size=16 * KiB)
    data = rand_bytes(100 * KiB)
    a = [len(x) for x in c.chunks(io.BytesIO(data))]
    b = [len(x) for x in c.chunks(io.BytesIO(data))]
    assert a == b
    assert len(a) > 5  # 실제로 내용 기반 경계가 생김


def test_cdc_boundaries_survive_insertion():
    """앞부분에 바이트를 삽입해도 뒤쪽 청크 대부분은 그대로 — fixed는 전부 깨짐."""
    data = rand_bytes(200 * KiB, seed=1)
    edited = data[:5000] + b"INSERTED" + data[5000:]
    for chunker, expect_most_shared in [
        (CdcChunker(1 * KiB, 4 * KiB, 16 * KiB), True),
        (FixedChunker(4 * KiB), False),
    ]:
        a = set(chunker.chunks(io.BytesIO(data)))
        b = list(chunker.chunks(io.BytesIO(edited)))
        shared = sum(1 for x in b if x in a)
        if expect_most_shared:
            assert shared >= len(b) - 3
        else:
            assert shared <= 1


def test_invalid_params():
    with pytest.raises(ValueError):
        CdcChunker(min_size=10, avg_size=3000, max_size=5000)  # avg 2의 거듭제곱 아님
    with pytest.raises(ValueError):
        CdcChunker(min_size=5000, avg_size=4096, max_size=8192)
    with pytest.raises(ValueError):
        make_chunker("nope")
