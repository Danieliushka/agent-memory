#!/usr/bin/env python3
"""
agent-memory CLI — Memory management for AI agents.

Usage:
    agent-memory search <query> [--dir=<dir>] [--limit=<n>]
    agent-memory budget [--dir=<dir>] [--top=<n>]
    agent-memory wake [--dir=<dir>]
    agent-memory compress [--dir=<dir>] [--week=<date>]
    agent-memory stats [--dir=<dir>]
"""

import sys
import os
from pathlib import Path


def find_memory_dir() -> str:
    """Find the memory directory (workspace or current dir)."""
    candidates = [
        os.environ.get("AGENT_MEMORY_DIR", ""),
        os.path.expanduser("~/.openclaw/workspace"),
        os.getcwd(),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return os.getcwd()


def cmd_search(args):
    """Search memory files."""
    from .index import MemoryIndex
    
    query = " ".join(args.get("query", []))
    if not query:
        print("Usage: agent-memory search <query>")
        return 1
    
    memory_dir = args.get("dir") or find_memory_dir()
    limit = int(args.get("limit", 10))
    
    idx = MemoryIndex(memory_dir)
    idx.build()
    results = idx.search(query, limit=limit)
    
    if not results:
        print(f"No results for '{query}'")
        return 0
    
    print(f"🔍 Results for '{query}' ({len(results)} hits):\n")
    for r in results:
        score_bar = "●" * int(r.score * 5) + "○" * (5 - int(r.score * 5))
        print(f"  [{score_bar}] {r.file}:{r.line_num}")
        print(f"    {r.line_text[:120]}")
        print()
    
    return 0


def cmd_budget(args):
    """Show token budget analysis."""
    from .budget import analyze_directory, format_budget
    
    memory_dir = args.get("dir") or find_memory_dir()
    top_n = int(args.get("top", 20))
    
    stats = analyze_directory(memory_dir)
    print(format_budget(stats, top_n))
    return 0


def cmd_wake(args):
    """Estimate wake sequence cost."""
    from .budget import wake_cost
    
    memory_dir = args.get("dir") or find_memory_dir()
    print(wake_cost(memory_dir))
    return 0


def cmd_compress(args):
    """Compress weekly logs."""
    from .compress import compress_week
    from datetime import date
    
    memory_dir = args.get("dir") or find_memory_dir()
    memory_subdir = os.path.join(memory_dir, "memory")
    
    if args.get("week"):
        week_date = date.fromisoformat(args["week"])
    else:
        week_date = None
    
    result = compress_week(memory_subdir, week_date)
    print(result)
    
    # Optionally save
    if "--save" in sys.argv:
        outdir = os.path.join(memory_subdir, "summaries")
        os.makedirs(outdir, exist_ok=True)
        # Use week number for filename
        from datetime import timedelta
        d = week_date or (date.today() - timedelta(weeks=1))
        week_num = d.isocalendar()[1]
        year = d.isocalendar()[0]
        outfile = os.path.join(outdir, f"{year}-W{week_num:02d}.md")
        with open(outfile, 'w') as f:
            f.write(result)
        print(f"\n💾 Saved to {outfile}")
    
    return 0


def cmd_stats(args):
    """Show index statistics."""
    from .index import MemoryIndex
    
    memory_dir = args.get("dir") or find_memory_dir()
    idx = MemoryIndex(memory_dir)
    idx.build()
    stats = idx.stats()
    
    print(f"📊 Index Statistics:")
    print(f"   Files indexed:    {stats['files_indexed']}")
    print(f"   Unique tokens:    {stats['unique_tokens']:,}")
    print(f"   Total references: {stats['total_token_refs']:,}")
    print(f"   Index size:       ~{stats['index_size_kb']:.1f} KB")
    return 0


def parse_args(argv):
    """Simple arg parser (no dependencies)."""
    args = {"query": []}
    
    if len(argv) < 2:
        return {"command": "help"}
    
    args["command"] = argv[1]
    
    i = 2
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--"):
            key = arg.lstrip("-").split("=")[0]
            if "=" in arg:
                args[key] = arg.split("=", 1)[1]
            elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                args[key] = argv[i + 1]
                i += 1
            else:
                args[key] = True
        else:
            args["query"].append(arg)
        i += 1
    
    return args


def main():
    args = parse_args(sys.argv)
    cmd = args.get("command", "help")
    
    commands = {
        "search": cmd_search,
        "budget": cmd_budget,
        "wake": cmd_wake,
        "compress": cmd_compress,
        "stats": cmd_stats,
    }
    
    if cmd == "help" or cmd not in commands:
        print(__doc__)
        return 0
    
    return commands[cmd](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
