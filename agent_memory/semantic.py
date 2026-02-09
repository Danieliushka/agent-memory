"""
Semantic search for agent memory files.
Uses OpenAI embeddings for meaning-based retrieval.

Cost: ~$0.0004 per full index of 20k tokens (text-embedding-3-small).
"""

import os
import json
import math
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class SemanticResult:
    """A semantic search hit."""
    file: str
    chunk_text: str
    similarity: float
    chunk_id: int = 0


class SemanticIndex:
    """
    Semantic search over memory files using OpenAI embeddings.
    
    Chunks files into paragraphs, embeds each chunk,
    and finds the most semantically similar chunks to a query.
    
    Usage:
        idx = SemanticIndex("/path/to/memory", openai_key="sk-...")
        idx.build()           # Embeds all files (~$0.001)
        idx.save("index.json") # Persist for reuse
        
        results = idx.search("how do I manage context compression?")
    """
    
    MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536
    CHUNK_SIZE = 500  # chars per chunk (roughly 125 tokens)
    CHUNK_OVERLAP = 50
    
    def __init__(self, memory_dir: str, openai_key: str = "",
                 extensions: tuple = (".md", ".json", ".txt")):
        self.memory_dir = Path(memory_dir)
        self.extensions = extensions
        self.openai_key = openai_key or os.environ.get("OPENAI_API_KEY", "")
        
        # Stored data
        self.chunks: List[dict] = []  # [{file, text, hash}]
        self.embeddings: List[List[float]] = []  # parallel to chunks
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.openai_key)
        return self._client
    
    def _chunk_file(self, content: str, rel_path: str) -> List[dict]:
        """Split file content into overlapping chunks."""
        chunks = []
        
        # Split by double newlines (paragraphs) first
        paragraphs = content.split('\n\n')
        
        current_chunk = ""
        chunk_id = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if len(current_chunk) + len(para) > self.CHUNK_SIZE and current_chunk:
                chunks.append({
                    "file": rel_path,
                    "text": current_chunk.strip(),
                    "hash": hashlib.md5(current_chunk.encode()).hexdigest()[:12],
                    "chunk_id": chunk_id,
                })
                chunk_id += 1
                # Keep overlap
                words = current_chunk.split()
                overlap_words = words[-10:] if len(words) > 10 else []
                current_chunk = " ".join(overlap_words) + "\n\n" + para
            else:
                current_chunk += "\n\n" + para if current_chunk else para
        
        # Last chunk
        if current_chunk.strip():
            chunks.append({
                "file": rel_path,
                "text": current_chunk.strip(),
                "hash": hashlib.md5(current_chunk.encode()).hexdigest()[:12],
                "chunk_id": chunk_id,
            })
        
        return chunks
    
    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for a batch of texts. Auto-splits if too large."""
        if not texts:
            return []
        
        # Split into sub-batches that stay under token limits
        # ~4 chars per token, max 250k tokens per request
        MAX_CHARS_PER_BATCH = 800_000  # ~200k tokens, safe margin
        
        all_embeddings = []
        batch = []
        batch_chars = 0
        
        for text in texts:
            if batch and batch_chars + len(text) > MAX_CHARS_PER_BATCH:
                # Send current batch
                resp = self.client.embeddings.create(model=self.MODEL, input=batch)
                all_embeddings.extend([d.embedding for d in resp.data])
                batch = []
                batch_chars = 0
            
            batch.append(text)
            batch_chars += len(text)
        
        # Send remaining
        if batch:
            resp = self.client.embeddings.create(model=self.MODEL, input=batch)
            all_embeddings.extend([d.embedding for d in resp.data])
        
        return all_embeddings
    
    def build(self, batch_size: int = 50) -> 'SemanticIndex':
        """
        Build semantic index from all files.
        Skips chunks that haven't changed (by hash).
        """
        old_hashes = {c["hash"]: i for i, c in enumerate(self.chunks)}
        new_chunks = []
        
        for root, _, files in os.walk(self.memory_dir):
            for fname in sorted(files):
                if not any(fname.endswith(ext) for ext in self.extensions):
                    continue
                
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, self.memory_dir)
                
                # Skip hidden files, index files, and very large files
                if fname.startswith('.') or fname == '.memory-index.json':
                    continue
                if os.path.getsize(fpath) > 100_000:  # skip files >100KB
                    continue
                
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    new_chunks.extend(self._chunk_file(content, rel_path))
                except (UnicodeDecodeError, PermissionError):
                    continue
        
        # Find chunks that need embedding (new or changed)
        to_embed = []
        to_embed_indices = []
        reused = 0
        
        final_chunks = []
        final_embeddings = []
        
        for chunk in new_chunks:
            if chunk["hash"] in old_hashes:
                # Reuse existing embedding
                old_idx = old_hashes[chunk["hash"]]
                final_chunks.append(chunk)
                final_embeddings.append(self.embeddings[old_idx])
                reused += 1
            else:
                final_chunks.append(chunk)
                to_embed.append(chunk["text"])
                to_embed_indices.append(len(final_chunks) - 1)
        
        # Embed new chunks in batches
        if to_embed:
            for i in range(0, len(to_embed), batch_size):
                batch = to_embed[i:i + batch_size]
                batch_embeddings = self._embed_batch(batch)
                
                for j, emb in enumerate(batch_embeddings):
                    idx = to_embed_indices[i + j]
                    if idx < len(final_embeddings):
                        final_embeddings[idx] = emb
                    else:
                        final_embeddings.append(emb)
        
        self.chunks = final_chunks
        self.embeddings = final_embeddings
        
        return self
    
    def search(self, query: str, limit: int = 5) -> List[SemanticResult]:
        """Find the most semantically similar chunks to a query."""
        if not self.chunks:
            return []
        
        # Embed query
        query_emb = self._embed_batch([query])[0]
        
        # Cosine similarity with all chunks
        scores = []
        for i, chunk_emb in enumerate(self.embeddings):
            sim = self._cosine_similarity(query_emb, chunk_emb)
            scores.append((i, sim))
        
        # Sort by similarity
        scores.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        seen_files = set()
        
        for idx, sim in scores[:limit * 2]:  # oversample then dedup
            chunk = self.chunks[idx]
            
            results.append(SemanticResult(
                file=chunk["file"],
                chunk_text=chunk["text"],
                similarity=sim,
                chunk_id=chunk["chunk_id"],
            ))
            
            if len(results) >= limit:
                break
        
        return results
    
    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    def save(self, path: str):
        """Save index to file for reuse between sessions."""
        data = {
            "version": 1,
            "model": self.MODEL,
            "memory_dir": str(self.memory_dir),
            "chunks": self.chunks,
            "embeddings": self.embeddings,
        }
        with open(path, 'w') as f:
            json.dump(data, f)
    
    @classmethod
    def load(cls, path: str, openai_key: str = "") -> 'SemanticIndex':
        """Load a previously saved index."""
        with open(path, 'r') as f:
            data = json.load(f)
        
        idx = cls(data["memory_dir"], openai_key=openai_key)
        idx.chunks = data["chunks"]
        idx.embeddings = data["embeddings"]
        return idx
    
    def stats(self) -> dict:
        """Index statistics."""
        files = set(c["file"] for c in self.chunks)
        total_chars = sum(len(c["text"]) for c in self.chunks)
        return {
            "files": len(files),
            "chunks": len(self.chunks),
            "total_chars": total_chars,
            "estimated_embed_cost": f"${total_chars / 4 / 1_000_000 * 0.02:.6f}",
        }
