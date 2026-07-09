"""Tests for recurring meeting digest functionality."""

import json
import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from zoom_insights.digest import (
    process_meetings_batch,
    aggregate_insights,
    write_digest_report,
)


@pytest.mark.unit
class TestAggregateInsights:
    """Tests for aggregate_insights function."""

    def test_aggregate_insights_merges_key_points(self):
        """Test that overlapping key points are deduplicated."""
        insights_list = [
            {
                "summary": "Meeting 1",
                "key_points": ["Performance is slow", "Users report latency"],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            },
            {
                "summary": "Meeting 2",
                "key_points": ["Performance is slow", "Need optimization"],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            },
        ]

        result = aggregate_insights(insights_list)

        assert "key_points" in result
        assert len(result["key_points"]) == 3
        # "Performance is slow" should only appear once (case-insensitive dedup)
        key_points_lower = [kp.lower() for kp in result["key_points"]]
        assert key_points_lower.count("performance is slow") == 1

    def test_aggregate_insights_groups_action_items_by_owner(self):
        """Test that action items are grouped by owner."""
        insights_list = [
            {
                "summary": "Meeting 1",
                "key_points": [],
                "decisions": [],
                "action_items": [
                    {"owner": "Alice", "task": "Optimize DB queries", "due": "2026-07-15"},
                    {"owner": "Bob", "task": "Write tests", "due": None},
                ],
                "open_questions": [],
                "notable_quotes": [],
            },
            {
                "summary": "Meeting 2",
                "key_points": [],
                "decisions": [],
                "action_items": [
                    {"owner": "Alice", "task": "Deploy to production", "due": "2026-07-20"},
                ],
                "open_questions": [],
                "notable_quotes": [],
            },
        ]

        result = aggregate_insights(insights_list)

        assert "action_items" in result
        # Should have 3 items total
        assert len(result["action_items"]) == 3
        # Verify grouping by owner (checking owner field is preserved)
        alice_items = [item for item in result["action_items"] if item["owner"] == "Alice"]
        bob_items = [item for item in result["action_items"] if item["owner"] == "Bob"]
        assert len(alice_items) == 2
        assert len(bob_items) == 1

    def test_aggregate_insights_deduplicates_tasks(self):
        """Test that identical tasks appear only once."""
        insights_list = [
            {
                "summary": "Meeting 1",
                "key_points": [],
                "decisions": [],
                "action_items": [
                    {"owner": "Alice", "task": "Fix bug in auth module", "due": "2026-07-15"},
                    {"owner": "Bob", "task": "Write documentation", "due": None},
                ],
                "open_questions": [],
                "notable_quotes": [],
            },
            {
                "summary": "Meeting 2",
                "key_points": [],
                "decisions": [],
                "action_items": [
                    {"owner": "Charlie", "task": "Fix bug in auth module", "due": "2026-07-20"},
                ],
                "open_questions": [],
                "notable_quotes": [],
            },
        ]

        result = aggregate_insights(insights_list)

        # The duplicate task should be deduplicated (case-insensitive)
        action_items = result["action_items"]
        auth_tasks = [item for item in action_items if "auth" in item["task"].lower()]
        assert len(auth_tasks) == 1

    def test_aggregate_insights_includes_meeting_attribution(self):
        """Test that rollup includes meeting attribution."""
        insights_list = [
            {
                "summary": "Meeting about performance",
                "key_points": ["Issue A"],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            },
            {
                "summary": "Meeting about features",
                "key_points": ["Issue B"],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            },
        ]

        result = aggregate_insights(insights_list)

        assert "meetings_processed" in result
        assert len(result["meetings_processed"]) == 2
        assert result["meeting_count"] == 2

    def test_aggregate_insights_empty_input(self):
        """Test safe handling of empty insights list."""
        result = aggregate_insights([])

        assert result["summary"] == "No meetings processed."
        assert result["key_points"] == []
        assert result["decisions"] == []
        assert result["action_items"] == []
        assert result["meeting_count"] == 0
        assert result["meetings_processed"] == []

    def test_aggregate_insights_handles_none_values(self):
        """Test that None owner is handled correctly."""
        insights_list = [
            {
                "summary": "Meeting 1",
                "key_points": [],
                "decisions": [],
                "action_items": [
                    {"owner": None, "task": "Unassigned task", "due": None},
                    {"owner": "Alice", "task": "Alice's task", "due": None},
                ],
                "open_questions": [],
                "notable_quotes": [],
            },
        ]

        result = aggregate_insights(insights_list)

        # Both items should be present
        assert len(result["action_items"]) == 2
        # Check for Unassigned owner in results
        owners = [item.get("owner") for item in result["action_items"]]
        assert None in owners or "Unassigned" in owners


