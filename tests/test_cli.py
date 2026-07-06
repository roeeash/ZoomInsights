"""Tests for CLI integration with tracker commands."""

import pytest
import os
import json
from pathlib import Path
from zoom_insights.config import Config
from zoom_insights.tracker import init_db, save_action_items


@pytest.mark.unit
class TestStatusCommand:
    """Tests for 'status' CLI command."""

    def test_status_command_empty(self, mocker, tmp_path, capsys):
        """Test status command with empty tracker shows no pending items."""
        from zoom_insights.cli import _status_command

        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        config = Config(
            zoom_account_id="test",
            zoom_client_id="test",
            zoom_client_secret="test",
            groq_api_key="test",
            tracker_db=db_path,
        )

        _status_command(config)

        captured = capsys.readouterr()
        assert "No pending action items." in captured.out

    def test_status_command_shows_pending(self, mocker, tmp_path, capsys):
        """Test status command displays pending items with correct format."""
        from zoom_insights.cli import _status_command

        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-test"
        items = [
            {"task": "Design review", "owner": "Alice", "due": "2026-07-10"},
            {"task": "Implementation", "owner": "Bob", "due": "2026-07-20"},
        ]
        save_action_items(db_path, meeting_uuid, items)

        config = Config(
            zoom_account_id="test",
            zoom_client_id="test",
            zoom_client_secret="test",
            groq_api_key="test",
            tracker_db=db_path,
        )

        _status_command(config)

        captured = capsys.readouterr()
        assert "Pending Action Items" in captured.out
        assert "Design review" in captured.out
        assert "Implementation" in captured.out
        assert "Alice" in captured.out
        assert "Bob" in captured.out


@pytest.mark.unit
class TestDoneCommand:
    """Tests for 'done' CLI command."""

    def test_done_command_marks_complete(self, mocker, tmp_path, capsys):
        """Test done command marks item as complete."""
        from zoom_insights.cli import _done_command
        from zoom_insights.tracker import list_pending

        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        meeting_uuid = "meeting-test"
        items = [
            {"task": "Close issue", "owner": "Alice", "due": None},
        ]
        save_action_items(db_path, meeting_uuid, items)

        # Get task_id
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT task_id FROM action_items")
        task_id = cursor.fetchone()[0]
        conn.close()

        config = Config(
            zoom_account_id="test",
            zoom_client_id="test",
            zoom_client_secret="test",
            groq_api_key="test",
            tracker_db=db_path,
        )

        _done_command(task_id, config)

        captured = capsys.readouterr()
        assert f"Marked {task_id} as done" in captured.out

        # Verify item is no longer pending
        pending = list_pending(db_path)
        assert len(pending) == 0

    def test_done_command_not_found(self, mocker, tmp_path):
        """Test done command fails when task_id doesn't exist."""
        from zoom_insights.cli import _done_command

        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        config = Config(
            zoom_account_id="test",
            zoom_client_id="test",
            zoom_client_secret="test",
            groq_api_key="test",
            tracker_db=db_path,
        )

        with pytest.raises(SystemExit):
            _done_command("nonexistent-id", config)
