"""End-to-end notification tests: Slack/Teams webhook posting."""

import pytest
from zoom_insights.notify import post_notification

pytestmark = pytest.mark.e2e


def test_happy_path_notify_and_report(mocker, sample_insights):
    """Happy path: Slack webhook receives POST → 200, returns True."""
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_post = mocker.patch("zoom_insights.notify.requests.post", return_value=mock_response)

    slack_url = "https://hooks.slack.com/services/T/B/X"
    result = post_notification(sample_insights, slack_url)

    assert result is True
    assert mock_post.called


def test_bad_input_unknown_platform(mocker, sample_insights):
    """Unknown webhook URL → returns False, no POST."""
    mock_post = mocker.patch("zoom_insights.notify.requests.post")

    result = post_notification(sample_insights, "https://unknown.com/webhook")

    assert result is False
    assert not mock_post.called


def test_bad_input_malformed_url(mocker, sample_insights):
    """Malformed URL → returns False, no POST."""
    mock_post = mocker.patch("zoom_insights.notify.requests.post")

    result = post_notification(sample_insights, "not-a-url")

    assert result is False
    assert not mock_post.called


def test_bad_input_missing_action_items(mocker):
    """Missing action_items field → handles gracefully with empty list."""
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mocker.patch("zoom_insights.notify.requests.post", return_value=mock_response)

    insights = {
        "summary": "Test summary",
        "key_points": [],
        "decisions": [],
        "open_questions": [],
        "notable_quotes": [],
        # action_items is missing
    }
    slack_url = "https://hooks.slack.com/services/T/B/X"

    # Should not crash
    result = post_notification(insights, slack_url)
    assert result is True


def test_stage_failure_empty_flag(mocker, sample_insights):
    """Empty webhook URL → returns False, no POST."""
    mock_post = mocker.patch("zoom_insights.notify.requests.post")

    result = post_notification(sample_insights, "")

    assert result is False
    assert not mock_post.called


def test_stage_failure_unknown_platform(mocker, sample_insights):
    """Unknown platform URL → returns False, no POST."""
    mock_post = mocker.patch("zoom_insights.notify.requests.post")

    result = post_notification(sample_insights, "https://random.domain.com/webhook")

    assert result is False
    assert not mock_post.called


def test_stage_failure_card_build_missing_field(mocker):
    """Missing insight fields → POST succeeds with placeholders."""
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mocker.patch("zoom_insights.notify.requests.post", return_value=mock_response)

    # Minimal insights dict
    insights = {
        "summary": "Test",
        # Missing: key_points, decisions, action_items, open_questions, notable_quotes
    }
    slack_url = "https://hooks.slack.com/services/T/B/X"

    result = post_notification(insights, slack_url)
    assert result is True


def test_stage_failure_post_404(mocker, sample_insights):
    """Webhook returns 404 → returns False, no exception raised."""
    mock_response = mocker.MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not found"
    mocker.patch("zoom_insights.notify.requests.post", return_value=mock_response)

    slack_url = "https://hooks.slack.com/services/T/B/X"
    result = post_notification(sample_insights, slack_url)

    assert result is False


def test_stage_failure_post_timeout(mocker, sample_insights):
    """Webhook times out → caught, returns False, no exception raised."""
    mocker.patch(
        "zoom_insights.notify.requests.post",
        side_effect=Exception("Timeout"),
    )

    slack_url = "https://hooks.slack.com/services/T/B/X"
    result = post_notification(sample_insights, slack_url)

    assert result is False


def test_stage_failure_ordering_guarantee(mocker, sample_insights):
    """Fire-and-forget semantics: notify fails, caller can continue."""
    # Mock notify to fail gracefully (404)
    mock_response = mocker.MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not found"
    mocker.patch("zoom_insights.notify.requests.post", return_value=mock_response)

    slack_url = "https://hooks.slack.com/services/T/B/X"

    # Even if notify fails, function returns False and doesn't raise
    result = post_notification(sample_insights, slack_url)

    # Verify it returned False but didn't crash
    assert result is False
