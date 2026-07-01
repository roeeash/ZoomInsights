"""Report generation and output file writing."""

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def sanitize_topic(topic: str) -> str:
    """Convert a meeting topic into a safe directory name."""
    # Remove or replace unsafe characters
    safe_name = re.sub(r"[^\w\s-]", "", topic)
    # Replace spaces with underscores
    safe_name = re.sub(r"\s+", "_", safe_name.strip())
    # Remove trailing underscores
    safe_name = safe_name.rstrip("_")
    # Limit length to 100 chars
    return safe_name[:100] or "meeting"


def write_report(topic: str, transcript: str, insights: dict, out_dir: str) -> None:
    """Write transcript, insights.json, and report.md to the output directory.

    Args:
        topic: Meeting topic (will be sanitized for directory name).
        transcript: Full meeting transcript text.
        insights: Dictionary with insights (must match INSIGHTS_SCHEMA).
        out_dir: Base output directory (e.g. "output").

    Creates:
        output/<safe-topic>/transcript.txt
        output/<safe-topic>/insights.json
        output/<safe-topic>/report.md
    """
    # Create safe directory name
    safe_topic = sanitize_topic(topic)
    topic_dir = os.path.join(out_dir, safe_topic)
    os.makedirs(topic_dir, exist_ok=True)

    logger.info(f"Writing report to {topic_dir}")

    # Write transcript.txt
    transcript_path = os.path.join(topic_dir, "transcript.txt")
    with open(transcript_path, "w") as f:
        f.write(transcript)
    logger.debug(f"Wrote transcript to {transcript_path}")

    # Write insights.json
    insights_path = os.path.join(topic_dir, "insights.json")
    with open(insights_path, "w") as f:
        json.dump(insights, f, indent=2)
    logger.debug(f"Wrote insights to {insights_path}")

    # Write report.md
    report_path = os.path.join(topic_dir, "report.md")
    report_content = _render_report(topic, insights)
    with open(report_path, "w") as f:
        f.write(report_content)
    logger.debug(f"Wrote report to {report_path}")

    logger.info(f"Report complete: {topic_dir}")


def _render_report(topic: str, insights: dict) -> str:
    """Render insights object into markdown report.

    Args:
        topic: Meeting topic.
        insights: Dictionary with insights.

    Returns:
        Markdown-formatted report.
    """
    lines = []

    # Title
    lines.append(f"# {topic}\n")

    # Summary
    if insights.get("summary"):
        lines.append("## Summary\n")
        lines.append(f"{insights['summary']}\n")

    # Key Points
    key_points = insights.get("key_points", [])
    if key_points:
        lines.append("## Key Points\n")
        for point in key_points:
            lines.append(f"- {point}")
        lines.append("")

    # Decisions
    decisions = insights.get("decisions", [])
    if decisions:
        lines.append("## Decisions\n")
        for decision in decisions:
            lines.append(f"- {decision}")
        lines.append("")

    # Action Items
    action_items = insights.get("action_items", [])
    if action_items:
        lines.append("## Action Items\n")
        for item in action_items:
            owner = item.get("owner") or "Unassigned"
            task = item.get("task", "")
            due = item.get("due")
            if due:
                lines.append(f"- **{owner}** — {task} (due: {due})")
            else:
                lines.append(f"- **{owner}** — {task}")
        lines.append("")

    # Open Questions
    questions = insights.get("open_questions", [])
    if questions:
        lines.append("## Open Questions\n")
        for question in questions:
            lines.append(f"- {question}")
        lines.append("")

    # Notable Quotes
    quotes = insights.get("notable_quotes", [])
    if quotes:
        lines.append("## Notable Quotes\n")
        for quote in quotes:
            lines.append(f'> {quote}')
            lines.append("")

    return "\n".join(lines)
