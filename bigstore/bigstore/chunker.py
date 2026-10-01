"""청킹 — 고정 크기(fixed) / 내용 기반(CDC, Gear rolling hash).

- fixed: 빠르다. 파일 중간에 바이트가 삽입되면 이후 청크가 전부 밀려 dedupe가 깨진다.
- cdc  : 경계를 내용으로 정한다 → 삽입/삭제가 있어도 주변 청크만 바뀌고 나머지는 재사용.
         FastCDC 단순화 버전(정규화 없음). 순수 Python이라 느리다(대략 수~수십 MB/s) —
         대용량 실사용은 Phase 2에서 네이티브 구현(fastcdc 패키지 등)으로 교체한다.
         교체해도 Chunker 인터페이스와 포인터/매니페스트 포맷은 그대로 유지.

청크 경계는 결정적(deterministic)이어야 한다: 같은 입력 → 같은 청크 → 같은 해시.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import BinaryIO, Iterator, Protocol

MiB = 1024 * 1024


class Chunker(Protocol):
    name: str

    def chunks(self, stream: BinaryIO) -> Iterator[bytes]: ...


@dataclass(frozen=True)
class FixedChunker:
    size: int = 8 * MiB
    name: str = "fixed"

    def chunks(self, stream: BinaryIO) -> Iterator[bytes]:
        while True:
            block = stream.read(self.size)
            if not block:
                return
            yield block


def _gear_table() -> tuple[int, ...]:
    # 고정 시드로 생성 → 버전/머신 간 동일한 경계 보장
    return tuple(
        int.from_bytes(hashlib.sha256(b"bigstore-gear-%d" % i).digest()[:8], "big")
        for i in range(256)
    )


_GEAR = _gear_table()
_MASK64 = (1 << 64) - 1


@dataclass(frozen=True)
class CdcChunker:
    min_size: int = 2 * MiB
    avg_size: int = 8 * MiB
    max_size: int = 32 * MiB
    name: str = "cdc"

    def __post_init__(self) -> None:
        if not (0 < self.min_size <= self.avg_size <= self.max_size):
            raise ValueError("min <= avg <= max 이어야 함")
        if self.avg_size & (self.avg_size - 1):
            raise ValueError("avg_size는 2의 거듭제곱이어야 함")

    @property
    def _mask(self) -> int:
        # 상위 비트를 사용 (gear hash는 하위 비트가 최근 바이트에만 의존)
        bits = self.avg_size.bit_length() - 1
        return ((1 << bits) - 1) << (64 - bits)

    def find_cut(self, data: bytes | bytearray | memoryview) -> int:
        """data 앞부분에서 첫 청크의 길이를 반환."""
        n = len(data)
        if n <= self.min_size:
            return n
        end = min(n, self.max_size)
        mask = self._mask
        gear = _GEAR
        h = 0
        for i in range(self.min_size, end):
            h = ((h << 1) + gear[data[i]]) & _MASK64
            if not (h & mask):
                return i + 1
        return end

    def chunks(self, stream: BinaryIO) -> Iterator[bytes]:
        buf = bytearray()
        eof = False
        while True:
            while not eof and len(buf) < self.max_size:
                block = stream.read(self.max_size)
                if not block:
                    eof = True
                else:
                    buf += block
            if not buf:
                return
            if eof and len(buf) <= self.min_size:
                yield bytes(buf)
                return
            cut = self.find_cut(buf)
            yield bytes(buf[:cut])
            del buf[:cut]


def make_chunker(name: str, **kw: int) -> Chunker:
    if name == "fixed":
        return FixedChunker(**kw)
    if name == "cdc":
        return CdcChunker(**kw)
    raise ValueError(f"알 수 없는 chunker: {name}")
