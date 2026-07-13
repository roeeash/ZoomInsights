"""Command-line interface for the Zoom Insights pipeline."""

import argparse
import base64
import functools
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from typing import Optional

import requests

from zoom_insights.config import load_config, Config
from zoom_insights.logging_config import setup_logging
from zoom_insights.zoom_client import (
    get_access_token,
    list_recent_recordings,
    get_meeting_recording,
    pick_file,
    download,
    download_path,
    ensure_work_dir,
)
from zoom_insights.audio import to_compressed_audio, maybe_segment, require_ffmpeg
from zoom_insights.transcribe import transcribe
from zoom_insights.insights import summarize
from zoom_insights.report import write_report, sanitize_topic
from zoom_insights.idempotency import is_completed, mark_completed
from zoom_insights.jira_export import create_jira_tickets, _build_auth_header
from zoom_insights.enrich_insights import enrich_insights_with_repo_context, read_repo_code_summary
from zoom_insights.notify import post_notification
from groq import Groq
from pathlib import Path

logger = logging.getLogger(__name__)


def _validate_jira_credentials(config: Config) -> None:
    """Validate Jira credentials by calling /rest/api/3/myself.

    Raises:
        RuntimeError: if credentials are invalid (401/403)
    """
    headers = {"Authorization": _build_auth_header(config.jira_email, config.jira_api_token)}

    try:
        response = requests.get(
            f"{config.jira_url}/rest/api/3/myself",
            headers=headers,
            timeout=5
        )
        if response.status_code in (401, 403):
            raise RuntimeError(
                f"Jira authentication failed ({response.status_code}): "
                "check JIRA_EMAIL and JIRA_API_TOKEN"
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to validate Jira credentials (HTTP {response.status_code})"
            )
        logger.info("Jira credentials validated")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Error validating Jira credentials: {e}")


@functools.lru_cache(maxsize=1)
def _load_agent_guidance() -> str:
    """Load the client-facing automation engineer agent's guidance.

    Returns:
        Agent guidance text for QA recommendations context, or empty string if not found.
    """
    # Resolve path relative to project root (not CWD)
    project_root = Path(__file__).parent.parent.parent
    agent_path = project_root / ".claude" / "agents" / "client-facing-automation-engineer.md"

    if not agent_path.exists():
        return ""

    try:
        with open(str(agent_path), "r", encoding="utf-8") as f:
            content = f.read()

        # Extract content after frontmatter (skip YAML)
        if "---" in content:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                guidance = parts[2].strip()
                return guidance

        return content
    except Exception as e:
        logger.debug(f"Could not load agent guidance: {e}")
        return ""