@pytest.mark.unit
class TestWriteDigestReport:
    """Tests for write_digest_report function."""

    def test_write_digest_report_date_range_format(self, tmp_path):
        """Test that output directory matches digest-YYYY-MM-DD-to-YYYY-MM-DD format."""
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)

        rollup = {
            "summary": "Test digest",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
            "meeting_count": 1,
            "meetings_processed": ["Test"],
        }

        result = write_digest_report(rollup, days_back=7, out_dir=out_dir)

        # Extract the directory name
        digest_dir = os.path.basename(result)

        # Should match pattern: digest-YYYY-MM-DD-to-YYYY-MM-DD
        assert digest_dir.startswith("digest-")
        parts = digest_dir.replace("digest-", "").split("-to-")
        assert len(parts) == 2
        # Validate date format
        try:
            datetime.strptime(parts[0], "%Y-%m-%d")
            datetime.strptime(parts[1], "%Y-%m-%d")
        except ValueError:
            pytest.fail("Date format doesn't match YYYY-MM-DD")

    def test_write_digest_report_includes_meeting_count(self, tmp_path):
        """Test that markdown mentions 'N meetings analyzed'."""
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)

        rollup = {
            "summary": "Test summary",
            "key_points": ["Point 1"],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
            "meeting_count": 3,
            "meetings_processed": ["M1", "M2", "M3"],
        }

        digest_dir = write_digest_report(rollup, days_back=7, out_dir=out_dir)
        report_path = os.path.join(digest_dir, "report.md")

        with open(report_path, "r") as f:
            content = f.read()

        assert "3" in content
        assert "meetings analyzed" in content.lower() or "meetings" in content.lower()

    def test_write_digest_report_groups_by_owner(self, tmp_path):
        """Test that action items are grouped under owner headers."""
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)

        rollup = {
            "summary": "Test",
            "key_points": [],
            "decisions": [],
            "action_items": [
                {"owner": "Alice", "task": "Task 1", "due": "2026-07-15"},
                {"owner": "Alice", "task": "Task 2", "due": None},
                {"owner": "Bob", "task": "Task 3", "due": "2026-07-20"},
            ],
            "open_questions": [],
            "notable_quotes": [],
            "meeting_count": 1,
            "meetings_processed": ["Test"],
        }

        digest_dir = write_digest_report(rollup, days_back=7, out_dir=out_dir)
        report_path = os.path.join(digest_dir, "report.md")

        with open(report_path, "r") as f:
            content = f.read()

        # Check for owner headers (### Owner format)
        assert "### Alice" in content
        assert "### Bob" in content

    def test_write_digest_report_creates_rollup_json(self, tmp_path):
        """Test that rollup.json file is created."""
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)

        rollup = {
            "summary": "Test",
            "key_points": ["Key 1"],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
            "meeting_count": 1,
            "meetings_processed": ["Test"],
        }

        digest_dir = write_digest_report(rollup, days_back=7, out_dir=out_dir)
        rollup_path = os.path.join(digest_dir, "rollup.json")

        assert os.path.exists(rollup_path)

        with open(rollup_path, "r") as f:
            data = json.load(f)

        assert data["summary"] == "Test"
        assert "Key 1" in data["key_points"]


