"""커밋 메시지 생성 — 순수 로직.

입력은 ``git diff --cached --numstat`` / ``--name-status`` 결과를 파싱한 FileStat 목록.
기본 구현은 규칙 기반이고, LLM 기반 생성기는 같은 Protocol을 구현해 끼워 넣는다
(Phase 2 — 네트워크·비용이 들므로 옵트인, 실패 시 규칙 기반으로 폴백).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol, Sequence

# git status 코드 → 동사
_VERBS = {"A": "add", "M": "update", "D": "remove", "R": "rename"}


@dataclass(frozen=True)
class FileStat:
    path: str
    added: int  # 바이너리면 0
    deleted: int
    status: str = "M"  # A / M / D / R
    binary: bool = False


class MessageGenerator(Protocol):
    def generate(self, stats: Sequence[FileStat], diff_text: str = "") -> str: ...


def parse_numstat(numstat: str, name_status: str = "") -> list[FileStat]:
    """``git diff --numstat`` (+ 선택적으로 ``--name-status``) 출력 파싱.

    numstat 행: ``<added>\\t<deleted>\\t<path>`` (바이너리는 ``-\\t-\\t<path>``)
    name-status 행: ``<status>\\t<path>`` 또는 rename ``R100\\t<old>\\t<new>``
    """
    statuses: dict[str, str] = {}
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0]:
            statuses[parts[-1]] = parts[0][0]

    out: list[FileStat] = []
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[-1]
        # numstat rename 표기 "dir/{old => new}.md" 는 -M 없이 호출하므로 등장하지 않음
        binary = a == "-" or d == "-"
        out.append(
            FileStat(
                path=path,
                added=0 if binary else int(a),
                deleted=0 if binary else int(d),
                status=statuses.get(path, "M"),
                binary=binary,
            )
        )
    return out


def _counts(added: int, deleted: int) -> str:
    return f"(+{added}/-{deleted})"


class RuleBasedMessageGenerator:
    """규칙 기반 메시지.

    - 1개 파일: ``docs: update guide.md (+12/-3)``
    - 같은 동사 여러 파일: ``docs: update 3 files in notes/ (+40/-7)``
    - 동사 혼합: ``docs: update 2, add 1 files (+40/-7)``
    본문(body)에는 파일별 상세를 나열한다.
    """

    def __init__(self, prefix: str = "docs", max_body_lines: int = 20) -> None:
        self.prefix = prefix
        self.max_body_lines = max_body_lines

    def generate(self, stats: Sequence[FileStat], diff_text: str = "") -> str:
        if not stats:
            raise ValueError("변경 사항이 없음")
        total_a = sum(s.added for s in stats)
        total_d = sum(s.deleted for s in stats)

        if len(stats) == 1:
            s = stats[0]
            name = PurePosixPath(s.path).name
            return f"{self.prefix}: {_VERBS.get(s.status, 'update')} {name} {_counts(s.added, s.deleted)}"

        verbs: dict[str, int] = {}
        for s in stats:
            v = _VERBS.get(s.status, "update")
            verbs[v] = verbs.get(v, 0) + 1

        if len(verbs) == 1:
            verb = next(iter(verbs))
            scope = _common_dir([s.path for s in stats])
            where = f" in {scope}/" if scope else ""
            subject = f"{verb} {len(stats)} files{where}"
        else:
            order = ["update", "add", "remove", "rename"]
            subject = ", ".join(f"{k} {verbs[k]}" for k in order if k in verbs) + " files"

        header = f"{self.prefix}: {subject} {_counts(total_a, total_d)}"
        body = [
            f"- {_VERBS.get(s.status, 'update')} {s.path}"
            + (" (binary)" if s.binary else f" {_counts(s.added, s.deleted)}")
            for s in sorted(stats, key=lambda x: x.path)
        ]
        if len(body) > self.max_body_lines:
            rest = len(body) - self.max_body_lines
            body = body[: self.max_body_lines] + [f"- … 외 {rest}개"]
        return header + "\n\n" + "\n".join(body)


def _common_dir(paths: Sequence[str]) -> str:
    parents = [PurePosixPath(p).parent.parts for p in paths]
    common: list[str] = []
    for parts in zip(*parents):
        if all(p == parts[0] for p in parts):
            common.append(parts[0])
        else:
            break
    return "/".join(common)