def main() -> None:
    """Main entry point for the CLI orchestrating the full pipeline."""
    parser = argparse.ArgumentParser(
        description="Extract structured insights from Zoom recordings"
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="list",
        help="Action: 'list' (default), 'jira', or meeting index/UUID to process (with Zoom), or path to insights.json/local file (with --local)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Process a locally saved Zoom recording file (no Zoom Cloud API needed)",
    )
    parser.add_argument(
        "--title",
        type=str,
        help="Override meeting title for local file processing (default: filename without extension)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--use-zoom-transcript",
        action="store_true",
        help="Use Zoom's VTT transcript instead of Whisper (if available)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess even if already completed (override idempotency)",
    )
    parser.add_argument(
        "--jira",
        action="store_true",
        help="Auto-export action items to Jira after processing (requires JIRA_* env vars)",
    )
    parser.add_argument(
        "--insights",
        type=str,
        help="Path to insights.json for Jira export (used with 'jira' action)",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        help="Output file path for enriched insights (auto-enrichment when passing insights.json)",
    )
    parser.add_argument(
        "--repo-path",
        type=str,
        default=".",
        help="Path to repository for code context (auto-enrichment when passing insights.json, default: current dir)",
    )
    parser.add_argument(
        "--task-id",
        type=str,
        help="Task ID to mark as done (used with 'done' action)",
    )
    parser.add_argument(
        "--notify",
        type=str,
        default="",
        help="Post summary to Slack or Teams webhook URL (optional; auto-detects platform)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(debug=args.debug)

    try:
        # Check if Jira action is being used (skip Zoom/Groq setup if so)
        # Check if status command is being used
        if args.action == "status":
            config = load_config()
            _status_command(config)
            return

        # Check if done command is being used
        if args.action == "done":
            if not args.task_id:
                print("Error: --task-id <id> required for 'done' command")
                sys.exit(1)
            config = load_config()
            _done_command(args.task_id, config)
            return

        if args.action == "jira":
            config = load_config()
            logger.info("Configuration loaded")
            _export_to_jira(args.insights, config)
            return

        # Check if insights.json file is passed (auto-enrich it)
        if args.action and os.path.isfile(args.action) and args.action.endswith("insights.json"):
            config = load_config()
            logger.info("Configuration loaded")
            _enrich_insights_cmd(args.action, args.output_file, args.repo_path, config)
            return

        # Check ffmpeg availability early
        require_ffmpeg()

        # Load configuration (Groq API key always needed)
        config = load_config()
        logger.info("Configuration loaded")

        # Initialize Groq client (always needed)
        groq_client = Groq(api_key=config.groq_api_key)
        logger.info("Groq client initialized")

        # Ensure work directory
        work_dir = ensure_work_dir("work")

        # Handle local file mode
        if args.local:
            if not args.action or args.action == "list":
                print("Error: --local requires a file path")
                print("Usage: zoom-insights /path/to/recording.mp4 --local [--title 'Meeting Title']")
                sys.exit(1)
            _process_local_file(
                args.action,
                groq_client,
                work_dir,
                title_override=args.title,
                force=args.force,
                jira=args.jira,
                config=config,
                notify=args.notify,
            )
            return

        # Zoom Cloud mode (requires authentication)
        # Initialize Zoom client
        token = get_access_token(config)
        logger.info("Zoom auth successful")

        # Handle 'list' action or no argument
        if args.action == "list":
            _list_recordings(token)
            return

        # Process specific meeting by index or UUID
        _process_meeting(
            args.action,
            token,
            groq_client,
            config,
            use_vtt=args.use_zoom_transcript,
            work_dir=work_dir,
            force=args.force,
            jira=args.jira,
            notify=args.notify,
        )

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"Configuration error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Error: {e}")
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Unexpected error: {e}")
        sys.exit(1)


