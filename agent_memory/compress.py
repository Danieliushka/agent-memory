"""
Compress daily logs into structured summaries.
Extracts key facts, decisions, and blockers — drops noise.
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date, timedelta


@dataclass
class DaySummary:
    """Structured summary of a daily log."""
    date: str
    actions: List[str] = field(default_factory=list)      # What was done
    decisions: List[str] = field(default_factory=list)     # Key decisions made
    blockers: List[str] = field(default_factory=list)      # What's stuck
    learnings: List[str] = field(default_factory=list)     # Insights/lessons
    contacts: List[str] = field(default_factory=list)      # People/agents mentioned
    links: List[str] = field(default_factory=list)         # URLs referenced
    stats: dict = field(default_factory=dict)              # Metrics (posts, commits, etc.)


def extract_summary(content: str, date_str: str = "") -> DaySummary:
    """
    Extract structured summary from a daily log.
    Uses pattern matching — no LLM needed.
    """
    summary = DaySummary(date=date_str)
    
    lines = content.split('\n')
    current_section = ""
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # Detect section headers
        if stripped.startswith('## '):
            current_section = stripped[3:].lower()
            continue
        
        # Extract actions (lines starting with - or * that describe completed work)
        if stripped.startswith(('- ', '* ')):
            item = stripped[2:]
            
            # Blockers
            if any(kw in item.lower() for kw in ['blocked', 'stuck', 'waiting', 'broken', 'failed', 'error', 'not working']):
                summary.blockers.append(item)
            # Decisions
            elif any(kw in item.lower() for kw in ['decided', 'decision', 'вирішив', 'рішення', 'changed to', 'switched']):
                summary.decisions.append(item)
            # Learnings
            elif any(kw in item.lower() for kw in ['learned', 'lesson', 'урок', 'зрозумів', 'insight', 'realization', 'дізнався']):
                summary.learnings.append(item)
            # Actions (everything else)
            else:
                summary.actions.append(item)
        
        # Extract contacts (@ mentions or agent names)
        contacts = re.findall(r'@(\w+)', stripped)
        contacts += re.findall(r'(?:з|from|with|replied to|commented on)\s+(\w+(?:\s+\w+)?)', stripped, re.IGNORECASE)
        summary.contacts.extend(contacts)
        
        # Extract URLs
        urls = re.findall(r'https?://[^\s\)]+', stripped)
        summary.links.extend(urls)
    
    # Dedupe contacts
    summary.contacts = list(set(summary.contacts))
    summary.links = list(set(summary.links))
    
    return summary


def format_summary(summary: DaySummary) -> str:
    """Format a DaySummary as compact markdown."""
    lines = [f"### {summary.date}"]
    
    if summary.actions:
        lines.append(f"**Done:** {'; '.join(summary.actions[:5])}")
        if len(summary.actions) > 5:
            lines.append(f"  (+{len(summary.actions) - 5} more actions)")
    
    if summary.decisions:
        lines.append(f"**Decisions:** {'; '.join(summary.decisions)}")
    
    if summary.blockers:
        lines.append(f"**Blocked:** {'; '.join(summary.blockers)}")
    
    if summary.learnings:
        lines.append(f"**Learned:** {'; '.join(summary.learnings)}")
    
    if summary.contacts:
        lines.append(f"**Contacts:** {', '.join(summary.contacts[:10])}")
    
    return '\n'.join(lines)


def compress_week(memory_dir: str, week_date: Optional[date] = None) -> str:
    """
    Compress a week of daily logs into a weekly summary.
    
    Args:
        memory_dir: Path to memory directory
        week_date: Any date in the target week (defaults to last week)
    
    Returns:
        Formatted weekly summary markdown
    """
    if week_date is None:
        week_date = date.today() - timedelta(weeks=1)
    
    # Find Monday of the week
    monday = week_date - timedelta(days=week_date.weekday())
    
    memory_path = Path(memory_dir)
    summaries = []
    
    for i in range(7):
        day = monday + timedelta(days=i)
        day_file = memory_path / f"{day.isoformat()}.md"
        
        if day_file.exists():
            with open(day_file, 'r') as f:
                content = f.read()
            summary = extract_summary(content, day.isoformat())
            summaries.append(summary)
    
    if not summaries:
        return f"# Week of {monday.isoformat()}\n\nNo daily logs found."
    
    # Aggregate
    week_num = monday.isocalendar()[1]
    lines = [
        f"# Week {week_num} ({monday.isoformat()} → {(monday + timedelta(days=6)).isoformat()})",
        "",
    ]
    
    # Per-day summaries
    for s in summaries:
        lines.append(format_summary(s))
        lines.append("")
    
    # Aggregated stats
    all_contacts = set()
    all_blockers = []
    all_decisions = []
    total_actions = 0
    
    for s in summaries:
        all_contacts.update(s.contacts)
        all_blockers.extend(s.blockers)
        all_decisions.extend(s.decisions)
        total_actions += len(s.actions)
    
    lines.append("---")
    lines.append(f"**Week totals:** {total_actions} actions | {len(all_decisions)} decisions | {len(all_blockers)} blockers")
    
    if all_contacts:
        lines.append(f"**All contacts:** {', '.join(sorted(all_contacts))}")
    
    if all_blockers:
        lines.append(f"**Unresolved:** {'; '.join(all_blockers)}")
    
    return '\n'.join(lines)
