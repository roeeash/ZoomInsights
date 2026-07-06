"""Tests for action item tracker (SQLite persistence)."""

import pytest
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from zoom_insights.tracker import (
    init_db,
    save_action_items,
    list_pending,
    mark_done,
    get_pending_count,
    get_overdue,
)


@pytest.mark.unit
class TestInitDB:
    """Tests for init_db function."""

    def test_init_db_creates_table(self, tmp_path):
        """Test that init_db creates action_items table if not exists."""
        db_path = str(tmp_path / "test.db")

        init_db(db_path)

        # Verify table exists
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='action_items'"
        )
        table = cursor.fetchone()
        conn.close()

        assert table is not None, "action_items table should exist"

    def test_init_db_idempotent(self, tmp_path):
        """Test that init_db can be called multiple times without error."""
        db_path = str(tmp_path / "test.db")

        init_db(db_path)
        init_db(db_path)  # Second call should not raise

        # Verify table still exists
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='action_items'"
        )
        table = cursor.fetchone()
        conn.close()

        assert table is not None


@pytest.mark.unit
class TestSaveActionItems:
    """Tests for save_action_items function."""

    def test_save_single_action_item(self, tmp_path):
        """Test that a single action item is saved to DB."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-123"
        items = [
            {"task": "Review proposal", "owner": "Alice", "due": "2026-07-15"}
        ]

        save_action_items(db_path, meeting_uuid, items)

        # Verify item is in DB
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM action_items")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0]["task"] == "Review proposal"
        assert rows[0]["owner"] == "Alice"
        assert rows[0]["due_date"] == "2026-07-15"
        assert rows[0]["status"] == "pending"

    def test_save_multiple_items(self, tmp_path):
        """Test that multiple action items are saved with correct fields."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-456"
        items = [
            {"task": "Task 1", "owner": "Alice", "due": "2026-07-10"},
            {"task": "Task 2", "owner": "Bob", "due": "2026-07-20"},
            {"task": "Task 3", "owner": None, "due": None},
        ]

        save_action_items(db_path, meeting_uuid, items)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM action_items ORDER BY task")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 3
        assert rows[0]["task"] == "Task 1"
        assert rows[1]["task"] == "Task 2"
        assert rows[2]["task"] == "Task 3"
        assert rows[2]["owner"] is None
        assert rows[2]["due_date"] is None

    def test_save_skips_empty_task(self, tmp_path):
        """Test that items with empty task description are skipped."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-789"
        items = [
            {"task": "Real task", "owner": "Alice", "due": None},
            {"task": "", "owner": "Bob", "due": "2026-07-20"},
            {"task": "Another task", "owner": "Charlie", "due": None},
        ]

        save_action_items(db_path, meeting_uuid, items)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM action_items")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 2, "Only non-empty tasks should be saved"

    def test_save_with_jira_keys(self, tmp_path):
        """Test that jira_keys are associated with action items in order."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-jira"
        items = [
            {"task": "Task 1", "owner": "Alice", "due": None},
            {"task": "Task 2", "owner": "Bob", "due": None},
        ]
        jira_keys = ["PROJ-1", "PROJ-2"]

        save_action_items(db_path, meeting_uuid, items, jira_keys=jira_keys)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT task, jira_key FROM action_items ORDER BY task")
        rows = cursor.fetchall()
        conn.close()

        assert rows[0]["jira_key"] == "PROJ-1"
        assert rows[1]["jira_key"] == "PROJ-2"

    def test_save_upsert_same_task_twice(self, tmp_path):
        """Test that saving same meeting+task twice results in upsert (one row)."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-upsert"
        items = [
            {"task": "Finalize design", "owner": "Alice", "due": "2026-07-15"}
        ]

        # Save once
        save_action_items(db_path, meeting_uuid, items)

        # Save again with updated owner
        items_updated = [
            {"task": "Finalize design", "owner": "Bob", "due": "2026-07-15"}
        ]
        save_action_items(db_path, meeting_uuid, items_updated)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM action_items")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 1, "Should only have one row (upserted)"
        assert rows[0]["owner"] == "Bob", "Owner should be updated"


@pytest.mark.unit
class TestListPending:
    """Tests for list_pending function."""

    def test_list_pending_empty(self, tmp_path):
        """Test that empty DB returns empty list."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        pending = list_pending(db_path)

        assert pending == []

    def test_list_pending_mixed_status(self, tmp_path):
        """Test that list_pending only returns items with status=pending."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-mixed"
        items = [
            {"task": "Task 1", "owner": "Alice", "due": None},
            {"task": "Task 2", "owner": "Bob", "due": None},
        ]
        save_action_items(db_path, meeting_uuid, items)

        # Mark one as done
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT task_id FROM action_items WHERE task='Task 1'")
        task_id = cursor.fetchone()[0]
        conn.close()

        mark_done(db_path, task_id)

        # List pending should only return Task 2
        pending = list_pending(db_path)

        assert len(pending) == 1
        assert pending[0]["task"] == "Task 2"

    def test_list_pending_sorts_by_due_date(self, tmp_path):
        """Test that list_pending sorts by due_date ASC (NULLs last)."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-sort"
        items = [
            {"task": "Task A", "owner": "Alice", "due": "2026-07-15"},
            {"task": "Task B", "owner": "Bob", "due": "2026-07-10"},
            {"task": "Task C", "owner": "Charlie", "due": None},
        ]
        save_action_items(db_path, meeting_uuid, items)

        pending = list_pending(db_path, sort_by="due_date")

        # Should be sorted: 2026-07-10, 2026-07-15, None
        assert pending[0]["task"] == "Task B"
        assert pending[1]["task"] == "Task A"
        assert pending[2]["task"] == "Task C"
        assert pending[2]["due_date"] is None