def _list_recordings(token: str) -> None:
    """List recent recordings and their indices."""
    meetings = list_recent_recordings(token)

    if not meetings:
        print("No recent recordings found.")
        return

    print("\nRecent recordings:")
    for i, meeting in enumerate(meetings):
        date_str = datetime.fromisoformat(
            meeting.start_time.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d %H:%M")
        print(f"  [{i}] {date_str} {meeting.topic}")

    print(f"\nTo process a recording: zoom-insights <index_or_uuid> [--use-zoom-transcript]")


def _process_meeting(
    meeting_ref: str,
    token: str,
    groq_client,
    config,
    use_vtt: bool = False,
    work_dir: str = "work",
    force: bool = False,
    jira: bool = False,
    notify: str = "",
) -> None:
    """Process a single meeting from index or UUID."""
    logger.info(f"Processing meeting: {meeting_ref}")

    # Validate Jira configuration early if jira export is requested
    if jira and not all([config.jira_url, config.jira_email, config.jira_api_token, config.jira_project_key]):
        raise RuntimeError("Jira configuration incomplete; check JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY")

    # Resolve meeting reference to UUID
    meeting_uuid = meeting_ref
    try:
        # Try as index first
        index = int(meeting_ref)
        meetings = list_recent_recordings(token)
        if index < 0 or index >= len(meetings):
            raise ValueError(f"Index {index} out of range (0-{len(meetings) - 1})")
        meeting_uuid = meetings[index].uuid
        logger.info(f"Resolved index {index} to UUID {meeting_uuid}")
    except ValueError as e:
        if "invalid literal" in str(e).lower():
            # Treat as UUID
            pass
        else:
            raise

    # Check idempotency
    if is_completed(meeting_uuid) and not force:
        logger.warning(f"Meeting {meeting_uuid} already processed; use --force to override")
        return
    if is_completed(meeting_uuid) and force:
        logger.info(f"Reprocessing meeting {meeting_uuid} (--force flag)")
        print(f"Reprocessing meeting: {meeting_uuid}")

    # Fetch meeting recording details
    logger.info(f"Fetching recording for meeting {meeting_uuid}")
    meeting = get_meeting_recording(token, meeting_uuid)

    # Pick audio file (prefer M4A over MP4)
    audio_file = pick_file(meeting.files, "M4A", "MP4")
    if not audio_file:
        raise RuntimeError(f"No audio files found for meeting {meeting_uuid}")

    logger.info(f"Selected file: {audio_file.file_name} ({audio_file.file_type})")

    # Download audio
    logger.info("Stage 1: Downloading audio...")
    download_path_str = download_path(audio_file, work_dir)
    download(audio_file, token, download_path_str)
    print(f"Downloaded to: {download_path_str}")

    # Compress audio
    logger.info("Stage 2: Compressing audio...")
    compressed_path = f"{download_path_str}.opus"
    to_compressed_audio(download_path_str, compressed_path)
    logger.info(f"Compressed audio: {compressed_path}")

    # Segment if necessary
    logger.info("Stage 3: Segmenting audio if needed...")
    segment_paths = maybe_segment(compressed_path)
    logger.info(f"Audio split into {len(segment_paths)} segment(s)")

    # Transcribe
    logger.info("Stage 4: Transcribing audio...")
    transcript = transcribe(
        segment_paths,
        groq_client,
        use_vtt=use_vtt,
        meeting_uuid=meeting_uuid,
        files=meeting.files,
        token=token,
        model=config.whisper_model,
        max_workers=config.max_transcription_workers,
    )
    logger.info(f"Transcript: {len(transcript)} characters")

    # Extract insights
    logger.info("Stage 5: Extracting insights with QA recommendations...")
    repo_summary = read_repo_code_summary(".")
    agent_guidance = _load_agent_guidance()
    insights = summarize(transcript, groq_client, model=config.llm_model, repo_summary=repo_summary, agent_guidance=agent_guidance)
    logger.info("Insights extracted and validated")

    # Enrich insights with repository context
    try:
        insights = enrich_insights_with_repo_context(insights, ".", config.groq_api_key, config.llm_model)
        logger.info("Insights enriched with repository context")
    except Exception as e:
        logger.warning(f"Failed to enrich insights: {e}")

    # Generate report
    logger.info("Stage 6: Generating report...")
    write_report(meeting.topic, transcript, insights, "output")
    logger.info(f"Report written to output/{sanitize_topic(meeting.topic)}/")

    # Post notification if requested
    if notify:
        logger.info(f"Posting notification to {notify}")
        success = post_notification(insights, notify)
        if success:
            logger.info("Notification posted successfully")
        else:
            logger.warning("Notification posting failed")

    # Auto-export to Jira if requested
    if jira:
        report_dir = os.path.join("output", sanitize_topic(meeting.topic))
        insights_path = os.path.join(report_dir, "insights.json")
        _export_to_jira(insights_path, config)

    # Mark as completed
    # Auto-save action items to tracker
    if config.tracker_db:
        from zoom_insights.tracker import save_action_items
        save_action_items(config.tracker_db, meeting_uuid, insights.get("action_items", []))
        logger.info(f"Saved action items to tracker")

    mark_completed(meeting_uuid)
    logger.info(f"Meeting {meeting_uuid} marked as completed")

    # Cleanup work directory
    try:
        shutil.rmtree(os.path.dirname(download_path_str), ignore_errors=True)
        logger.debug(f"Cleaned up work directory")
    except Exception as e:
        logger.debug(f"Could not clean up work directory: {e}")

    print(f"\nProcessing complete!")
    print(f"Report: output/{sanitize_topic(meeting.topic)}/")
    print(f"  - report.md")
    print(f"  - insights.json")
    print(f"  - transcript.txt")


def _process_local_file(
    file_path: str,
    groq_client,
    work_dir: str = "work",
    title_override: str = None,
    force: bool = False,
    jira: bool = False,
    config: Config = None,
    notify: str = "",
) -> None:
    """Process a locally saved Zoom recording file."""
    logger.info(f"Processing local file: {file_path}")

    # Validate file exists
    if not os.path.isfile(file_path):
        raise RuntimeError(f"File not found: {file_path}")

    # Extract or use title
    if title_override:
        meeting_title = title_override
        logger.info(f"Using provided title: {meeting_title}")
    else:
        # Use filename without extension as title
        meeting_title = os.path.splitext(os.path.basename(file_path))[0]
        logger.info(f"Extracted title from filename: {meeting_title}")

    # Use absolute path as UUID for idempotency tracking (to distinguish same-named files in different dirs)
    meeting_uuid = str(Path(file_path).resolve())

    # Validate Jira configuration early if jira export is requested
    if jira:
        if not config:
            raise ValueError("config required when jira=True")
        if not all([config.jira_url, config.jira_email, config.jira_api_token, config.jira_project_key]):
            raise RuntimeError("Jira configuration incomplete; check JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY")
        # Validate Jira credentials early
        _validate_jira_credentials(config)

    # Check idempotency
    if is_completed(meeting_uuid) and not force:
        logger.warning(f"File {meeting_uuid} already processed; use --force to override")
        return
    if is_completed(meeting_uuid) and force:
        logger.info(f"Reprocessing file {meeting_uuid} (--force flag)")
        print(f"Reprocessing file: {meeting_uuid}")

    # Copy file to work directory
    logger.info("Stage 1: Copying audio to work directory...")
    work_file = os.path.join(work_dir, os.path.basename(file_path))
    shutil.copy2(file_path, work_file)
    logger.info(f"Copied to: {work_file}")
    print(f"Copied to work directory: {work_file}")

    # Compress audio
    logger.info("Stage 2: Compressing audio...")
    compressed_path = f"{work_file}.opus"
    to_compressed_audio(work_file, compressed_path)
    logger.info(f"Compressed audio: {compressed_path}")

    # Segment if necessary
    logger.info("Stage 3: Segmenting audio if needed...")
    segment_paths = maybe_segment(compressed_path)
    logger.info(f"Audio split into {len(segment_paths)} segment(s)")

    # Transcribe (no VTT for local files)
    logger.info("Stage 4: Transcribing audio with Groq Whisper...")
    transcript = transcribe(segment_paths, groq_client, use_vtt=False, model=config.whisper_model, max_workers=config.max_transcription_workers)
    logger.info(f"Transcript: {len(transcript)} characters")

    # Extract insights
    logger.info("Stage 5: Extracting insights with QA recommendations...")
    repo_summary = read_repo_code_summary(".")
    agent_guidance = _load_agent_guidance()
    insights = summarize(transcript, groq_client, model=config.llm_model, repo_summary=repo_summary, agent_guidance=agent_guidance)
    logger.info("Insights extracted and validated")

    # Enrich insights with repository context
    try:
        insights = enrich_insights_with_repo_context(insights, ".", config.groq_api_key, config.llm_model)
        logger.info("Insights enriched with repository context")
    except Exception as e:
        logger.warning(f"Failed to enrich insights: {e}")

    # Generate report
    logger.info("Stage 6: Generating report...")
    write_report(meeting_title, transcript, insights, "output")
    logger.info(f"Report written to output/{sanitize_topic(meeting_title)}/")

    # Post notification if requested
    if notify:
        logger.info(f"Posting notification to {notify}")
        success = post_notification(insights, notify)
        if success:
            logger.info("Notification posted successfully")
        else:
            logger.warning("Notification posting failed")

    # Auto-export to Jira if requested
    if jira:
        report_dir = os.path.join("output", sanitize_topic(meeting_title))
        insights_path = os.path.join(report_dir, "insights.json")
        _export_to_jira(insights_path, config)

    # Mark as completed
    mark_completed(meeting_uuid)
    logger.info(f"File {meeting_uuid} marked as completed")

    # Cleanup work files
    # Auto-save action items to tracker
    if config.tracker_db:
        from zoom_insights.tracker import save_action_items
        save_action_items(config.tracker_db, meeting_uuid, insights.get("action_items", []))
        logger.info(f"Saved action items to tracker")

    logger.info("Cleaning up temporary work files...")
    try:
        os.remove(work_file)
        os.remove(compressed_path)
        for segment in segment_paths:
            if os.path.exists(segment):
                os.remove(segment)
        logger.info("Cleanup complete")
    except Exception as e:
        logger.warning(f"Could not delete work files: {e}")

    print(f"\nProcessing complete!")
    print(f"Report: output/{sanitize_topic(meeting_title)}/")
    print(f"  - report.md")
    print(f"  - insights.json")
    print(f"  - transcript.txt")


def _enrich_insights_cmd(
    insights_path: str,
    output_file: Optional[str],
    repo_path: str,
    config: Config,
) -> None:
    """Enrich insights with repository-aware QA recommendations.

    Args:
        insights_path: Path to insights.json file (or used as input file path)
        output_file: Path to write enriched insights (if None, overwrites input)
        repo_path: Path to repository for code context
        config: Configuration object with Claude API key

    Raises:
        SystemExit: on validation or file errors
    """
    # Check Groq API key is set
    if not config.groq_api_key:
        logger.debug("Groq API key not set; skipping automatic enrichment")
        return

    # Check insights file is provided and exists
    if not insights_path:
        logger.debug("No insights path provided; skipping enrichment")
        return

    if not os.path.isfile(insights_path):
        print(f"Error: Insights file not found: {insights_path}")
        sys.exit(1)

    # Load and parse insights.json
    try:
        with open(insights_path, "r") as f:
            insights = json.load(f)
        logger.info(f"Loaded insights from {insights_path}")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {insights_path}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to read {insights_path}: {e}")
        sys.exit(1)

    # Enrich insights
    logger.info("Enriching insights with QA recommendations...")
    try:
        enriched_insights = enrich_insights_with_repo_context(
            insights,
            repo_path,
            config.groq_api_key,
            model=config.llm_model
        )
        logger.info("Insights enriched successfully")
    except ValueError as e:
        print(f"Error: {e}")
        logger.error(f"Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to enrich insights: {e}")
        logger.exception(f"Exception enriching insights: {e}")
        sys.exit(1)

    # Write enriched insights to file
    output_path = output_file or insights_path
    try:
        with open(output_path, "w") as f:
            json.dump(enriched_insights, f, indent=2)
        logger.info(f"Enriched insights written to {output_path}")
        print(f"Enriched insights written to: {output_path}")
    except Exception as e:
        print(f"Error: Failed to write output file: {e}")
        logger.exception(f"Exception writing output: {e}")
        sys.exit(1)


def _export_to_jira(insights_path: Optional[str], config: Config) -> None:
    """Export insights to Jira Cloud tickets.

    Args:
        insights_path: Path to insights.json file
        config: Configuration object with Jira settings

    Raises:
        SystemExit: on validation or file errors
    """
    # Check insights file is provided and exists
    if not insights_path:
        print("Error: --insights <path> required for jira command")
        sys.exit(1)

    if not os.path.isfile(insights_path):
        print(f"Error: Insights file not found: {insights_path}")
        sys.exit(1)

    # Check all Jira config vars are set
    missing_vars = []
    if not config.jira_url:
        missing_vars.append("JIRA_URL")
    if not config.jira_email:
        missing_vars.append("JIRA_EMAIL")
    if not config.jira_api_token:
        missing_vars.append("JIRA_API_TOKEN")
    if not config.jira_project_key:
        missing_vars.append("JIRA_PROJECT_KEY")

    if missing_vars:
        print(f"Error: missing Jira config: {', '.join(missing_vars)}")
        sys.exit(1)

    # Load and parse insights.json
    try:
        with open(insights_path, "r") as f:
            insights = json.load(f)
        logger.info(f"Loaded insights from {insights_path}")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {insights_path}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to read {insights_path}: {e}")
        sys.exit(1)

    # Create tickets
    logger.info(f"Creating Jira tickets in {config.jira_project_key}")
    try:
        created_keys = create_jira_tickets(
            insights,
            config.jira_url,
            config.jira_email,
            config.jira_api_token,
            config.jira_project_key
        )
        logger.info(f"Created {len(created_keys)} ticket(s)")
        print(f"\nCreated {len(created_keys)} ticket(s) in {config.jira_project_key}")
    except ValueError as e:
        print(f"Error: {e}")
        logger.error(f"Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to create tickets: {e}")
        logger.exception(f"Exception creating tickets: {e}")
        sys.exit(1)


def _status_command(config: Config) -> None:
    """Display pending action items status.

    Args:
        config: Configuration object with tracker_db path
    """
    from zoom_insights.tracker import list_pending, get_overdue

    if not config.tracker_db:
        print("Error: TRACKER_DB not configured")
        return

    pending = list_pending(config.tracker_db)
    overdue = get_overdue(config.tracker_db)

    if not pending:
        print("No pending action items.")
        return

    # Separate pending into overdue, upcoming, and no due date
    upcoming = [item for item in pending if item not in overdue and item["due_date"]]
    no_due_date = [item for item in pending if not item["due_date"]]

    print(f"\nPending Action Items ({len(pending)} total)")
    print("=" * 48)

    if overdue:
        print(f"\nOVERDUE ({len(overdue)} items):")
        for item in overdue:
            owner_str = f"({item['owner']})" if item["owner"] else "(unassigned)"
            due_str = f" (due: {item['due_date']})" if item["due_date"] else ""
            print(f"  - [{item['task_id']}] {owner_str} {item['task']}{due_str}")

    if upcoming:
        print(f"\nUPCOMING ({len(upcoming)} items):")
        for item in upcoming:
            owner_str = f"({item['owner']})" if item["owner"] else "(unassigned)"
            due_str = f" (due: {item['due_date']})" if item["due_date"] else ""
            print(f"  - [{item['task_id']}] {owner_str} {item['task']}{due_str}")

    if no_due_date:
        print(f"\nNO DUE DATE ({len(no_due_date)} items):")
        for item in no_due_date:
            owner_str = f"({item['owner']})" if item["owner"] else "(unassigned)"
            print(f"  - [{item['task_id']}] {owner_str} {item['task']}")


def _done_command(task_id: str, config: Config) -> None:
    """Mark an action item as done.

    Args:
        task_id: Task ID to mark as done
        config: Configuration object with tracker_db path

    Raises:
        SystemExit: if task_id not found
    """
    from zoom_insights.tracker import mark_done

    if not config.tracker_db:
        print("Error: TRACKER_DB not configured")
        sys.exit(1)

    success = mark_done(config.tracker_db, task_id)

    if success:
        print(f"Marked {task_id} as done")
        logger.info(f"marked task {task_id} as done")
    else:
        print(f"Task {task_id} not found")
        sys.exit(1)
