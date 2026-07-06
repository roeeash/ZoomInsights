"""Tests for Slack and Teams notification integration."""

import pytest
import json
from unittest.mock import MagicMock
from zoom_insights.notify import (
    detect_platform,
    post_slack,
    post_teams,
    post_notification,
)


@pytest.mark.unit
class TestDetectPlatform:
    """Tests for platform detection from webhook URL."""

    def test_detect_slack_platform(self):
        """Test detection of Slack webhook URL."""
        url = "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXX"
        assert detect_platform(url) == "slack"

    def test_detect_slack_lowercase(self):
        """Test detection of Slack webhook URL (case-insensitive)."""
        url = "HTTPS://HOOKS.SLACK.COM/services/T00000000/B00000000/XXXXXXXXXXXX"
        assert detect_platform(url) == "slack"

    def test_detect_teams_platform(self):
        """Test detection of Teams webhook URL."""
        url = "https://outlook.webhook.office.com/webhookb2/XXXXXX/IncomingWebhook/XXXXXX"
        assert detect_platform(url) == "teams"

    def test_detect_teams_alternative_format(self):
        """Test detection of Teams webhook URL (alternative format)."""
        url = "https://webhook.office.com/webhookb2/XXXXXX/IncomingWebhook/XXXXXX"
        assert detect_platform(url) == "teams"

    def test_detect_unknown_platform(self):
        """Test detection of unknown webhook URL."""
        url = "https://example.com/webhook"
        assert detect_platform(url) == "unknown"

    def test_detect_empty_url(self):
        """Test detection with empty URL."""
        assert detect_platform("") == "unknown"


@pytest.mark.unit
class TestPostSlack:
    """Tests for Slack notification posting."""

    def test_post_slack_success(self, mocker):
        """Test successful Slack post."""
        # Mock requests.post
        mock_post = mocker.patch("zoom_insights.notify.requests.post")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        insights = {
            "summary": "Test meeting summary",
            "key_points": ["Point 1", "Point 2"],
            "action_items": [
                {"task": "Task 1", "owner": "Alice"},
                {"task": "Task 2", "owner": "Bob"},
            ],
        }
        webhook_url = "https://hooks.slack.com/services/T00000000/B00000000/XXX"

        result = post_slack(insights, webhook_url)

        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == webhook_url
        assert "json" in call_args[1]
        payload = call_args[1]["json"]
        assert "blocks" in payload
        assert len(payload["blocks"]) > 0

    def test_post_slack_timeout(self, mocker):
        """Test Slack post timeout handling."""
        import requests

        mock_post = mocker.patch("zoom_insights.notify.requests.post")
        mock_post.side_effect = requests.exceptions.Timeout()

        insights = {"summary": "Test"}
        webhook_url = "https://hooks.slack.com/services/T00000000/B00000000/XXX"

        result = post_slack(insights, webhook_url)

        assert result is False

    def test_post_slack_http_error(self, mocker):
        """Test Slack post HTTP error handling."""
        mock_post = mocker.patch("zoom_insights.notify.requests.post")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        mock_post.return_value = mock_response

        insights = {"summary": "Test"}
        webhook_url = "https://hooks.slack.com/services/T00000000/B00000000/XXX"

        result = post_slack(insights, webhook_url)

        assert result is False

    def test_post_slack_includes_action_items(self, mocker):
        """Test that Slack payload includes top 3 action items."""
        mock_post = mocker.patch("zoom_insights.notify.requests.post")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        insights = {
            "summary": "Test meeting",
            "action_items": [
                {"task": "Task 1", "owner": None},
                {"task": "Task 2", "owner": "Alice"},
                {"task": "Task 3", "owner": "Bob"},
                {"task": "Task 4", "owner": "Charlie"},
            ],
        }
        webhook_url = "https://hooks.slack.com/services/T00000000/B00000000/XXX"

        result = post_slack(insights, webhook_url)

        assert result is True
        payload = mock_post.call_args[1]["json"]
        # Check that action items are in the payload
        payload_text = json.dumps(payload)
        assert "Task 1" in payload_text
        assert "Task 2" in payload_text
        assert "Task 3" in payload_text
        # Task 4 may or may not be included (top 3 limit)


