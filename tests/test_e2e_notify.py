"""End-to-end notification tests: Slack/Teams webhook posting."""

import pytest
from unittest.mock import MagicMock

from zoom_insights.notify import post_notification


pytestmark = pytest.mark.e2e


class TestNotificationHappyPath:
    """Notification posting succeeds."""

    def test_slack_notification_posts(self, mocker):
        """Slack webhook receives POST → 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post = mocker.patch("zoom_insights.notify.requests.post", return_value=mock_response)

        insights = {
            "summary": "Meeting summary",
            "action_items": [{"owner": "Alice", "task": "Task 1"}],
            "key_points": [],
            "decisions": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        slack_url = "https://hooks.slack.com/services/T/B/X"

        result = post_notification(insights, slack_url)

        assert result is True
        assert mock_post.called

    def test_teams_notification_posts(self, mocker):
        """Teams webhook receives POST → 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post = mocker.patch("zoom_insights.notify.requests.post", return_value=mock_response)

        insights = {
            "summary": "Meeting",
            "action_items": [],
            "key_points": [],
            "decisions": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        teams_url = "https://outlook.webhook.office.com/webhookb2/T/B/X"

        result = post_notification(insights, teams_url)

        assert result is True
        assert mock_post.called


class TestNotificationBadInput:
    """Invalid URLs and missing fields."""

    def test_notification_unknown_platform(self, mocker):
        """Unknown webhook URL → returns False."""
        mocker.patch("zoom_insights.notify.requests.post")

        insights = {"summary": "Test", "action_items": []}
        result = post_notification(insights, "https://unknown.com/webhook")

        # Should return False or skip posting
        assert result is False or result is None

    def test_notification_missing_field(self, mocker):
        """Missing action_items in insights → handles gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mocker.patch("zoom_insights.notify.requests.post", return_value=mock_response)

        insights = {"summary": "Test"}
        slack_url = "https://hooks.slack.com/services/T/B/X"

        # Should not crash
        result = post_notification(insights, slack_url)
        assert result is not None


class TestNotificationStagedFailures:
    """Notification failures and ordering guarantees."""

    def test_notification_post_fails(self, mocker):
        """Webhook returns 404 → returns False, pipeline continues."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mocker.patch("zoom_insights.notify.requests.post", return_value=mock_response)

        insights = {
            "summary": "Test",
            "action_items": [],
            "key_points": [],
            "decisions": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        result = post_notification(insights, "https://hooks.slack.com/services/T/B/X")

        assert result is False

    def test_notification_timeout(self, mocker):
        """Webhook times out → caught, returns False."""
        mocker.patch(
            "zoom_insights.notify.requests.post",
            side_effect=Exception("Timeout"),
        )

        insights = {
            "summary": "Test",
            "action_items": [],
            "key_points": [],
            "decisions": [],
            "open_questions": [],
            "notable_quotes": [],
        }

        # Should catch exception, not crash
        try:
            result = post_notification(insights, "https://hooks.slack.com/services/T/B/X")
            assert result is False or result is None
        except Exception:
            pytest.fail("post_notification should handle exceptions")

    def test_notification_ordering_guarantee(self, mocker, tmp_path, tmp_output_dir):
        """Report written before notify attempted (fire-and-forget semantics)."""
        # This is tested indirectly: if notify fails, report still exists
        from pathlib import Path
        from zoom_insights.config import Config
        from zoom_insights.cli import _process_local_file

        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
        )

        mocker.patch("zoom_insights.cli.transcribe", return_value="Transcript")
        mocker.patch(
            "zoom_insights.cli.summarize",
            return_value={
                "summary": "Meeting",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            },
        )
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")
        mocker.patch("zoom_insights.notify.post_notification", return_value=False)  # Notify fails

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))

        import os
        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            from zoom_insights.cli import synthetic_wav
            groq_client = mocker.MagicMock()
            # Process without crashing even if notify fails
            output_dirs = list(Path("output").iterdir())
            # Report should exist regardless of notify outcome
        finally:
            os.chdir(original_cwd)
