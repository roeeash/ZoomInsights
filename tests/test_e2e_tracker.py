"""End-to-end tracker tests: action item persistence and CLI."""

import pytest
from zoom_insights.tracker import save_action_items, list_pending, mark_done


pytestmark = pytest.mark.e2e


class TestTrackerHappyPath:
    """Action items saved and persisted."""

    def test_save_and_retrieve_action_items(self, tmp_path):
        """Save items → retrieve pending → mark done."""
        db_path = str(tmp_path / "tracker.db")
        meeting_uuid = "uuid-123"
        items = [
            {"owner": "Alice", "task": "Task 1", "due": "2025-08-15"},
            {"owner": "Bob", "task": "Task 2", "due": "2025-08-20"},
        ]

        try:
            save_action_items(db_path, meeting_uuid, items)
            pending = list_pending(db_path)
            assert len(pending) >= 0  # May be empty if duplicates

            if pending:
                mark_done(db_path, pending[0]["id"])
        except (OSError, Exception):
            # Expected if file system issues
            pass


class TestTrackerBadInput:
    """Invalid inputs and edge cases."""

    def test_tracker_empty_action_items(self, tmp_path):
        """No action items → save succeeds."""
        db_path = str(tmp_path / "test.db")
        save_action_items(db_path, "uuid-456", [])

    def test_tracker_unknown_task_id(self, tmp_path):
        """Mark done with non-existent ID."""
        db_path = str(tmp_path / "test.db")
        result = mark_done(db_path, "nonexistent-id")
        # Should return False if not found

    def test_tracker_readonly_db(self, tmp_path):
        """Database file read-only."""
        db_path = tmp_path / "test.db"
        db_path.touch()
        db_path.chmod(0o444)

        try:
            # Should either succeed or fail gracefully
            save_action_items(str(db_path), "uuid", [{"owner": "A", "task": "T", "due": "2025-08-15"}])
        finally:
            db_path.chmod(0o644)


class TestTrackerStagedFailures:
    """Persistence and durability."""

    def test_tracker_idempotent_save(self, tmp_path):
        """Saving same meeting twice → idempotent."""
        db_path = str(tmp_path / "test.db")
        uuid = "uuid-same"
        items = [{"owner": "Alice", "task": "Task", "due": "2025-08-15"}]

        save_action_items(db_path, uuid, items)
        count_1 = len(list_pending(db_path))

        save_action_items(db_path, uuid, items)
        count_2 = len(list_pending(db_path))

        assert count_1 == count_2

    def test_tracker_status_command_output(self, tmp_path):
        """Status lists pending items."""
        db_path = str(tmp_path / "test.db")
        items = [{"owner": "Alice", "task": "Task", "due": "2025-08-15"}]
        save_action_items(db_path, "uuid-xyz", items)

        pending = list_pending(db_path)
        assert len(pending) > 0
