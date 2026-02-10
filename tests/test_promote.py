"""Tests for promote module."""
import tempfile
import os
from pathlib import Path
from agent_memory.promote import (
    score_line, scan_file, dedupe, format_candidates, format_json,
    find_section, check_already_present, PromoteCandidate, SECTION_MAP,
)


def test_score_line_returns_float():
    score = score_line("Some text about a decision", "decision")
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_score_line_bold_increases():
    plain = score_line("built a thing", "fact")
    bold = score_line("**built a thing**", "fact")
    assert bold > plain


def test_score_line_emoji_increases():
    plain = score_line("something happened", "fact")
    emoji = score_line("something happened ✅", "fact")
    assert emoji > plain


def test_scan_file_finds_patterns():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("# Day Log\n")
        f.write("- вирішив перейти на новий фреймворк\n")
        f.write("- урок: не довіряй кешу\n")
        f.write("- побудував agent-memory v0.2\n")
        f.write("- написав email клієнту\n")
        f.write("- some random text without keywords\n")
        f.name
    try:
        candidates = scan_file(Path(f.name))
        assert len(candidates) >= 3
        categories = {c.category for c in candidates}
        assert "decision" in categories
        assert "lesson" in categories
        assert "fact" in categories
    finally:
        os.unlink(f.name)


def test_dedupe_removes_duplicates():
    candidates = [
        PromoteCandidate("built a new thing today", "a.md", 1, "fact", 0.5),
        PromoteCandidate("built a new thing today with extras", "b.md", 2, "fact", 0.4),
        PromoteCandidate("completely different text about lessons", "c.md", 3, "lesson", 0.6),
    ]
    result = dedupe(candidates)
    assert len(result) == 2  # first and third survive


def test_format_candidates_structure():
    candidates = [
        PromoteCandidate("test fact", "test.md", 1, "fact", 0.7),
        PromoteCandidate("test lesson", "test.md", 5, "lesson", 0.5),
    ]
    output = format_candidates(candidates)
    assert "📋" in output
    assert "Promotion candidates" in output
    assert "📌" in output  # fact emoji
    assert "💡" in output  # lesson emoji
    assert "test fact" in output


def test_format_json_valid():
    import json
    candidates = [
        PromoteCandidate("test item", "test.md", 1, "fact", 0.7),
    ]
    output = format_json(candidates)
    parsed = json.loads(output)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["text"] == "test item"
    assert parsed[0]["category"] == "fact"
    assert parsed[0]["importance"] == 0.7


def test_find_section_maps_correctly():
    content = "# Memory\n\n## Уроки\n- lesson 1\n\n## Платформи\n- platform 1\n"
    assert find_section(content, "lesson") is not None
    assert find_section(content, "platform") is not None
    assert find_section(content, "contact") is None  # no contact section


def test_check_already_present():
    existing = "- урок: не довіряй кешу ніколи"
    assert check_already_present("не довіряй кешу ніколи", existing) is True
    assert check_already_present("completely new unrelated text here", existing) is False