@pytest.mark.unit
class TestMarkDone:
    """Tests for mark_done function."""

    def test_mark_done_success(self, tmp_path):
        """Test that mark_done updates status and sets completed_at."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-done"
        items = [{"task": "Close issue", "owner": "Alice", "due": None}]
        save_action_items(db_path, meeting_uuid, items)

        # Get task_id
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT task_id FROM action_items")
        task_id = cursor.fetchone()[0]
        conn.close()

        success = mark_done(db_path, task_id)

        assert success is True

        # Verify status and completed_at are set
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT status, completed_at FROM action_items WHERE task_id=?", (task_id,))
        row = cursor.fetchone()
        conn.close()

        assert row["status"] == "done"
        assert row["completed_at"] is not None

    def test_mark_done_not_found(self, tmp_path):
        """Test that mark_done returns False if task_id doesn't exist."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        success = mark_done(db_path, "nonexistent-id")

        assert success is False


@pytest.mark.unit
class TestGetPendingCount:
    """Tests for get_pending_count function."""

    def test_get_pending_count_returns_correct_number(self, tmp_path):
        """Test that get_pending_count returns count of pending items."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-count"
        items = [
            {"task": "Task 1", "owner": "Alice", "due": None},
            {"task": "Task 2", "owner": "Bob", "due": None},
            {"task": "Task 3", "owner": "Charlie", "due": None},
        ]
        save_action_items(db_path, meeting_uuid, items)

        count = get_pending_count(db_path)

        assert count == 3


@pytest.mark.unit
class TestGetOverdue:
    """Tests for get_overdue function."""

    def test_get_overdue_filters_past_due_dates(self, tmp_path):
        """Test that get_overdue returns only items with due_date < today."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-overdue"
        today = datetime.now().date()
        past_date = (today - timedelta(days=1)).isoformat()
        future_date = (today + timedelta(days=10)).isoformat()

        items = [
            {"task": "Overdue task", "owner": "Alice", "due": past_date},
            {"task": "Future task", "owner": "Bob", "due": future_date},
            {"task": "No due date", "owner": "Charlie", "due": None},
        ]
        save_action_items(db_path, meeting_uuid, items)

        overdue = get_overdue(db_path)

        assert len(overdue) == 1
        assert overdue[0]["task"] == "Overdue task"
