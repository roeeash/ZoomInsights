"""End-to-end tests for the Zoom Insights pipeline.

Tests the full flow: local recording → insights.json → Jira ticket creation.
"""

import pytest
import json
import os
import tempfile
from groq import Groq
from zoom_insights.cli import _process_local_file, _export_to_jira
from zoom_insights.config import Config


def bad_request_response(mocker):
    """Factory: mock response with 400 status."""
    resp = mocker.MagicMock()
    resp.status_code = 400
    resp.text = "Bad Request"
    return resp


def server_error_response(mocker):
    """Factory: mock response with 500 status."""
    resp = mocker.MagicMock()
    resp.status_code = 500
    resp.text = "Internal Server Error"
    return resp


@pytest.mark.e2e
def test_e2e_happy_flow(groq_api_key, tmp_output_dir, mocker):
    """E2E happy flow: real audio → real Groq transcription → real Groq LLM → real file output → mocked Jira.

    Uses real Groq APIs and sample_meeting.mp4 audio file. Mocks only idempotency
    (to avoid duplicate processing) and Jira HTTP calls (to prevent noise on test.atlassian.net).
    Allows ffmpeg, transcription, summarization, and file writing to run for real.
    """
    # Get sample meeting file
    sample_file = os.path.join(
        os.path.dirname(__file__),
        "sample_data",
        "sample_meeting.mp4"
    )
    if not os.path.exists(sample_file):
        pytest.skip(f"Sample audio file not found: {sample_file}")

    # Mock idempotency checks (always not completed)
    mocker.patch("zoom_insights.cli.is_completed", return_value=False)
    mocker.patch("zoom_insights.cli.mark_completed")

    # Mock Jira credential validation (requests.get) to succeed
    mock_get_response = mocker.MagicMock()
    mock_get_response.status_code = 200
    mocker.patch("zoom_insights.cli.requests.get", return_value=mock_get_response)

    # Mock Jira HTTP layer to return successful ticket creation (status 201)
    mock_response = mocker.MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"key": "PROJ-1"}
    mock_post = mocker.patch("zoom_insights.jira_export.requests.post", return_value=mock_response)

    # Real Groq client (uses real API with provided key)
    groq_client = Groq(api_key=groq_api_key)

    # Real config with test Jira credentials
    config = Config(
        zoom_account_id="test",
        zoom_client_id="test",
        zoom_client_secret="test",
        groq_api_key=groq_api_key,
        jira_url="https://test.atlassian.net",
        jira_email="test@test.com",
        jira_api_token="test_token",
        jira_project_key="TEST",
    )

    # Execute: _process_local_file with jira=True
    # This will:
    # - Actually call ffmpeg to compress audio
    # - Actually call Groq Whisper API to transcribe
    # - Actually call Groq LLM API to summarize
    # - Actually write report to disk
    # - Call mocked requests.post for Jira
    _process_local_file(
        sample_file,
        groq_client,
        work_dir=tmp_output_dir,
        title_override="E2E Test Meeting",
        force=True,
        jira=True,
        config=config,
    )

    # Assertions
    # 1. Verify requests.post was called (Jira API was invoked)
    assert mock_post.called, "requests.post should have been called for Jira API"

    # 2. Report file should exist in output/{sanitized_title}/insights.json
    from zoom_insights.report import sanitize_topic
    sanitized_title = sanitize_topic("E2E Test Meeting")
    insights_file = os.path.join("output", sanitized_title, "insights.json")
    assert os.path.exists(insights_file), f"insights.json should be written to {insights_file}"

    # 3. Verify insights has required keys
    with open(insights_file, "r") as f:
        insights = json.load(f)
    assert "summary" in insights, "insights should have 'summary' key"
    assert "action_items" in insights, "insights should have 'action_items' key"
    assert isinstance(insights["summary"], str), "summary should be a string"
    assert isinstance(insights["action_items"], list), "action_items should be a list"

    # 4. If there are action items, verify Jira was called to create tickets
    if insights["action_items"]:
        assert mock_post.call_count >= 1, "requests.post should have been called for each action item"


@pytest.mark.e2e
def test_e2e_bad_credentials(groq_api_key, tmp_output_dir, mocker):
    """E2E with bad Jira credentials: should raise RuntimeError before running pipeline.

    Mocks requests.get (credential validation) to return 401 Unauthorized.
    Expects RuntimeError to be raised before any Groq/ffmpeg calls.
    No output should be created.
    """
    # Get sample meeting file
    sample_file = os.path.join(
        os.path.dirname(__file__),
        "sample_data",
        "sample_meeting.mp4"
    )
    if not os.path.exists(sample_file):
        pytest.skip(f"Sample audio file not found: {sample_file}")

    # Mock idempotency checks
    mocker.patch("zoom_insights.cli.is_completed", return_value=False)
    mocker.patch("zoom_insights.cli.mark_completed")

    # Mock requests.get (credential validation) to return 401 Unauthorized
    mock_get_response = mocker.MagicMock()
    mock_get_response.status_code = 401
    mocker.patch("zoom_insights.cli.requests.get", return_value=mock_get_response)

    # Real Groq client
    groq_client = Groq(api_key=groq_api_key)

    # Config with invalid Jira token
    config = Config(
        zoom_account_id="test",
        zoom_client_id="test",
        zoom_client_secret="test",
        groq_api_key=groq_api_key,
        jira_url="https://test.atlassian.net",
        jira_email="test@test.com",
        jira_api_token="invalid_token",
        jira_project_key="TEST",
    )

    # Execute: expect RuntimeError during credential validation (before pipeline runs)
    with pytest.raises(RuntimeError, match="Jira authentication failed"):
        _process_local_file(
            sample_file,
            groq_client,
            work_dir=tmp_output_dir,
            title_override="Bad Creds Test",
            force=True,
            jira=True,
            config=config,
        )

    # Assertions: no output should have been created (pipeline never ran)
    from zoom_insights.report import sanitize_topic
    sanitized_title = sanitize_topic("Bad Creds Test")
    insights_file = os.path.join("output", sanitized_title, "insights.json")
    assert not os.path.exists(insights_file), "No output should be written when credential validation fails"


