"""SQLite-based action item tracker for follow-up management."""

import sqlite3
import hashlib
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def init_db(db_path: str) -> None:
    """Initialize SQLite database with action_items table if not exists.

    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS action_items (
            id INTEGER PRIMARY KEY,
            task_id TEXT UNIQUE NOT NULL,
            meeting_uuid TEXT NOT NULL,
            task TEXT NOT NULL,
            owner TEXT,
            due_date TEXT,
            jira_key TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
        )
        """
    )

    conn.commit()
    conn.close()


def save_action_items(
    db_path: str,
    meeting_uuid: str,
    items: list[dict],
    jira_keys: Optional[list[str]] = None,
) -> None:
    """Upsert action items from a processed meeting into DB.

    Args:
        db_path: Path to SQLite database file
        meeting_uuid: UUID of the source meeting
        items: List of action item dicts with 'task', 'owner', 'due' keys
        jira_keys: Optional list of Jira keys to associate with items (in order)

    Log:
        INFO: "Saved N action items for meeting {meeting_uuid}"
    """
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    saved_count = 0
    now = datetime.now().isoformat()

    for idx, item in enumerate(items):
        task = item.get("task", "").strip()

        # Skip empty tasks
        if not task:
            continue

        owner = item.get("owner")
        due = item.get("due")

        # Generate stable task_id from meeting_uuid and task
        task_id = hashlib.sha256(f"{meeting_uuid}:{task}".encode()).hexdigest()[:16]

        # Associate jira_key if provided
        jira_key = None
        if jira_keys and idx < len(jira_keys):
            jira_key = jira_keys[idx]

        # Upsert: insert or replace
        cursor.execute(
            """
            INSERT OR REPLACE INTO action_items
            (task_id, meeting_uuid, task, owner, due_date, jira_key, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (task_id, meeting_uuid, task, owner, due, jira_key, now),
        )

        saved_count += 1

    conn.commit()
    conn.close()

    logger.info(f"Saved {saved_count} action items for meeting {meeting_uuid}")


def list_pending(db_path: str, sort_by: str = "due_date") -> list[dict]:
    """Return all pending action items in dict form.

    Args:
        db_path: Path to SQLite database file
        sort_by: Sort field: "due_date" (default) or "created_at"

    Returns:
        List of dicts with task_id, task, owner, due_date, created_at, jira_key, status
    """
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Sort by due_date ASC (NULLs last) or created_at ASC
    if sort_by == "created_at":
        cursor.execute(
            """
            SELECT task_id, task, owner, due_date, created_at, jira_key, status
            FROM action_items
            WHERE status = 'pending'
            ORDER BY created_at ASC
            """
        )
    else:  # due_date (default)
        cursor.execute(
            """
            SELECT task_id, task, owner, due_date, created_at, jira_key, status
            FROM action_items
            WHERE status = 'pending'
            ORDER BY due_date ASC NULLS LAST, created_at ASC
            """
        )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def mark_done(db_path: str, task_id: str) -> bool:
    """Mark an action item as done.

    Args:
        db_path: Path to SQLite database file
        task_id: Task ID to mark as done

    Returns:
        True if row exists and was updated; False if task_id not found

    Log:
        INFO: "Marked task {task_id} as done"
    """
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute(
        """
        UPDATE action_items
        SET status = 'done', completed_at = ?
        WHERE task_id = ?
        """,
        (now, task_id),
    )

    conn.commit()
    success = cursor.rowcount > 0
    conn.close()

    if success:
        logger.info(f"Marked task {task_id} as done")

    return success


def get_pending_count(db_path: str) -> int:
    """Get count of pending action items.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Number of pending items
    """
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM action_items WHERE status = 'pending'")
    count = cursor.fetchone()[0]
    conn.close()

    return count


def get_overdue(db_path: str) -> list[dict]:
    """Return pending action items with due_date < today.

    Args:
        db_path: Path to SQLite database file

    Returns:
        List of dicts with task_id, task, owner, due_date, created_at, jira_key, status
    """
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    today = datetime.now().date().isoformat()

    cursor.execute(
        """
        SELECT task_id, task, owner, due_date, created_at, jira_key, status
        FROM action_items
        WHERE status = 'pending'
        AND due_date IS NOT NULL
        AND due_date < ?
        ORDER BY due_date ASC
        """,
        (today,),
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
