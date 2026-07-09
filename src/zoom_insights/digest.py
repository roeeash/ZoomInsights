"""Recurring meeting digest - batch processing and aggregation of multiple meetings."""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from zoom_insights.zoom_client import list_recent_recordings
from zoom_insights.idempotency import is_completed, mark_completed

logger = logging.getLogger(__name__)


def process_meetings_batch(
    token: str,
    groq_client,
    config,
    days_back: int = 7,
    skip_completed: bool = True,
) -> dict:
    """Process all recordings from the past N days, respecting idempotency.

    Args:
        token: Zoom API access token
        groq_client: Groq client for transcription and summarization
        config: Config object with API credentials and settings
        days_back: Number of days to look back (default 7)
        skip_completed: If True, skip already-processed meetings (default True)

    Returns:
        Dictionary with:
            - "meetings": list of processed Meeting objects
            - "insights": list of insights dicts from each meeting
            - "meeting_count": total meetings processed
            - "meetings_processed": list of meeting UUIDs/topics that were processed
    """
    logger.info(f"Processing recordings from last {days_back} days")

    # Import here to avoid circular dependency
    from zoom_insights.cli import _process_meeting

    # List recent recordings
    meetings = list_recent_recordings(token, days_back=days_back)
    logger.info(f"Found {len(meetings)} recordings in the past {days_back} days")

    # Build list of meetings to process (excluding already-completed)
    meetings_to_process = []
    for index, meeting in enumerate(meetings):
        meeting_uuid = meeting.uuid
        if skip_completed and is_completed(meeting_uuid):
            logger.debug(f"Skipping already-completed meeting: {meeting.topic}")
            continue
        meetings_to_process.append((index, meeting))

    insights_list = []
    meetings_processed = []
    processed_count = 0

    if not meetings_to_process:
        logger.info("No new meetings to process")
        return {
            "meetings": meetings,
            "insights": insights_list,
            "meeting_count": processed_count,
            "meetings_processed": meetings_processed,
        }

    # Use ThreadPoolExecutor for concurrent meeting processing
    max_workers = min(len(meetings_to_process), config.max_batch_workers)
    results_by_index = {}  # indexed by original position in meetings list

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_info = {}
        for index, meeting in meetings_to_process:
            logger.info(f"Processing: {meeting.topic}")

            future = executor.submit(
                _process_meeting_for_batch,
                meeting.uuid,
                token,
                groq_client,
                config,
            )
            future_to_info[future] = (index, meeting)

        # Collect results as they complete
        for future in as_completed(future_to_info):
            index, meeting = future_to_info[future]
            try:
                insights = future.result()
                results_by_index[index] = insights
                if insights:
                    processed_count += 1
                    meetings_processed.append(meeting.topic)
                    mark_completed(meeting.uuid)
            except Exception as e:
                logger.error(f"Failed to process {meeting.topic}: {e}")
                results_by_index[index] = None

    # Extract insights in original order
    for index in sorted(results_by_index.keys()):
        insights = results_by_index[index]
        if insights:
            insights_list.append(insights)

    logger.info(f"Processed {processed_count} meetings successfully")

    return {
        "meetings": meetings,
        "insights": insights_list,
        "meeting_count": processed_count,
        "meetings_processed": meetings_processed,
    }