@pytest.mark.e2e
def test_e2e_nonexistent_file(tmp_output_dir, mock_groq_client, mock_config):
    """E2E: processing nonexistent file raises RuntimeError and doesn't call Groq.

    No credential fixtures needed (no API calls).
    """
    nonexistent = os.path.join(tmp_output_dir, "does_not_exist.wav")

    # Execute
    with pytest.raises(RuntimeError, match="File not found"):
        _process_local_file(
            nonexistent,
            mock_groq_client,
            work_dir=tmp_output_dir,
            config=mock_config,
        )

    # Groq client should not have been called
    mock_groq_client.audio.transcriptions.create.assert_not_called()


@pytest.mark.e2e
def test_e2e_malformed_insights(synthetic_wav, tmp_output_dir, mocker, mock_config):
    """E2E: Groq returns invalid insights (missing fields); fallback is used.

    Mocks Groq to return JSON that doesn't match schema, verifies write_report
    is still called with a fallback insights object (action_items = []).
    """
    # Mock ffmpeg and work directory
    mocker.patch("zoom_insights.cli.require_ffmpeg")
    mocker.patch("zoom_insights.cli.ensure_work_dir", return_value=tmp_output_dir)
    mocker.patch("zoom_insights.cli.to_compressed_audio")
    mocker.patch("zoom_insights.cli.maybe_segment", return_value=[synthetic_wav])
    mocker.patch("zoom_insights.cli.is_completed", return_value=False)
    mocker.patch("zoom_insights.cli.mark_completed")

    write_report_mock = mocker.patch("zoom_insights.cli.write_report")

    # Mock Groq client
    mock_groq = mocker.MagicMock()
    mock_groq.audio.transcriptions.create.return_value = "Sample transcript"

    # For map phase: return valid summaries
    valid_map_response = mocker.MagicMock()
    valid_map_response.choices = [mocker.MagicMock(message=mocker.MagicMock(content="Map summary"))]

    # For reduce phase: return JSON with missing required fields (invalid schema)
    invalid_insights = {
        "summary": "Invalid insights",
        # Missing: key_points, decisions, action_items, open_questions, notable_quotes
    }
    invalid_reduce_response = mocker.MagicMock()
    invalid_reduce_response.choices = [mocker.MagicMock(
        message=mocker.MagicMock(content=json.dumps(invalid_insights))
    )]

    # For repair attempt: also return invalid JSON
    repair_response = mocker.MagicMock()
    repair_response.choices = [mocker.MagicMock(message=mocker.MagicMock(content="not valid json"))]

    # Chat completions side effect
    mock_groq.chat.completions.create.side_effect = [
        valid_map_response,       # Map phase
        invalid_reduce_response,  # Reduce phase (invalid schema)
        repair_response,          # Repair attempt (bad JSON)
    ]

    # Execute
    _process_local_file(
        synthetic_wav,
        mock_groq,
        work_dir=tmp_output_dir,
        title_override="Malformed Test",
        force=True,
        config=mock_config,
    )

    # Verify write_report was called
    assert write_report_mock.called, "write_report should have been called"

    # Check that insights has fallback values
    call_args = write_report_mock.call_args
    _, _, insights, _ = call_args[0]

    # With invalid schema, fallback should be used (action_items = [])
    assert insights["action_items"] == [], "Invalid insights should trigger fallback with empty action_items"


@pytest.mark.e2e
@pytest.mark.parametrize("case_name,build_response", [
    ("bad_request", bad_request_response),
    ("server_error", server_error_response),
], ids=["400_bad_request", "500_server_error"])
def test_e2e_jira_ticket_not_created(case_name, build_response, mocker, sample_insights, mock_config, capsys):
    """E2E: Jira rejects ticket (400 or 500); result is empty, warning printed.

    Parametrized over bad_request_response and server_error_response factories.
    """
    # Mock requests.post to return error response
    error_resp = build_response(mocker)
    mocker.patch("zoom_insights.jira_export.requests.post", return_value=error_resp)

    # Execute create_jira_tickets
    from zoom_insights.jira_export import create_jira_tickets

    result = create_jira_tickets(
        sample_insights,
        mock_config.jira_url,
        mock_config.jira_email,
        mock_config.jira_api_token,
        mock_config.jira_project_key,
    )

    # Assertions
    assert result == [], f"Should return empty list for {case_name}"

    # Verify "Warning" is printed to stdout
    captured = capsys.readouterr()
    assert "Warning" in captured.out, f"Should print Warning for {case_name}"
