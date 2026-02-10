#!/usr/bin/env python3
"""
agent-memory — Memory management toolkit for AI agents.

Usage:
    agent-memory search <query> [--dir=<dir>] [--limit=<n>]
    agent-memory semantic <query> [--dir=<dir>] [--limit=<n>] [--key=<openai_key>]
    agent-memory budget [--dir=<dir>] [--top=<n>] [--csv]
    agent-memory wake [--dir=<dir>]
    agent-memory compress [--dir=<dir>] [--week=<date>] [--save]
    agent-memory promote [--dir=<dir>] [--since=<days>] [--category=<cat>] [--top=<n>] [--apply] [--json]
    agent-memory stats [--dir=<dir>]
    agent-memory version

Categories for promote: decision, lesson, fact, contact, platform
"""

import sys
import os
from pathlib import Path

VERSION = "0.2.0"


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
    from .budget import analyze_directory, format_budget, format_csv
    
    memory_dir = args.get("dir") or find_memory_dir()
    top_n = int(args.get("top", 20))
    
    stats = analyze_directory(memory_dir)
    
    if args.get("csv"):
        print(format_csv(stats))
    else:
        print(format_budget(stats, top_n))
    return 0


def cmd_wake(args):
    """Estimate wake sequence cost."""
    from .budget import wake_cost
    
    memory_dir = args.get("dir") or find_memory_dir()
    print(wake_cost(memory_dir))
    return 0


def cmd_promote(args):
    """Scan daily logs for facts to promote to MEMORY.md."""
    from .promote import scan_recent, format_candidates, format_json, apply_promotion
    
    memory_dir = args.get("dir") or find_memory_dir()
    days = int(args.get("since", args.get("days", 7)))
    top_n = int(args.get("top", 15))
    category = args.get("category")
    
    candidates = scan_recent(memory_dir, days=days, category=category)
    
    if args.get("apply"):
        memory_file = os.path.join(memory_dir, "MEMORY.md")
        print(apply_promotion(candidates, memory_file, top_n=top_n))
    elif args.get("json"):
        print(format_json(candidates, top_n=top_n))
    else:
        print(format_candidates(candidates, top_n=top_n))
    
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
    if args.get("save") or "--save" in sys.argv:
        outdir = os.path.join(memory_subdir, "summaries")
        os.makedirs(outdir, exist_ok=True)
        from datetime import timedelta
        d = week_date or (date.today() - timedelta(weeks=1))
        week_num = d.isocalendar()[1]
        year = d.isocalendar()[0]
        outfile = os.path.join(outdir, f"{year}-W{week_num:02d}.md")
        with open(outfile, 'w') as f:
            f.write(result)
        print(f"\n💾 Saved to {outfile}")
    
    return 0


def cmd_semantic(args):
    """Semantic search using embeddings."""
    from .semantic import SemanticIndex
    
    query = " ".join(args.get("query", []))
    if not query:
        print("Usage: agent-memory semantic <query> [--dir=<dir>] [--key=<openai_key>]")
        return 1
    
    memory_dir = args.get("dir") or find_memory_dir()
    limit = int(args.get("limit", 5))
    
    # Get OpenAI key
    openai_key = args.get("key") or os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        # Try to read from OpenClaw config
        try:
            import json
            profiles = json.load(open(os.path.expanduser(
                "~/.openclaw/agents/main/agent/auth-profiles.json")))
            openai_key = profiles["profiles"]["openai:default"]["token"]
        except Exception:
            print("Error: No OpenAI API key. Set OPENAI_API_KEY or pass --key=")
            return 1
    
    index_path = os.path.join(memory_dir, ".memory-index.json")
    
    # Try to load existing index
    idx = None
    if os.path.exists(index_path):
        try:
            idx = SemanticIndex.load(index_path, openai_key=openai_key)
            print("📂 Loaded existing index, rebuilding incrementally...")
        except Exception:
            pass
    
    if idx is None:
        idx = SemanticIndex(memory_dir, openai_key=openai_key)
    
    idx.build()
    idx.save(index_path)
    
    stats = idx.stats()
    print(f"🧠 Index: {stats['chunks']} chunks from {stats['files']} files (embed cost: {stats['estimated_embed_cost']})\n")
    
    results = idx.search(query, limit=limit)
    
    if not results:
        print(f"No results for '{query}'")
        return 0
    
    print(f"🔮 Semantic results for '{query}':\n")
    for r in results:
        pct = int(r.similarity * 100)
        bar = "●" * (pct // 20) + "○" * (5 - pct // 20)
        print(f"  [{bar}] {pct}% — {r.file}")
        preview = r.chunk_text[:200].replace('\n', ' ')
        print(f"    {preview}...")
        print()
    
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
    
    if cmd == "version":
        print(f"agent-memory {VERSION}")
        return 0
    
    commands = {
        "search": cmd_search,
        "semantic": cmd_semantic,
        "budget": cmd_budget,
        "wake": cmd_wake,
        "compress": cmd_compress,
        "promote": cmd_promote,
        "stats": cmd_stats,
    }
    
    if cmd == "help" or cmd not in commands:
        print(__doc__)
        print(f"  version {VERSION}")
        return 0
    
    return commands[cmd](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