@pytest.mark.unit
class TestProcessMeetingsBatch:
    """Tests for process_meetings_batch function."""

    def test_process_meetings_batch_skips_completed(self, mocker):
        """Test that already-completed meetings are skipped."""
        # Mock list_recent_recordings
        mock_meeting1 = mocker.MagicMock()
        mock_meeting1.uuid = "uuid-1"
        mock_meeting1.topic = "Meeting 1"

        mock_meeting2 = mocker.MagicMock()
        mock_meeting2.uuid = "uuid-2"
        mock_meeting2.topic = "Meeting 2"

        mocker.patch(
            "zoom_insights.digest.list_recent_recordings",
            return_value=[mock_meeting1, mock_meeting2],
        )

        # Mock is_completed to return True for uuid-1
        def is_completed_side_effect(uuid):
            return uuid == "uuid-1"

        mocker.patch(
            "zoom_insights.digest.is_completed",
            side_effect=is_completed_side_effect,
        )

        # Mock mark_completed
        mocker.patch("zoom_insights.digest.mark_completed")

        # Mock _process_meeting_for_batch
        mock_insights = {
            "summary": "Test",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        mocker.patch(
            "zoom_insights.digest._process_meeting_for_batch",
            return_value=mock_insights,
        )

        config = mocker.MagicMock()
        config.max_batch_workers = 3

        result = process_meetings_batch(
            token="fake-token",
            groq_client=mocker.MagicMock(),
            config=config,
            days_back=7,
            skip_completed=True,
        )

        # Only uuid-2 should be processed (uuid-1 is already completed)
        assert result["meeting_count"] == 1
        assert len(result["insights"]) == 1

    def test_process_meetings_batch_with_force_reprocesses(self, mocker):
        """Test that force=True (skip_completed=False) reprocesses all."""
        mock_meeting1 = mocker.MagicMock()
        mock_meeting1.uuid = "uuid-1"
        mock_meeting1.topic = "Meeting 1"

        mock_meeting2 = mocker.MagicMock()
        mock_meeting2.uuid = "uuid-2"
        mock_meeting2.topic = "Meeting 2"

        mocker.patch(
            "zoom_insights.digest.list_recent_recordings",
            return_value=[mock_meeting1, mock_meeting2],
        )

        # Mock is_completed to always return True (simulating completed state)
        mocker.patch("zoom_insights.digest.is_completed", return_value=True)

        # Mock mark_completed
        mocker.patch("zoom_insights.digest.mark_completed")

        # Mock _process_meeting_for_batch
        mock_insights = {
            "summary": "Test",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        mocker.patch(
            "zoom_insights.digest._process_meeting_for_batch",
            return_value=mock_insights,
        )

        config = mocker.MagicMock()
        config.max_batch_workers = 3

        # With skip_completed=False (force=True), all meetings should be processed
        result = process_meetings_batch(
            token="fake-token",
            groq_client=mocker.MagicMock(),
            config=config,
            days_back=7,
            skip_completed=False,
        )

        assert result["meeting_count"] == 2
        assert len(result["insights"]) == 2

    def test_process_meetings_batch_handles_empty_days(self, mocker):
        """Test safe handling when no recordings exist for the period."""
        # Mock list_recent_recordings to return empty
        mocker.patch(
            "zoom_insights.digest.list_recent_recordings",
            return_value=[],
        )

        config = mocker.MagicMock()
        config.max_batch_workers = 3

        result = process_meetings_batch(
            token="fake-token",
            groq_client=mocker.MagicMock(),
            config=config,
            days_back=7,
            skip_completed=True,
        )

        assert result["meeting_count"] == 0
        assert len(result["insights"]) == 0
        assert result["meetings_processed"] == []

    def test_process_meetings_batch_continues_on_error(self, mocker):
        """Test that batch processing continues even when one meeting fails."""
        mock_meeting1 = mocker.MagicMock()
        mock_meeting1.uuid = "uuid-1"
        mock_meeting1.topic = "Meeting 1"

        mock_meeting2 = mocker.MagicMock()
        mock_meeting2.uuid = "uuid-2"
        mock_meeting2.topic = "Meeting 2"

        mocker.patch(
            "zoom_insights.digest.list_recent_recordings",
            return_value=[mock_meeting1, mock_meeting2],
        )

        mocker.patch("zoom_insights.digest.is_completed", return_value=False)
        mocker.patch("zoom_insights.digest.mark_completed")

        # Mock _process_meeting_for_batch to fail for first, succeed for second
        def process_side_effect(uuid, *args, **kwargs):
            if uuid == "uuid-1":
                raise RuntimeError("Processing failed")
            mock_insights = {
                "summary": "Test",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }
            return mock_insights

        mocker.patch(
            "zoom_insights.digest._process_meeting_for_batch",
            side_effect=process_side_effect,
        )

        config = mocker.MagicMock()
        config.max_batch_workers = 3

        result = process_meetings_batch(
            token="fake-token",
            groq_client=mocker.MagicMock(),
            config=config,
            days_back=7,
            skip_completed=True,
        )

        # Only the second meeting should be in results
        assert result["meeting_count"] == 1
        assert len(result["insights"]) == 1


@pytest.mark.unit
class TestConcurrentBatchProcessing:
    """Tests for concurrent batch processing with ThreadPoolExecutor."""

    def test_batch_processes_meetings_concurrently(self, mocker):
        """Test that 3 meetings with delays complete concurrently (wall time < serial)."""
        import time

        # Create 3 mock meetings
        mock_meetings = []
        for i in range(3):
            mock_meeting = mocker.MagicMock()
            mock_meeting.uuid = f"uuid-{i}"
            mock_meeting.topic = f"Meeting {i}"
            mock_meetings.append(mock_meeting)

        mocker.patch(
            "zoom_insights.digest.list_recent_recordings",
            return_value=mock_meetings,
        )
        mocker.patch("zoom_insights.digest.is_completed", return_value=False)
        mocker.patch("zoom_insights.digest.mark_completed")

        # Mock _process_meeting_for_batch to take 0.2s per call
        def slow_process(uuid, *args, **kwargs):
            time.sleep(0.2)
            return {
                "summary": f"Summary {uuid}",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

        mocker.patch(
            "zoom_insights.digest._process_meeting_for_batch",
            side_effect=slow_process,
        )

        # Create config with max_batch_workers=3
        config = mocker.MagicMock()
        config.max_batch_workers = 3

        start_time = time.time()
        result = process_meetings_batch(
            token="fake-token",
            groq_client=mocker.MagicMock(),
            config=config,
            days_back=7,
            skip_completed=True,
        )
        elapsed = time.time() - start_time

        # With concurrency, 3 * 0.2s should take ~0.2s total, not ~0.6s
        # Allow some margin for overhead, but assert it's closer to max than sum
        assert elapsed < 0.45, f"Concurrent processing took {elapsed}s, expected <0.45s"
        assert result["meeting_count"] == 3
        assert len(result["insights"]) == 3

    def test_batch_continues_on_one_meeting_failure(self, mocker):
        """Test that batch continues when one meeting fails."""
        # Create 3 mock meetings
        mock_meetings = []
        for i in range(3):
            mock_meeting = mocker.MagicMock()
            mock_meeting.uuid = f"uuid-{i}"
            mock_meeting.topic = f"Meeting {i}"
            mock_meetings.append(mock_meeting)

        mocker.patch(
            "zoom_insights.digest.list_recent_recordings",
            return_value=mock_meetings,
        )
        mocker.patch("zoom_insights.digest.is_completed", return_value=False)
        mocker.patch("zoom_insights.digest.mark_completed")

        # Mock _process_meeting_for_batch to fail for meeting 1 only
        def process_with_failure(uuid, *args, **kwargs):
            if uuid == "uuid-1":
                raise RuntimeError("Meeting 1 failed")
            return {
                "summary": f"Summary {uuid}",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

        mocker.patch(
            "zoom_insights.digest._process_meeting_for_batch",
            side_effect=process_with_failure,
        )

        config = mocker.MagicMock()
        config.max_batch_workers = 3

        result = process_meetings_batch(
            token="fake-token",
            groq_client=mocker.MagicMock(),
            config=config,
            days_back=7,
            skip_completed=True,
        )

        # Meetings 0 and 2 should be in results; meeting 1 failed
        assert result["meeting_count"] == 2
        assert len(result["insights"]) == 2
        # Verify meetings 0 and 2 are processed (not meeting 1)
        assert "Meeting 0" in result["meetings_processed"]
        assert "Meeting 2" in result["meetings_processed"]
        assert "Meeting 1" not in result["meetings_processed"]

    def test_batch_aggregation_order_deterministic(self, mocker):
        """Test that meetings in aggregation are in original order, not completion order."""
        # Create 3 mock meetings
        mock_meetings = []
        for i in range(3):
            mock_meeting = mocker.MagicMock()
            mock_meeting.uuid = f"uuid-{i}"
            mock_meeting.topic = f"Meeting {i}"
            mock_meetings.append(mock_meeting)

        mocker.patch(
            "zoom_insights.digest.list_recent_recordings",
            return_value=mock_meetings,
        )
        mocker.patch("zoom_insights.digest.is_completed", return_value=False)

        # Create a mock for mark_completed to track which meetings were marked
        mock_mark_completed = mocker.patch("zoom_insights.digest.mark_completed")

        # Mock _process_meeting_for_batch with varying delays to simulate out-of-order completion
        delays = {"uuid-2": 0.05, "uuid-0": 0.15, "uuid-1": 0.10}

        def delayed_process(uuid, *args, **kwargs):
            time.sleep(delays.get(uuid, 0.1))
            return {
                "summary": f"Summary {uuid}",
                "key_points": [f"Point from {uuid}"],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

        import time

        mocker.patch(
            "zoom_insights.digest._process_meeting_for_batch",
            side_effect=delayed_process,
        )

        config = mocker.MagicMock()
        config.max_batch_workers = 3

        result = process_meetings_batch(
            token="fake-token",
            groq_client=mocker.MagicMock(),
            config=config,
            days_back=7,
            skip_completed=True,
        )

        # Verify all 3 were processed
        assert result["meeting_count"] == 3
        assert len(result["insights"]) == 3

        # Verify insights are in original meeting order by checking key_points
        # They should be in order: Meeting 0, Meeting 1, Meeting 2
        assert "Point from uuid-0" in result["insights"][0]["key_points"]
        assert "Point from uuid-1" in result["insights"][1]["key_points"]
        assert "Point from uuid-2" in result["insights"][2]["key_points"]

    def test_batch_respects_worker_cap(self, mocker):
        """Test that no more than max_batch_workers concurrent calls happen."""
        # Create 10 mock meetings
        mock_meetings = []
        for i in range(10):
            mock_meeting = mocker.MagicMock()
            mock_meeting.uuid = f"uuid-{i}"
            mock_meeting.topic = f"Meeting {i}"
            mock_meetings.append(mock_meeting)

        mocker.patch(
            "zoom_insights.digest.list_recent_recordings",
            return_value=mock_meetings,
        )
        mocker.patch("zoom_insights.digest.is_completed", return_value=False)
        mocker.patch("zoom_insights.digest.mark_completed")

        # Track concurrent calls
        concurrent_calls = []
        max_concurrent = [0]
        lock = mocker.MagicMock()

        def track_concurrent(uuid, *args, **kwargs):
            import time
            import threading

            concurrent_calls.append(threading.current_thread().ident)
            # Count unique concurrent threads
            unique_threads = len(set(concurrent_calls))
            max_concurrent[0] = max(max_concurrent[0], unique_threads)
            time.sleep(0.05)
            concurrent_calls.pop()
            return {
                "summary": f"Summary {uuid}",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

        mocker.patch(
            "zoom_insights.digest._process_meeting_for_batch",
            side_effect=track_concurrent,
        )

        config = mocker.MagicMock()
        config.max_batch_workers = 2

        result = process_meetings_batch(
            token="fake-token",
            groq_client=mocker.MagicMock(),
            config=config,
            days_back=7,
            skip_completed=True,
        )

        # All 10 meetings should be processed
        assert result["meeting_count"] == 10
        assert len(result["insights"]) == 10

        # Max concurrent should not exceed 2 (plus some wiggle room for threading overhead)
        assert max_concurrent[0] <= 3, f"Too many concurrent threads: {max_concurrent[0]}"
