"""
Promote important facts from daily logs to long-term memory.
Scans daily logs, extracts candidates, formats for MEMORY.md.
"""

import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from datetime import date, timedelta


@dataclass
class PromoteCandidate:
    """A fact candidate for promotion to long-term memory."""
    text: str
    source_file: str
    line_num: int
    category: str  # decision, lesson, fact, contact, platform
    importance: float  # 0.0 - 1.0


# Patterns that indicate promotable content
PATTERNS = {
    "decision": [
        r'(?:decided|decision|вирішив|рішення)',
        r'(?:switched to|moved to|переїхав)',
        r'(?:will use|буду використовувати)',
        r'(?:approved|підтверджено|confirmed)',
    ],
    "lesson": [
        r'(?:урок|lesson|learned|зрозумів|insight)',
        r'(?:помилка|mistake|факап|fuckup|fix)',
        r'(?:не робити|don\'t|never again|більше не)',
        r'(?:краще|better to|should have)',
    ],
    "fact": [
        r'(?:LIVE|DONE|CLAIMED|PRODUCTION|DEPLOYED)',
        r'(?:підключ|connected|configured|встановлено|installed)',
        r'(?:створив|created|built|побудував|pushed)',
        r'(?:зареєструвався|registered|signed up)',
    ],
    "contact": [
        r'(?:бартер|deal|клієнт|client)',
        r'(?:контакт|contact|friend|партнер)',
    ],
    "platform": [
        r'(?:API key|token|creds|credentials)',
        r'(?:repo|repository|github\.com)',
        r'(?:inbox|email|agentmail)',
    ],
}


def score_line(line: str, category: str) -> float:
    """Score how important a line is (0.0-1.0)."""
    score = 0.3  # base for matching a pattern

    # Bold text = author emphasized it
    if '**' in line or '__' in line:
        score += 0.2

    # Emoji markers suggest importance
    if any(e in line for e in ['✅', '❌', '⚠️', '🔑', '💡', '🚀']):
        score += 0.15

    # Exclamation = emphasis
    if '!' in line:
        score += 0.05

    # URLs = concrete reference
    if 'http' in line:
        score += 0.1

    # Category weights
    weights = {
        "decision": 0.15,
        "lesson": 0.2,
        "fact": 0.1,
        "contact": 0.1,
        "platform": 0.05,
    }
    score += weights.get(category, 0)

    return min(score, 1.0)


def scan_file(filepath: Path) -> List[PromoteCandidate]:
    """Scan a file for promotable content."""
    candidates = []

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return candidates

    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # Clean bullet prefix
        text = stripped
        if text.startswith(('- ', '* ', '• ')):
            text = text[2:]

        for category, patterns in PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    importance = score_line(text, category)
                    candidates.append(PromoteCandidate(
                        text=text,
                        source_file=str(filepath),
                        line_num=i,
                        category=category,
                        importance=importance,
                    ))
                    break  # one match per category is enough
            # Don't break outer loop — same line can match multiple categories

    return candidates


def scan_recent(memory_dir: str, days: int = 7) -> List[PromoteCandidate]:
    """Scan recent daily logs for promotable content."""
    memory_path = Path(memory_dir) / "memory"
    if not memory_path.exists():
        memory_path = Path(memory_dir)

    candidates = []
    today = date.today()

    for i in range(days):
        day = today - timedelta(days=i)
        day_file = memory_path / f"{day.isoformat()}.md"
        if day_file.exists():
            candidates.extend(scan_file(day_file))

        # Also check inner-monologue
        mono_file = memory_path / "inner-monologue" / f"{day.isoformat()}.md"
        if mono_file.exists():
            candidates.extend(scan_file(mono_file))

    # Sort by importance descending, dedupe by text similarity
    candidates.sort(key=lambda c: c.importance, reverse=True)
    return dedupe(candidates)


def dedupe(candidates: List[PromoteCandidate], threshold: float = 0.7) -> List[PromoteCandidate]:
    """Remove near-duplicate candidates."""
    seen_texts = []
    result = []
    for c in candidates:
        # Simple word-overlap dedup
        words = set(c.text.lower().split())
        is_dupe = False
        for seen in seen_texts:
            overlap = len(words & seen) / max(len(words | seen), 1)
            if overlap > threshold:
                is_dupe = True
                break
        if not is_dupe:
            result.append(c)
            seen_texts.append(words)
    return result


def format_candidates(candidates: List[PromoteCandidate], top_n: int = 15) -> str:
    """Format candidates for display."""
    if not candidates:
        return "No promotion candidates found."

    lines = [f"📋 Promotion candidates ({len(candidates)} found, showing top {min(top_n, len(candidates))}):\n"]

    cat_emoji = {
        "decision": "🔑",
        "lesson": "💡",
        "fact": "📌",
        "contact": "🤝",
        "platform": "🔧",
    }

    for i, c in enumerate(candidates[:top_n], 1):
        emoji = cat_emoji.get(c.category, "•")
        score_bar = "█" * int(c.importance * 5) + "░" * (5 - int(c.importance * 5))
        source = Path(c.source_file).name
        lines.append(f"  {i:2d}. {emoji} [{score_bar}] {c.text[:100]}")
        lines.append(f"      {c.category} | {source}:{c.line_num}")

    lines.append(f"\nTo promote all to MEMORY.md: agent-memory promote --apply")
    return '\n'.join(lines)


def apply_promotion(candidates: List[PromoteCandidate], memory_file: str, top_n: int = 10) -> str:
    """Append top candidates to MEMORY.md."""
    memory_path = Path(memory_file)

    if not memory_path.exists():
        existing = ""
    else:
        existing = memory_path.read_text(encoding="utf-8")

    # Filter out candidates already in MEMORY.md (fuzzy)
    existing_lower = existing.lower()
    new_candidates = []
    for c in candidates[:top_n]:
        # Check if key words already present
        key_words = [w for w in c.text.lower().split() if len(w) > 4]
        overlap = sum(1 for w in key_words if w in existing_lower) / max(len(key_words), 1)
        if overlap < 0.6:
            new_candidates.append(c)

    if not new_candidates:
        return "All candidates already present in MEMORY.md."

    # Format new entries
    ts = date.today().isoformat()
    section = f"\n\n## Promoted {ts}\n"
    for c in new_candidates:
        cat_emoji = {"decision": "🔑", "lesson": "💡", "fact": "📌", "contact": "🤝", "platform": "🔧"}
        emoji = cat_emoji.get(c.category, "-")
        section += f"- {emoji} {c.text}\n"

    # Append
    with open(memory_path, 'a', encoding='utf-8') as f:
        f.write(section)

    return f"✅ Promoted {len(new_candidates)} items to {memory_path.name}"
