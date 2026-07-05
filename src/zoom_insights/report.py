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
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript)
    logger.debug(f"Wrote transcript to {transcript_path}")

    # Write insights.json
    insights_path = os.path.join(topic_dir, "insights.json")
    with open(insights_path, "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2)
    logger.debug(f"Wrote insights to {insights_path}")

    # Write report.md
    report_path = os.path.join(topic_dir, "report.md")
    report_content = _render_report(topic, insights)
    with open(report_path, "w", encoding="utf-8") as f:
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
    lines.append(f"# {topic}")
    lines.append("")

    # Summary
    if insights.get("summary"):
        lines.append("## Summary")
        lines.append(insights['summary'])
        lines.append("")

    # Key Points
    key_points = insights.get("key_points", [])
    if key_points:
        lines.append("## Key Points")
        for point in key_points:
            lines.append(f"- {point}")
        lines.append("")

    # Decisions
    decisions = insights.get("decisions", [])
    if decisions:
        lines.append("## Decisions")
        for decision in decisions:
            lines.append(f"- {decision}")
        lines.append("")

    # Action Items
    action_items = insights.get("action_items", [])
    if action_items:
        lines.append("## Action Items")
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
        lines.append("## Open Questions")
        for question in questions:
            lines.append(f"- {question}")
        lines.append("")

    # Notable Quotes
    quotes = insights.get("notable_quotes", [])
    if quotes:
        lines.append("## Notable Quotes")
        for quote in quotes:
            lines.append(f"> {quote}")
        lines.append("")

    # QA Recommendations
    qa_recommendations = insights.get("qa_recommendations")
    if qa_recommendations:
        lines.append("## QA Recommendations")
        lines.append("")

        # Test Scenarios
        test_scenarios = qa_recommendations.get("test_scenarios", [])
        if test_scenarios:
            lines.append("### Test Scenarios")
            for scenario in test_scenarios:
                scenario_text = scenario if isinstance(scenario, str) else scenario.get("title", str(scenario))
                lines.append(f"- {scenario_text}")
            lines.append("")

        # Features to Add
        features = qa_recommendations.get("features_to_add", [])
        if features:
            lines.append("### Features to Add")
            for feature in features:
                feature_text = feature if isinstance(feature, str) else feature.get("title", str(feature))
                lines.append(f"- {feature_text}")
            lines.append("")

        # Edge Cases to Cover
        edge_cases = qa_recommendations.get("edge_cases_to_cover", [])
        if edge_cases:
            lines.append("### Edge Cases to Cover")
            for edge_case in edge_cases:
                edge_case_text = edge_case if isinstance(edge_case, str) else edge_case.get("scenario", str(edge_case))
                lines.append(f"- {edge_case_text}")
            lines.append("")

    return "\n".join(lines)
