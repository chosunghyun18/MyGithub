"""git 명령 래퍼 (subprocess). 순수 로직은 message.py / batcher.py 에 있다."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from .message import MessageGenerator, RuleBasedMessageGenerator, parse_numstat


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def repo_root(path: Path) -> Path:
    return Path(_git(path, "rev-parse", "--show-toplevel").strip())


def commit_paths(
    repo: Path,
    paths: Sequence[str],
    generator: MessageGenerator | None = None,
    dry_run: bool = False,
) -> str | None:
    """경로들을 stage → 메시지 생성 → 커밋. 실제 변경이 없으면 None.

    ``paths`` 는 repo 기준 상대경로. 삭제된 파일도 ``git add -A -- <path>`` 로 반영된다.
    이미 stage되어 있던 다른 파일은 커밋에 섞이지 않도록 ``-- <paths>`` 로 범위를 제한한다.
    """
    if not paths:
        return None
    generator = generator or RuleBasedMessageGenerator()
    _git(repo, "add", "-A", "--", *paths)
    numstat = _git(repo, "diff", "--cached", "--numstat", "--no-renames", "--", *paths)
    if not numstat.strip():
        return None
    name_status = _git(repo, "diff", "--cached", "--name-status", "--no-renames", "--", *paths)
    stats = parse_numstat(numstat, name_status)
    message = generator.generate(stats)
    if dry_run:
        try:
            _git(repo, "reset", "-q", "--", *paths)
        except subprocess.CalledProcessError:  # 첫 커밋 전(HEAD 없음)
            _git(repo, "rm", "-q", "--cached", "-r", "--", *paths)
        return message
    _git(repo, "commit", "-q", "-m", message, "--", *paths)
    return message
