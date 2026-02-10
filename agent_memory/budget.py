"""
Token budget analysis for memory files.
Know how much each file costs before reading it.
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class FileStats:
    """Token/size stats for a single file."""
    path: str
    bytes: int
    lines: int
    estimated_tokens: int
    
    @property
    def bar(self) -> str:
        """Visual bar representation (max 10 blocks)."""
        max_tokens = 5000  # scale reference
        filled = min(10, int(self.estimated_tokens / max_tokens * 10))
        return "█" * filled + "░" * (10 - filled)


def estimate_tokens(text: str) -> int:
    """
    Estimate token count without tiktoken.
    Uses the ~4 chars per token heuristic for English/mixed text.
    For CJK/Cyrillic, adjusts to ~2-3 chars per token.
    """
    # Count CJK characters (higher token density)
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', text))
    # Count Cyrillic (slightly higher than English)
    cyrillic = len(re.findall(r'[\u0400-\u04ff]', text))
    # Rest is roughly English/code/symbols
    other = len(text) - cjk - cyrillic
    
    tokens = (cjk * 0.7) + (cyrillic * 0.5) + (other / 4.0)
    return max(1, int(tokens))


def analyze_directory(memory_dir: str, extensions: tuple = (".md", ".json", ".txt")) -> List[FileStats]:
    """Analyze all memory files and return token estimates."""
    memory_path = Path(memory_dir)
    results = []
    
    for root, _, files in os.walk(memory_path):
        for fname in sorted(files):
            if not any(fname.endswith(ext) for ext in extensions):
                continue
            
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, memory_dir)
            
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                results.append(FileStats(
                    path=rel_path,
                    bytes=len(content.encode('utf-8')),
                    lines=content.count('\n') + 1,
                    estimated_tokens=estimate_tokens(content),
                ))
            except (UnicodeDecodeError, PermissionError):
                continue
    
    results.sort(key=lambda x: x.estimated_tokens, reverse=True)
    return results


def format_budget(stats: List[FileStats], top_n: int = 20) -> str:
    """Format budget analysis as a readable table."""
    total_tokens = sum(s.estimated_tokens for s in stats)
    lines = [
        f"📊 Memory Budget Analysis",
        f"   {len(stats)} files | ~{total_tokens:,} estimated tokens",
        f"{'─' * 65}",
    ]
    
    for s in stats[:top_n]:
        pct = (s.estimated_tokens / total_tokens * 100) if total_tokens > 0 else 0
        lines.append(
            f"  {s.path:<40} {s.estimated_tokens:>6,} tok  {s.bar}  {pct:4.1f}%"
        )
    
    if len(stats) > top_n:
        rest = sum(s.estimated_tokens for s in stats[top_n:])
        lines.append(f"  ... +{len(stats) - top_n} more files ({rest:,} tokens)")
    
    lines.append(f"{'─' * 65}")
    lines.append(f"  TOTAL: ~{total_tokens:,} tokens")
    
    return "\n".join(lines)


def format_csv(stats: List[FileStats]) -> str:
    """Format budget analysis as CSV (path,bytes,lines,tokens,pct)."""
    total_tokens = sum(s.estimated_tokens for s in stats)
    lines = ["path,bytes,lines,tokens,pct"]
    for s in stats:
        pct = (s.estimated_tokens / total_tokens * 100) if total_tokens > 0 else 0
        lines.append(f"{s.path},{s.bytes},{s.lines},{s.estimated_tokens},{pct:.1f}")
    return "\n".join(lines)


def format_csv(stats: List[FileStats]) -> str:
    """Format budget analysis as CSV."""
    total_tokens = sum(s.estimated_tokens for s in stats)
    lines = ["path,bytes,lines,tokens,pct"]
    for s in stats:
        pct = (s.estimated_tokens / total_tokens * 100) if total_tokens > 0 else 0
        lines.append(f"{s.path},{s.bytes},{s.lines},{s.estimated_tokens},{pct:.1f}")
    lines.append(f"TOTAL,{sum(s.bytes for s in stats)},{sum(s.lines for s in stats)},{total_tokens},100.0")
    return "\n".join(lines)


def wake_cost(memory_dir: str, wake_files: Optional[List[str]] = None) -> str:
    """
    Estimate the token cost of a typical wake sequence.
    If wake_files not specified, uses common defaults.
    """
    if wake_files is None:
        wake_files = [
            "MEMORY.md",
            "heartbeat-state.json",
        ]
        # Add today's and yesterday's logs
        from datetime import date, timedelta
        today = date.today()
        yesterday = today - timedelta(days=1)
        wake_files.extend([
            f"memory/{today.isoformat()}.md",
            f"memory/{yesterday.isoformat()}.md",
        ])
    
    memory_path = Path(memory_dir)
    total = 0
    lines = ["🌅 Wake Sequence Cost:"]
    
    for wf in wake_files:
        fpath = memory_path / wf
        if fpath.exists():
            with open(fpath, 'r') as f:
                content = f.read()
            tokens = estimate_tokens(content)
            total += tokens
            lines.append(f"  ✅ {wf:<35} ~{tokens:,} tokens")
        else:
            lines.append(f"  ❌ {wf:<35} (not found)")
    
    lines.append(f"  {'─' * 45}")
    lines.append(f"  Total wake cost: ~{total:,} tokens")
    
    return "\n".join(lines)
