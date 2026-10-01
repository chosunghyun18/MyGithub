import random
from pathlib import Path

from bigstore.cli import main


def test_add_status_checkout_flow(tmp_path: Path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    objects = tmp_path / "objects"
    main(["init", "--backend", str(objects), "--chunker", "fixed"], root=repo)

    big = repo / "data" / "video.bin"
    big.parent.mkdir()
    data = random.Random(0).randbytes(300_000)
    big.write_bytes(data)

    main(["add", str(big)], root=repo)
    ptr = repo / "data" / "video.bin.bsp"
    assert ptr.read_text().startswith("version ")
    assert "/data/video.bin" in (repo / ".gitignore").read_text().splitlines()

    capsys.readouterr()
    main(["status"], root=repo)
    assert capsys.readouterr().out.startswith("ok")

    big.unlink()  # 새 머신에서 clone한 상황
    main(["status"], root=repo)
    assert "missing" in capsys.readouterr().out
    main(["checkout"], root=repo)
    assert big.read_bytes() == data

    big.write_bytes(b"changed")
    main(["status"], root=repo)
    assert "modified" in capsys.readouterr().out
