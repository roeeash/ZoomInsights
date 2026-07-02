"""Idempotency tracking for processed meetings."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve path relative to project root
COMPLETED_LOG_PATH = str(Path(__file__).parent.parent.parent / "work" / "completed.log")


def load_completed_uuids(log_path: str = COMPLETED_LOG_PATH) -> set[str]:
    """Load the set of already-processed meeting UUIDs.

    Args:
        log_path: Path to completed.log file.

    Returns:
        Set of UUIDs that have been processed.
    """
    if not os.path.exists(log_path):
        return set()

    uuids = set()
    try:
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    uuids.add(line)
    except IOError as e:
        logger.warning(f"Error reading completed log: {e}")

    return uuids


def mark_completed(meeting_uuid: str, log_path: str = COMPLETED_LOG_PATH) -> None:
    """Mark a meeting UUID as completed (deduplicates if already present).

    Args:
        meeting_uuid: UUID of the processed meeting.
        log_path: Path to completed.log file.
    """
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    try:
        # Check if UUID already in log; deduplicate
        completed = load_completed_uuids(log_path)
        if meeting_uuid in completed:
            logger.debug(f"{meeting_uuid} already marked as completed")
            return

        with open(log_path, "a") as f:
            f.write(f"{meeting_uuid}\n")
        logger.debug(f"Marked {meeting_uuid} as completed")
    except IOError as e:
        logger.warning(f"Error writing to completed log: {e}")


def is_completed(meeting_uuid: str, log_path: str = COMPLETED_LOG_PATH) -> bool:
    """Check if a meeting UUID has been processed.

    Args:
        meeting_uuid: UUID to check.
        log_path: Path to completed.log file.

    Returns:
        True if the meeting has been processed before.
    """
    completed = load_completed_uuids(log_path)
    return meeting_uuid in completed
