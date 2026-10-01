import pytest

from autocommit.message import FileStat, RuleBasedMessageGenerator, parse_numstat

gen = RuleBasedMessageGenerator()


def test_parse_numstat_with_status_and_binary():
    numstat = "12\t3\tdocs/guide.md\n5\t0\tdocs/new.md\n-\t-\timg/a.png\n"
    name_status = "M\tdocs/guide.md\nA\tdocs/new.md\nA\timg/a.png\n"
    stats = parse_numstat(numstat, name_status)
    assert stats == [
        FileStat("docs/guide.md", 12, 3, "M"),
        FileStat("docs/new.md", 5, 0, "A"),
        FileStat("img/a.png", 0, 0, "A", binary=True),
    ]


def test_single_file_message():
    msg = gen.generate([FileStat("notes/X.md", 12, 3, "M")])
    assert msg == "docs: update X.md (+12/-3)"


def test_single_added_and_deleted():
    assert gen.generate([FileStat("a.md", 4, 0, "A")]) == "docs: add a.md (+4/-0)"
    assert gen.generate([FileStat("a.md", 0, 9, "D")]) == "docs: remove a.md (+0/-9)"


def test_multi_file_same_verb_with_common_dir():
    msg = gen.generate(
        [FileStat("notes/daily/a.md", 10, 2), FileStat("notes/daily/b.md", 5, 1)]
    )
    header, _, body = msg.partition("\n\n")
    assert header == "docs: update 2 files in notes/daily/ (+15/-3)"
    assert body.splitlines() == [
        "- update notes/daily/a.md (+10/-2)",
        "- update notes/daily/b.md (+5/-1)",
    ]


def test_multi_file_mixed_verbs_no_common_dir():
    msg = gen.generate([FileStat("a.md", 1, 0, "M"), FileStat("b/c.md", 3, 0, "A")])
    assert msg.splitlines()[0] == "docs: update 1, add 1 files (+4/-0)"


def test_body_truncation_and_prefix():
    g = RuleBasedMessageGenerator(prefix="notes", max_body_lines=2)
    msg = g.generate([FileStat(f"f{i}.md", 1, 0) for i in range(5)])
    lines = msg.splitlines()
    assert lines[0].startswith("notes: update 5 files")
    assert lines[-1] == "- … 외 3개"


def test_empty_raises():
    with pytest.raises(ValueError):
        gen.generate([])