@pytest.mark.unit
class TestPostTeams:
    """Tests for Teams notification posting."""

    def test_post_teams_success(self, mocker):
        """Test successful Teams post."""
        mock_post = mocker.patch("zoom_insights.notify.requests.post")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        insights = {
            "summary": "Test meeting summary",
            "key_points": ["Point 1", "Point 2"],
            "action_items": [
                {"task": "Task 1", "owner": "Alice"},
                {"task": "Task 2", "owner": "Bob"},
            ],
        }
        webhook_url = "https://outlook.webhook.office.com/webhookb2/XXXXXX/IncomingWebhook/XXXXXX"

        result = post_teams(insights, webhook_url)

        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == webhook_url
        assert "json" in call_args[1]
        payload = call_args[1]["json"]
        assert "@type" in payload
        assert payload["@type"] == "MessageCard"
        assert "sections" in payload

    def test_post_teams_timeout(self, mocker):
        """Test Teams post timeout handling."""
        import requests

        mock_post = mocker.patch("zoom_insights.notify.requests.post")
        mock_post.side_effect = requests.exceptions.Timeout()

        insights = {"summary": "Test"}
        webhook_url = "https://outlook.webhook.office.com/webhookb2/XXX"

        result = post_teams(insights, webhook_url)

        assert result is False

    def test_post_teams_http_error(self, mocker):
        """Test Teams post HTTP error handling."""
        mock_post = mocker.patch("zoom_insights.notify.requests.post")
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        insights = {"summary": "Test"}
        webhook_url = "https://outlook.webhook.office.com/webhookb2/XXX"

        result = post_teams(insights, webhook_url)

        assert result is False

    def test_post_teams_includes_action_items(self, mocker):
        """Test that Teams payload includes top 3 action items."""
        mock_post = mocker.patch("zoom_insights.notify.requests.post")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        insights = {
            "summary": "Test meeting",
            "action_items": [
                {"task": "Task 1", "owner": None},
                {"task": "Task 2", "owner": "Alice"},
                {"task": "Task 3", "owner": "Bob"},
            ],
        }
        webhook_url = "https://outlook.webhook.office.com/webhookb2/XXX"

        result = post_teams(insights, webhook_url)

        assert result is True
        payload = mock_post.call_args[1]["json"]
        payload_text = json.dumps(payload)
        assert "Task 1" in payload_text
        assert "Task 2" in payload_text
        assert "Task 3" in payload_text


@pytest.mark.unit
class TestPostNotification:
    """Tests for unified notification posting."""

    def test_post_notification_slack_dispatch(self, mocker):
        """Test that post_notification dispatches to Slack correctly."""
        mock_post_slack = mocker.patch("zoom_insights.notify.post_slack")
        mock_post_slack.return_value = True

        insights = {"summary": "Test"}
        webhook_url = "https://hooks.slack.com/services/T00000000/B00000000/XXX"

        result = post_notification(insights, webhook_url)

        assert result is True
        mock_post_slack.assert_called_once_with(insights, webhook_url)

    def test_post_notification_teams_dispatch(self, mocker):
        """Test that post_notification dispatches to Teams correctly."""
        mock_post_teams = mocker.patch("zoom_insights.notify.post_teams")
        mock_post_teams.return_value = True

        insights = {"summary": "Test"}
        webhook_url = "https://outlook.webhook.office.com/webhookb2/XXX"

        result = post_notification(insights, webhook_url)

        assert result is True
        mock_post_teams.assert_called_once_with(insights, webhook_url)

    def test_post_notification_unknown_platform(self, mocker):
        """Test that post_notification handles unknown platforms."""
        insights = {"summary": "Test"}
        webhook_url = "https://example.com/webhook"

        result = post_notification(insights, webhook_url)

        assert result is False

    def test_post_notification_empty_webhook(self, mocker):
        """Test that post_notification handles empty webhook URL."""
        insights = {"summary": "Test"}
        webhook_url = ""

        result = post_notification(insights, webhook_url)

        assert result is False

    def test_post_notification_slack_failure_propagates(self, mocker):
        """Test that Slack posting failures are handled."""
        mock_post_slack = mocker.patch("zoom_insights.notify.post_slack")
        mock_post_slack.return_value = False

        insights = {"summary": "Test"}
        webhook_url = "https://hooks.slack.com/services/T00000000/B00000000/XXX"

        result = post_notification(insights, webhook_url)

        assert result is False

    def test_post_notification_teams_failure_propagates(self, mocker):
        """Test that Teams posting failures are handled."""
        mock_post_teams = mocker.patch("zoom_insights.notify.post_teams")
        mock_post_teams.return_value = False

        insights = {"summary": "Test"}
        webhook_url = "https://outlook.webhook.office.com/webhookb2/XXX"

        result = post_notification(insights, webhook_url)

        assert result is False
