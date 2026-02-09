"""
Inverted index for memory files.
Search across all .md and .json files without reading everything.
"""

import os
import re
import json
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SearchResult:
    """A single search hit."""
    file: str
    line_num: int
    line_text: str
    score: float = 0.0
    context: List[str] = field(default_factory=list)


class MemoryIndex:
    """
    Simple inverted index over memory files.
    
    Usage:
        idx = MemoryIndex("/path/to/memory")
        idx.build()
        results = idx.search("moltbook credentials")
    """
    
    def __init__(self, memory_dir: str, extensions: tuple = (".md", ".json", ".txt")):
        self.memory_dir = Path(memory_dir)
        self.extensions = extensions
        # token -> [(file, line_num, line_text)]
        self.inverted: dict[str, list] = defaultdict(list)
        self.file_count = 0
        self.token_count = 0
    
    def _tokenize(self, text: str) -> List[str]:
        """Split text into searchable tokens."""
        text = text.lower()
        # Remove markdown formatting
        text = re.sub(r'[#*_`\[\](){}|>~]', ' ', text)
        # Split on non-alphanumeric (keep hyphens in words)
        tokens = re.findall(r'[a-z0-9][\w\-]*[a-z0-9]|[a-z0-9]', text)
        return tokens
    
    def build(self) -> 'MemoryIndex':
        """Build the index from all files in memory_dir."""
        self.inverted.clear()
        self.file_count = 0
        self.token_count = 0
        
        for root, _, files in os.walk(self.memory_dir):
            for fname in files:
                if not any(fname.endswith(ext) for ext in self.extensions):
                    continue
                
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, self.memory_dir)
                self.file_count += 1
                
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            line = line.rstrip()
                            if not line:
                                continue
                            tokens = self._tokenize(line)
                            self.token_count += len(tokens)
                            for token in set(tokens):  # dedupe per line
                                self.inverted[token].append((rel_path, line_num, line))
                except (UnicodeDecodeError, PermissionError):
                    continue
        
        return self
    
    def search(self, query: str, limit: int = 10, context_lines: int = 1) -> List[SearchResult]:
        """
        Search the index for a query.
        Returns results ranked by number of matching tokens.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        
        # Score: (file, line_num) -> (score, line_text)
        hits: dict[tuple, dict] = defaultdict(lambda: {"score": 0, "text": ""})
        
        for token in query_tokens:
            for rel_path, line_num, line_text in self.inverted.get(token, []):
                key = (rel_path, line_num)
                hits[key]["score"] += 1
                hits[key]["text"] = line_text
        
        # Sort by score descending
        ranked = sorted(hits.items(), key=lambda x: x[1]["score"], reverse=True)[:limit]
        
        results = []
        for (rel_path, line_num), data in ranked:
            result = SearchResult(
                file=rel_path,
                line_num=line_num,
                line_text=data["text"],
                score=data["score"] / len(query_tokens),  # normalize to 0-1
            )
            
            # Add context lines
            if context_lines > 0:
                result.context = self._get_context(rel_path, line_num, context_lines)
            
            results.append(result)
        
        return results
    
    def _get_context(self, rel_path: str, line_num: int, n: int) -> List[str]:
        """Get n lines before and after the match."""
        fpath = self.memory_dir / rel_path
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            start = max(0, line_num - n - 1)
            end = min(len(lines), line_num + n)
            return [l.rstrip() for l in lines[start:end]]
        except Exception:
            return []
    
    def stats(self) -> dict:
        """Return index statistics."""
        return {
            "files_indexed": self.file_count,
            "unique_tokens": len(self.inverted),
            "total_token_refs": self.token_count,
            "index_size_kb": sum(
                len(entries) for entries in self.inverted.values()
            ) * 50 / 1024  # rough estimate
        }
    
    def save(self, path: str):
        """Save index to JSON for reuse."""
        data = {
            "memory_dir": str(self.memory_dir),
            "file_count": self.file_count,
            "token_count": self.token_count,
            "inverted": {
                k: [(f, ln, t) for f, ln, t in v]
                for k, v in self.inverted.items()
            }
        }
        with open(path, 'w') as f:
            json.dump(data, f)
    
    @classmethod
    def load(cls, path: str) -> 'MemoryIndex':
        """Load a previously saved index."""
        with open(path, 'r') as f:
            data = json.load(f)
        
        idx = cls(data["memory_dir"])
        idx.file_count = data["file_count"]
        idx.token_count = data["token_count"]
        idx.inverted = defaultdict(list, {
            k: [(f, ln, t) for f, ln, t in v]
            for k, v in data["inverted"].items()
        })
        return idx
