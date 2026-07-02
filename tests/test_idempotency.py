"""Tests for idempotency tracking."""

import os
import tempfile
import pytest
from zoom_insights.idempotency import (
    load_completed_uuids,
    mark_completed,
    is_completed,
)


@pytest.mark.unit
class TestLoadCompletedUUIDs:
    """Tests for loading completed UUIDs."""

    def test_load_completed_uuids_empty_log(self):
        """Test loading from non-existent log returns empty set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "completed.log")
            result = load_completed_uuids(log_path)
            assert result == set()

    def test_load_completed_uuids_from_file(self):
        """Test loading UUIDs from existing log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "completed.log")
            with open(log_path, "w") as f:
                f.write("uuid-123\n")
                f.write("uuid-456\n")
                f.write("uuid-789\n")

            result = load_completed_uuids(log_path)

            assert len(result) == 3
            assert "uuid-123" in result
            assert "uuid-456" in result
            assert "uuid-789" in result

    def test_load_completed_uuids_ignores_empty_lines(self):
        """Test that empty lines are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "completed.log")
            with open(log_path, "w") as f:
                f.write("uuid-123\n")
                f.write("\n")
                f.write("uuid-456\n")
                f.write("  \n")
                f.write("uuid-789\n")

            result = load_completed_uuids(log_path)

            assert len(result) == 3

    def test_load_completed_uuids_strips_whitespace(self):
        """Test that whitespace is stripped from UUIDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "completed.log")
            with open(log_path, "w") as f:
                f.write("  uuid-123  \n")
                f.write("uuid-456\n")

            result = load_completed_uuids(log_path)

            assert "uuid-123" in result
            assert "uuid-456" in result


@pytest.mark.unit
class TestMarkCompleted:
    """Tests for marking UUIDs as completed."""

    def test_mark_completed_creates_log(self):
        """Test that log file is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "work", "completed.log")
            mark_completed("uuid-123", log_path)

            assert os.path.exists(log_path)

    def test_mark_completed_appends_uuid(self):
        """Test that UUID is appended to log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "completed.log")
            mark_completed("uuid-123", log_path)

            with open(log_path) as f:
                content = f.read()
            assert "uuid-123\n" in content

    def test_mark_completed_appends_multiple(self):
        """Test that multiple marks are appended."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "completed.log")
            mark_completed("uuid-123", log_path)
            mark_completed("uuid-456", log_path)

            with open(log_path) as f:
                lines = f.readlines()
            assert len(lines) == 2
            assert "uuid-123\n" in lines
            assert "uuid-456\n" in lines


@pytest.mark.unit
class TestIsCompleted:
    """Tests for checking if UUID is completed."""

    def test_is_completed_returns_false_for_empty_log(self):
        """Test that non-existent UUID is not completed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "completed.log")
            result = is_completed("uuid-123", log_path)
            assert result is False

    def test_is_completed_returns_true_for_existing_uuid(self):
        """Test that existing UUID is marked as completed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "completed.log")
            with open(log_path, "w") as f:
                f.write("uuid-123\n")
                f.write("uuid-456\n")

            assert is_completed("uuid-123", log_path) is True
            assert is_completed("uuid-456", log_path) is True

    def test_is_completed_returns_false_for_missing_uuid(self):
        """Test that missing UUID is not marked as completed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "completed.log")
            with open(log_path, "w") as f:
                f.write("uuid-123\n")

            assert is_completed("uuid-789", log_path) is False

    def test_is_completed_idempotent(self):
        """Test that re-running same meeting is idempotent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "completed.log")

            # First run
            if not is_completed("uuid-123", log_path):
                mark_completed("uuid-123", log_path)

            # Second run
            assert is_completed("uuid-123", log_path) is True
            # Deduplicates on second write
            mark_completed("uuid-123", log_path)

            with open(log_path) as f:
                lines = f.readlines()
            assert len(lines) == 1
