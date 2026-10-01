"""CLI 진입점.

    python -m autocommit.cli watch <docs_dir> [--quiet 5] [--max-wait 120] [--interval 1]
    python -m autocommit.cli once  <docs_dir> [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .batcher import ChangeBatcher
from .gitops import commit_paths, repo_root
from .message import RuleBasedMessageGenerator
from .watcher import DEFAULT_INCLUDE, diff_snapshots, take_snapshot


def _to_repo_rel(repo: Path, docs: Path, rels: list[str]) -> list[str]:
    base = docs.resolve().relative_to(repo.resolve())
    return [(base / r).as_posix() if str(base) != "." else r for r in rels]


def cmd_once(args: argparse.Namespace) -> int:
    docs = Path(args.dir)
    repo = repo_root(docs)
    rels = sorted(take_snapshot(docs, tuple(args.include)))
    msg = commit_paths(
        repo,
        _to_repo_rel(repo, docs, rels) or ["."],
        RuleBasedMessageGenerator(args.prefix),
        dry_run=args.dry_run,
    )
    print(msg or "변경 없음")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    docs = Path(args.dir)
    repo = repo_root(docs)
    include = tuple(args.include)
    gen = RuleBasedMessageGenerator(args.prefix)
    batcher = ChangeBatcher(args.quiet, args.max_wait)
    snap = take_snapshot(docs, include)
    print(f"감시 시작: {docs.resolve()} (repo={repo}, quiet={args.quiet}s)")
    try:
        while True:
            time.sleep(args.interval)
            now = time.monotonic()
            new = take_snapshot(docs, include)
            for p in diff_snapshots(snap, new):
                batcher.add(p, now)
            snap = new
            batch = batcher.flush_if_due(now)
            if batch:
                msg = commit_paths(repo, _to_repo_rel(repo, docs, batch), gen)
                if msg:
                    print(f"[commit] {msg.splitlines()[0]}")
    except KeyboardInterrupt:
        # 종료 직전 남은 변경 커밋
        if batcher.pending:
            commit_paths(repo, _to_repo_rel(repo, docs, batcher.pending), gen)
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="autocommit", description="문서 저장 시 자동 커밋")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("watch", "once"):
        s = sub.add_parser(name)
        s.add_argument("dir")
        s.add_argument("--prefix", default="docs")
        s.add_argument("--include", nargs="+", default=list(DEFAULT_INCLUDE))
    w = sub.choices["watch"]
    w.add_argument("--quiet", type=float, default=5.0, help="마지막 저장 후 대기(초)")
    w.add_argument("--max-wait", type=float, default=120.0, help="연속 편집 시 최대 대기(초)")
    w.add_argument("--interval", type=float, default=1.0, help="폴링 간격(초)")
    sub.choices["once"].add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return cmd_watch(args) if args.cmd == "watch" else cmd_once(args)


if __name__ == "__main__":
    sys.exit(main())
