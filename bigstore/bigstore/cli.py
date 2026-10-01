"""CLI 진입점 (git 레포 루트에서 실행).

    bigstore init --backend ~/bigstore-objects [--chunker cdc|fixed]
    bigstore add <file>...        # 청크 저장 + <file>.bsp 포인터 생성 + 원본은 .gitignore
    bigstore checkout [<file>...] # 포인터 → 원본 복원 (인자 없으면 전체)
    bigstore status               # 포인터와 작업 파일 비교
    bigstore gc                   # 현재 작업트리 포인터 기준 미참조 오브젝트 삭제 (주의: 히스토리 미반영)

설정은 ``.bigstore/config.json`` (git에 커밋 — 백엔드 위치를 팀/머신 간 공유).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .backend import Backend, LocalBackend
from .chunker import Chunker, make_chunker
from .manifest import POINTER_SUFFIX, Pointer
from .store import file_oid, gc, restore_file, store_file

CONFIG = Path(".bigstore/config.json")


def load_config(root: Path) -> dict:
    p = root / CONFIG
    if not p.exists():
        raise SystemExit("bigstore 미초기화: `bigstore init --backend <dir>` 먼저 실행")
    return json.loads(p.read_text())


def open_backend(cfg: dict) -> Backend:
    b = cfg["backend"]
    if b["type"] == "local":
        return LocalBackend(b["path"])
    raise SystemExit(f"지원하지 않는 backend: {b['type']} (S3/R2는 Phase 2)")


def open_chunker(cfg: dict) -> Chunker:
    c = cfg["chunker"]
    return make_chunker(c["name"], **c.get("params", {}))


def pointer_path(f: Path) -> Path:
    return f.with_name(f.name + POINTER_SUFFIX)


def find_pointers(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*" + POINTER_SUFFIX) if ".git" not in p.relative_to(root).parts
    )


def ensure_gitignored(root: Path, rel: str) -> None:
    gi = root / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    entry = "/" + rel
    if entry not in lines:
        with gi.open("a") as f:
            if lines and lines[-1] != "":
                f.write("\n")
            f.write(entry + "\n")


def cmd_init(args: argparse.Namespace, root: Path) -> int:
    cfg = {
        "backend": {"type": "local", "path": args.backend},
        "chunker": {"name": args.chunker, "params": {}},
    }
    (root / CONFIG).parent.mkdir(exist_ok=True)
    (root / CONFIG).write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"초기화: {root / CONFIG}")
    return 0


def cmd_add(args: argparse.Namespace, root: Path) -> int:
    cfg = load_config(root)
    backend, chunker = open_backend(cfg), open_chunker(cfg)
    for name in args.files:
        f = Path(name).resolve()
        rel = f.relative_to(root.resolve()).as_posix()
        r = store_file(f, backend, chunker)
        pointer_path(f).write_text(r.pointer.dumps())
        ensure_gitignored(root, rel)
        print(
            f"{rel}: {r.pointer.size:,} B, 청크 {r.chunks_total} "
            f"(신규 {r.chunks_new}, 재사용 {r.chunks_reused}, 업로드 {r.bytes_new:,} B)"
        )
    print(f"→ git add {' '.join(n + POINTER_SUFFIX for n in args.files)} .gitignore")
    return 0


def _targets(args: argparse.Namespace, root: Path) -> list[Path]:
    if getattr(args, "files", None):
        return [pointer_path(Path(n).resolve()) for n in args.files]
    return find_pointers(root)


def cmd_checkout(args: argparse.Namespace, root: Path) -> int:
    backend = open_backend(load_config(root))
    for pp in _targets(args, root):
        ptr = Pointer.loads(pp.read_text())
        dest = pp.with_name(pp.name.removesuffix(POINTER_SUFFIX))
        if dest.exists() and file_oid(dest) == ptr.oid:
            continue
        restore_file(ptr, backend, dest)
        print(f"복원: {dest.relative_to(root.resolve())}")
    return 0


def cmd_status(args: argparse.Namespace, root: Path) -> int:
    for pp in find_pointers(root):
        ptr = Pointer.loads(pp.read_text())
        dest = pp.with_name(pp.name.removesuffix(POINTER_SUFFIX))
        rel = dest.relative_to(root.resolve()).as_posix()
        if not dest.exists():
            state = "missing (checkout 필요)"
        elif dest.stat().st_size != ptr.size or file_oid(dest) != ptr.oid:
            state = "modified (add 필요)"
        else:
            state = "ok"
        print(f"{state:24} {rel}")
    return 0


def cmd_gc(args: argparse.Namespace, root: Path) -> int:
    backend = open_backend(load_config(root))
    live = [Pointer.loads(p.read_text()) for p in find_pointers(root)]
    dm, dc = gc(backend, live)
    print(f"삭제: 매니페스트 {dm}, 청크 {dc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bigstore", description="대용량 파일 청크 저장 + git 포인터")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--backend", required=True, help="로컬 오브젝트 디렉터리")
    i.add_argument("--chunker", choices=["fixed", "cdc"], default="fixed")
    a = sub.add_parser("add")
    a.add_argument("files", nargs="+")
    c = sub.add_parser("checkout")
    c.add_argument("files", nargs="*")
    sub.add_parser("status")
    sub.add_parser("gc")
    return p


COMMANDS = {"init": cmd_init, "add": cmd_add, "checkout": cmd_checkout, "status": cmd_status, "gc": cmd_gc}


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.cmd](args, (root or Path.cwd()).resolve())


if __name__ == "__main__":
    sys.exit(main())