def _process_meeting_for_batch(
    meeting_uuid: str,
    token: str,
    groq_client,
    config,
) -> Optional[dict]:
    """Helper to process a single meeting and return its insights dict.

    Args:
        meeting_uuid: Meeting UUID from Zoom
        token: Zoom API token
        groq_client: Groq client
        config: Config object

    Returns:
        Insights dict if successful, None otherwise
    """
    # Import here to avoid circular dependency
    from zoom_insights.zoom_client import get_meeting_recording, pick_file, download
    from zoom_insights.audio import to_compressed_audio, maybe_segment
    from zoom_insights.transcribe import transcribe
    from zoom_insights.insights import summarize

    try:
        # Get meeting details and recording files
        meeting = get_meeting_recording(token, meeting_uuid)

        # Pick the best audio file
        best_file = pick_file(meeting.files, "M4A", "MP4")
        if not best_file:
            logger.warning(f"No audio file found for {meeting.topic}")
            return None

        # Download the file
        out_path = download(best_file, token, "work")

        # Compress audio
        compressed_path = os.path.join("work", f"compressed_{meeting_uuid}.opus")
        to_compressed_audio(out_path, compressed_path)

        # Segment if needed
        segments = maybe_segment(compressed_path)

        # Transcribe
        transcript = transcribe(segments, groq_client)

        # Summarize
        insights = summarize(transcript, groq_client, config)

        return insights
    except Exception as e:
        logger.error(f"Error processing meeting {meeting_uuid}: {e}")
        return None


def aggregate_insights(insights_list: list[dict]) -> dict:
    """Merge multiple insights dicts into a rollup.

    Deduplicates key_points and decisions, groups action_items by owner,
    includes meeting attribution.

    Args:
        insights_list: List of insights dicts from multiple meetings

    Returns:
        Aggregated insights dict with:
            - "summary": combined summary
            - "key_points": deduplicated list
            - "decisions": deduplicated list
            - "action_items": grouped by owner
            - "open_questions": merged list
            - "notable_quotes": merged list
            - "meeting_count": number of meetings aggregated
            - "meetings_processed": list of meeting topics that contributed
    """
    if not insights_list:
        return {
            "summary": "No meetings processed.",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
            "meeting_count": 0,
            "meetings_processed": [],
        }

    # Collect all data
    all_summaries = []
    all_key_points = []
    all_decisions = []
    all_action_items = []
    all_questions = []
    all_quotes = []
    meetings_processed = []

    for i, insights in enumerate(insights_list):
        if not insights:
            continue

        # Collect summaries (we'll combine them)
        if "summary" in insights and insights["summary"]:
            all_summaries.append(insights["summary"])

        # Collect key points
        if "key_points" in insights:
            all_key_points.extend(insights.get("key_points", []))

        # Collect decisions
        if "decisions" in insights:
            all_decisions.extend(insights.get("decisions", []))

        # Collect action items
        if "action_items" in insights:
            all_action_items.extend(insights.get("action_items", []))

        # Collect questions
        if "open_questions" in insights:
            all_questions.extend(insights.get("open_questions", []))

        # Collect quotes
        if "notable_quotes" in insights:
            all_quotes.extend(insights.get("notable_quotes", []))

        # Track meeting
        meetings_processed.append(f"Meeting {i + 1}")

    # Deduplicate key points and decisions (case-insensitive)
    unique_key_points = []
    seen_kp = set()
    for kp in all_key_points:
        kp_lower = kp.lower().strip() if kp else ""
        if kp_lower and kp_lower not in seen_kp:
            unique_key_points.append(kp)
            seen_kp.add(kp_lower)

    unique_decisions = []
    seen_dec = set()
    for dec in all_decisions:
        dec_lower = dec.lower().strip() if dec else ""
        if dec_lower and dec_lower not in seen_dec:
            unique_decisions.append(dec)
            seen_dec.add(dec_lower)

    # Deduplicate and group action items by owner
    action_items_by_owner = {}
    seen_tasks = set()

    for item in all_action_items:
        if not item or not item.get("task"):
            continue

        task_lower = item.get("task", "").lower().strip()
        if task_lower in seen_tasks:
            continue

        seen_tasks.add(task_lower)

        owner = item.get("owner") or "Unassigned"
        if owner not in action_items_by_owner:
            action_items_by_owner[owner] = []

        action_items_by_owner[owner].append(item)

    # Rebuild action items list (grouped by owner)
    grouped_action_items = []
    for owner in sorted(action_items_by_owner.keys()):
        grouped_action_items.extend(action_items_by_owner[owner])

    # Combine summaries
    combined_summary = " ".join(all_summaries) if all_summaries else "No summary available."

    # Deduplicate questions and quotes
    unique_questions = list(dict.fromkeys(all_questions))
    unique_quotes = list(dict.fromkeys(all_quotes))

    return {
        "summary": combined_summary,
        "key_points": unique_key_points,
        "decisions": unique_decisions,
        "action_items": grouped_action_items,
        "open_questions": unique_questions,
        "notable_quotes": unique_quotes,
        "meeting_count": len(insights_list),
        "meetings_processed": meetings_processed,
    }


