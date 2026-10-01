import subprocess
from pathlib import Path

from autocommit.gitops import commit_paths
from autocommit.watcher import diff_snapshots, take_snapshot


def test_diff_snapshots():
    before = {"a.md": (1.0, 10), "b.md": (1.0, 10), "gone.md": (1.0, 1)}
    after = {"a.md": (1.0, 10), "b.md": (2.0, 12), "new.md": (3.0, 5)}
    assert diff_snapshots(before, after) == ["b.md", "gone.md", "new.md"]


def test_take_snapshot_filters(tmp_path: Path):
    (tmp_path / "a.md").write_text("x")
    (tmp_path / "b.py").write_text("x")
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "c.md").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "d.md").write_text("x")
    assert sorted(take_snapshot(tmp_path)) == ["a.md", "sub/d.md"]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def test_commit_paths_end_to_end(tmp_path: Path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.md").write_text("line1\nline2\n")
    (tmp_path / "other.md").write_text("staged elsewhere\n")
    _git(tmp_path, "add", "other.md")  # 배치 밖의 stage는 커밋에 섞이지 않아야 함

    msg = commit_paths(tmp_path, ["a.md"])
    assert msg == "docs: add a.md (+2/-0)"
    assert _git(tmp_path, "log", "-1", "--format=%s").strip() == msg
    assert _git(tmp_path, "show", "--name-only", "--format=").split() == ["a.md"]

    # 변경 없으면 커밋하지 않음
    assert commit_paths(tmp_path, ["a.md"]) is None

    (tmp_path / "a.md").write_text("line1\nchanged\nline3\n")
    assert commit_paths(tmp_path, ["a.md"]) == "docs: update a.md (+2/-1)"

    (tmp_path / "a.md").unlink()
    assert commit_paths(tmp_path, ["a.md"]) == "docs: remove a.md (+0/-3)"
