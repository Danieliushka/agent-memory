"""
Promote important facts from daily logs to long-term memory.
v0.2: Section-aware promotion, category filters, JSON output.
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict
from datetime import date, timedelta


@dataclass
class PromoteCandidate:
    """A fact candidate for promotion to long-term memory."""
    text: str
    source_file: str
    line_num: int
    category: str  # decision, lesson, fact, contact, platform
    importance: float  # 0.0 - 1.0


# Section mapping: category → MEMORY.md section header
SECTION_MAP: Dict[str, List[str]] = {
    "lesson": ["## Уроки", "## Lessons", "## Уроки (нові)"],
    "decision": ["## Ключові рішення", "## Key Decisions", "## Рішення"],
    "fact": ["## Ключове", "## Key Facts", "## Факти"],
    "contact": ["## Контакти", "## Contacts", "## Мережа"],
    "platform": ["## Платформи", "## Platforms", "## Інфра"],
}

# Patterns that indicate promotable content
PATTERNS = {
    "decision": [
        r'(?:decided|decision|вирішив|рішення)',
        r'(?:switched to|moved to|переїхав|перейшов)',
        r'(?:will use|буду використовувати)',
        r'(?:approved|підтверджено|confirmed)',
        r'(?:abandoned|відмовились|забили|killed)',
    ],
    "lesson": [
        r'(?:урок|lesson|learned|зрозумів|insight)',
        r'(?:помилка|mistake|факап|fuckup|fix)',
        r'(?:не робити|don\'t|never again|більше не)',
        r'(?:краще|better to|should have)',
        r'(?:важливо|important|critical|ключов)',
    ],
    "fact": [
        r'(?:LIVE|DONE|CLAIMED|PRODUCTION|DEPLOYED)',
        r'(?:підключ|connected|configured|встановлено|installed)',
        r'(?:створив|created|built|побудував|pushed)',
        r'(?:зареєструвався|registered|signed up)',
        r'(?:v\d+\.\d+|version \d)',
    ],
    "contact": [
        r'(?:бартер|deal|клієнт|client)',
        r'(?:контакт|contact|friend|партнер)',
        r'(?:collaboration|collab|співпраця)',
        r'(?:replied|відповів|wrote to|написав)',
    ],
    "platform": [
        r'(?:API key|token|creds|credentials)',
        r'(?:repo|repository|github\.com)',
        r'(?:inbox|email|agentmail)',
        r'(?:wallet|гаманець|address)',
        r'(?:cron|service|systemd|deploy)',
    ],
}


def score_line(line: str, category: str) -> float:
    """Score how important a line is (0.0-1.0)."""
    score = 0.3  # base for matching a pattern

    # Bold text = author emphasized it
    if '**' in line or '__' in line:
        score += 0.2

    # Emoji markers suggest importance
    if any(e in line for e in ['✅', '❌', '⚠️', '🔑', '💡', '🚀', '🔥']):
        score += 0.15

    # Exclamation = emphasis
    if '!' in line:
        score += 0.05

    # URLs = concrete reference
    if 'http' in line:
        score += 0.1

    # ALL CAPS words (excluding common headers) = emphasis
    caps_words = re.findall(r'\b[A-Z]{3,}\b', line)
    caps_words = [w for w in caps_words if w not in ('API', 'URL', 'SSH', 'CLI', 'SDK', 'HTTP', 'UTC', 'DM')]
    if caps_words:
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

    return candidates


def scan_recent(memory_dir: str, days: int = 7, category: Optional[str] = None) -> List[PromoteCandidate]:
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

    # Filter by category if specified
    if category:
        candidates = [c for c in candidates if c.category == category]

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


def format_json(candidates: List[PromoteCandidate], top_n: int = 15) -> str:
    """Format candidates as JSON."""
    items = []
    for c in candidates[:top_n]:
        items.append({
            "text": c.text,
            "source": c.source_file,
            "line": c.line_num,
            "category": c.category,
            "importance": round(c.importance, 3),
        })
    return json.dumps(items, indent=2, ensure_ascii=False)


def find_section(content: str, category: str) -> Optional[int]:
    """Find the line number of the matching section in MEMORY.md."""
    section_names = SECTION_MAP.get(category, [])
    lines = content.split('\n')
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        for name in section_names:
            if stripped == name or stripped.startswith(name):
                return i
    return None


def find_section_end(content: str, section_start: int) -> int:
    """Find the end of a section (next ## header or EOF)."""
    lines = content.split('\n')
    for i in range(section_start + 1, len(lines)):
        if lines[i].strip().startswith('## '):
            return i
    return len(lines)


def check_already_present(text: str, existing_content: str) -> bool:
    """Check if a candidate is already in MEMORY.md using phrase matching."""
    existing_lower = existing_content.lower()
    
    # Extract meaningful phrases (3+ word sequences)
    words = text.lower().split()
    if len(words) < 3:
        return words[0] in existing_lower if words else False
    
    # Check 3-word sliding windows
    matches = 0
    total_windows = max(1, len(words) - 2)
    for i in range(total_windows):
        phrase = ' '.join(words[i:i+3])
        if phrase in existing_lower:
            matches += 1
    
    # If more than 40% of phrases match, consider it present
    return (matches / total_windows) > 0.4


def apply_promotion(candidates: List[PromoteCandidate], memory_file: str, top_n: int = 10) -> str:
    """Apply promotions to MEMORY.md, inserting into matching sections."""
    memory_path = Path(memory_file)

    if not memory_path.exists():
        existing = ""
    else:
        existing = memory_path.read_text(encoding="utf-8")

    # Filter out candidates already in MEMORY.md
    new_candidates = [c for c in candidates[:top_n] if not check_already_present(c.text, existing)]

    if not new_candidates:
        return "All candidates already present in MEMORY.md."

    # Group by category
    by_category: Dict[str, List[PromoteCandidate]] = {}
    for c in new_candidates:
        by_category.setdefault(c.category, []).append(c)

    cat_emoji = {"decision": "🔑", "lesson": "💡", "fact": "📌", "contact": "🤝", "platform": "🔧"}
    lines = existing.split('\n')
    inserted = 0
    unsectioned = []

    for category, items in by_category.items():
        section_start = find_section(existing, category)
        if section_start is not None:
            # Find end of section
            section_end = find_section_end(existing, section_start)
            # Insert before the next section
            new_lines = []
            for item in items:
                emoji = cat_emoji.get(category, "-")
                new_lines.append(f"- {emoji} {item.text}")
                inserted += 1
            # Insert at end of section (before next header)
            for nl in reversed(new_lines):
                lines.insert(section_end, nl)
        else:
            unsectioned.extend(items)

    # Append unsectioned items at the end
    if unsectioned:
        ts = date.today().isoformat()
        lines.append(f"\n## Promoted {ts}")
        for item in unsectioned:
            emoji = cat_emoji.get(item.category, "-")
            lines.append(f"- {emoji} {item.text}")
            inserted += 1

    # Write back
    with open(memory_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return f"✅ Promoted {inserted} items to {memory_path.name} ({len(new_candidates) - len(unsectioned)} into sections, {len(unsectioned)} appended)"