def write_digest_report(
    rollup_insights: dict,
    days_back: int,
    out_dir: str = "output",
) -> str:
    """Write a digest report to a dated directory.

    Args:
        rollup_insights: Aggregated insights dict
        days_back: Number of days covered in the digest
        out_dir: Base output directory (default "output")

    Returns:
        Path to the created digest directory

    Creates:
        output/digest-YYYY-MM-DD-to-YYYY-MM-DD/
        ├── report.md
        └── rollup.json
    """
    # Calculate date range
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back - 1)

    date_range = f"{start_date.strftime('%Y-%m-%d')}-to-{end_date.strftime('%Y-%m-%d')}"
    digest_dir = os.path.join(out_dir, f"digest-{date_range}")
    os.makedirs(digest_dir, exist_ok=True)

    logger.info(f"Writing digest report to {digest_dir}")

    # Write rollup.json
    rollup_path = os.path.join(digest_dir, "rollup.json")
    with open(rollup_path, "w", encoding="utf-8") as f:
        json.dump(rollup_insights, f, indent=2)
    logger.debug(f"Wrote rollup to {rollup_path}")

    # Write report.md
    report_path = os.path.join(digest_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(_render_digest_markdown(rollup_insights, start_date, end_date))
    logger.debug(f"Wrote report to {report_path}")

    return digest_dir


def _render_digest_markdown(
    rollup_insights: dict,
    start_date,
    end_date,
) -> str:
    """Render rollup insights as markdown report.

    Args:
        rollup_insights: Aggregated insights dict
        start_date: Start date of the digest
        end_date: End date of the digest

    Returns:
        Markdown string for the report
    """
    lines = []

    lines.append(f"# Digest: {start_date} to {end_date}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(rollup_insights.get("summary", "No summary available."))
    lines.append("")

    # Meetings analyzed
    meeting_count = rollup_insights.get("meeting_count", 0)
    lines.append(f"**Meetings analyzed: {meeting_count}**")
    lines.append("")

    # Key Points
    if rollup_insights.get("key_points"):
        lines.append("## Key Points")
        for point in rollup_insights["key_points"]:
            lines.append(f"- {point}")
        lines.append("")

    # Decisions
    if rollup_insights.get("decisions"):
        lines.append("## Decisions")
        for decision in rollup_insights["decisions"]:
            lines.append(f"- {decision}")
        lines.append("")

    # Action Items (grouped by owner)
    if rollup_insights.get("action_items"):
        lines.append("## Action Items")

        # Group by owner
        by_owner = {}
        for item in rollup_insights["action_items"]:
            owner = item.get("owner") or "Unassigned"
            if owner not in by_owner:
                by_owner[owner] = []
            by_owner[owner].append(item)

        for owner in sorted(by_owner.keys()):
            lines.append(f"### {owner}")
            for item in by_owner[owner]:
                task = item.get("task", "")
                due = item.get("due")
                if due:
                    lines.append(f"- {task} (due: {due})")
                else:
                    lines.append(f"- {task}")
            lines.append("")

    # Open Questions
    if rollup_insights.get("open_questions"):
        lines.append("## Open Questions")
        for question in rollup_insights["open_questions"]:
            lines.append(f"- {question}")
        lines.append("")

    # Notable Quotes
    if rollup_insights.get("notable_quotes"):
        lines.append("## Notable Quotes")
        for quote in rollup_insights["notable_quotes"]:
            lines.append(f"> {quote}")
        lines.append("")

    return "\n".join(lines)
