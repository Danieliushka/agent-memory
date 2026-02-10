"""Tests for budget module."""
import tempfile
import os
from agent_memory.budget import estimate_tokens, analyze_directory, format_csv, FileStats


def test_estimate_tokens_positive():
    assert estimate_tokens("hello world") > 0
    assert estimate_tokens("") >= 1


def test_estimate_tokens_cyrillic_higher():
    # Cyrillic should estimate more tokens per char than English
    en = estimate_tokens("a" * 100)
    cy = estimate_tokens("а" * 100)  # Cyrillic а
    assert cy > en


def test_analyze_directory():
    with tempfile.TemporaryDirectory() as d:
        # Create test files
        with open(os.path.join(d, "test.md"), 'w') as f:
            f.write("# Test\nSome content here\n- bullet 1\n- bullet 2\n")
        with open(os.path.join(d, "data.json"), 'w') as f:
            f.write('{"key": "value"}')
        with open(os.path.join(d, "skip.py"), 'w') as f:
            f.write("print('hello')")  # should be skipped (not md/json/txt)
        
        stats = analyze_directory(d)
        assert len(stats) == 2  # only .md and .json
        assert all(isinstance(s, FileStats) for s in stats)
        assert all(s.estimated_tokens > 0 for s in stats)


def test_format_csv_valid():
    stats = [
        FileStats("test.md", 100, 10, 25),
        FileStats("data.json", 50, 5, 12),
    ]
    output = format_csv(stats)
    lines = output.strip().split('\n')
    assert lines[0] == "path,bytes,lines,tokens,pct"
    assert len(lines) == 4  # header + 2 files + TOTAL
    assert "TOTAL" in lines[-1]
    
    # Check values parse correctly
    parts = lines[1].split(',')
    assert parts[0] == "test.md"
    assert int(parts[3]) == 25


def test_format_csv_empty():
    output = format_csv([])
    lines = output.strip().split('\n')
    assert lines[0] == "path,bytes,lines,tokens,pct"
    assert "TOTAL" in lines[-1]
