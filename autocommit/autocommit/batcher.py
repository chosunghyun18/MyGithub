"""디바운스 배치 — 순수 로직 (시간은 외부에서 주입).

에디터는 저장 한 번에 여러 이벤트(임시파일 쓰기, rename, 메타데이터 변경)를 낸다.
연속 저장마다 커밋하면 히스토리가 지저분해지므로:

- 마지막 변경 후 ``quiet_seconds`` 동안 조용하면 → 묶어서 flush
- 계속 편집 중이어도 첫 변경 후 ``max_wait_seconds`` 가 지나면 → 강제 flush
  (장시간 편집 중 작업이 유실되지 않도록)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChangeBatcher:
    quiet_seconds: float = 5.0
    max_wait_seconds: float = 120.0
    _pending: dict[str, float] = field(default_factory=dict)
    _first_at: float | None = None
    _last_at: float | None = None

    def add(self, path: str, now: float) -> None:
        """변경 이벤트 기록. 같은 경로는 한 번만 남는다."""
        self._pending[path] = now
        if self._first_at is None:
            self._first_at = now
        self._last_at = now

    @property
    def pending(self) -> list[str]:
        return sorted(self._pending)

    def due(self, now: float) -> bool:
        if not self._pending:
            return False
        assert self._first_at is not None and self._last_at is not None
        return (
            now - self._last_at >= self.quiet_seconds
            or now - self._first_at >= self.max_wait_seconds
        )

    def flush_if_due(self, now: float) -> list[str] | None:
        """flush 시점이면 묶인 경로 목록(정렬)을 반환하고 비운다. 아니면 None."""
        if not self.due(now):
            return None
        batch = self.pending
        self._pending.clear()
        self._first_at = self._last_at = None
        return batch
