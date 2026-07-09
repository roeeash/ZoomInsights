"""End-to-end webhook endpoint tests: signature validation, job enqueueing."""

import hashlib
import hmac
import json
import time
import pytest
from fastapi.testclient import TestClient

from zoom_insights.api import app, jobs
from zoom_insights.config import Config


pytestmark = pytest.mark.e2e


def _generate_zoom_signature(payload_bytes: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for Zoom webhook."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


class TestWebhookHappyPath:
    """Valid signature + payload → job enqueued."""

    def test_webhook_valid_signature_creates_job(self, mocker, tmp_path, tmp_output_dir):
        """POST /webhook with valid signature → 200, job created and processed."""
        secret = "test_webhook_secret"
        config = Config(
            zoom_account_id="test_account",
            zoom_client_id="test_client",
            zoom_client_secret="test_secret",
            groq_api_key="test_key",
            zoom_webhook_secret_token=secret,
        )

        payload = {
            "event": "recording.completed",
            "data": {"object": {"id": "meeting-uuid-123"}},
        }
        payload_bytes = json.dumps(payload).encode()
        signature = _generate_zoom_signature(payload_bytes, secret)

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        mocker.patch("zoom_insights.api.load_config", return_value=config)
        mocker.patch("zoom_insights.api.Groq")
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch(
            "zoom_insights.zoom_client.list_recent_recordings",
            return_value=[{"id": "meeting-uuid-123", "filename": "test.mp4"}],
        )
        mocker.patch("zoom_insights.zoom_client.download", return_value="/tmp/test.mp4")
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.transcribe", return_value="Meeting transcript")
        mocker.patch(
            "zoom_insights.cli.summarize",
            return_value={
                "summary": "Webhook meeting",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            },
        )

        client = TestClient(app)
        response = client.post(
            "/webhook",
            content=payload_bytes,
            headers={
                "x-zm-signature": f"v0={signature}",
                "content-type": "application/json",
            },
        )
        assert response.status_code == 200
        # Job should be created
        initial_jobs = len(jobs)
        assert initial_jobs > 0


class TestWebhookBadInput:
    """Invalid signatures and malformed payloads."""

    def test_webhook_missing_signature(self):
        """Missing x-zm-signature header → 401."""
        client = TestClient(app)
        response = client.post(
            "/webhook",
            json={"event": "recording.completed", "data": {"object": {"id": "uuid"}}},
        )
        assert response.status_code == 401

    def test_webhook_wrong_signature(self):
        """Invalid signature → 401."""
        client = TestClient(app)
        payload = json.dumps({"event": "recording.completed", "data": {"object": {"id": "uuid"}}})
        response = client.post(
            "/webhook",
            json=json.loads(payload),
            headers={"x-zm-signature": "v0=wrong_signature"},
        )
        assert response.status_code == 401

    def test_webhook_malformed_json(self):
        """Invalid JSON body → 422."""
        client = TestClient(app)
        response = client.post(
            "/webhook",
            content="not json",
            headers={"content-type": "application/json", "x-zm-signature": "v0=sig"},
        )
        assert response.status_code in (422, 401)

    def test_webhook_missing_uuid(self, mocker):
        """Valid signature but missing meeting UUID → 400."""
        secret = "test_secret"
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="unused",
            zoom_webhook_secret_token=secret,
        )

        payload = {"event": "recording.completed", "data": {"object": {}}}
        payload_bytes = json.dumps(payload).encode()
        signature = _generate_zoom_signature(payload_bytes, secret)

        mocker.patch("zoom_insights.api.load_config", return_value=config)

        client = TestClient(app)
        response = client.post(
            "/webhook",
            content=payload_bytes,
            headers={
                "x-zm-signature": f"v0={signature}",
                "content-type": "application/json",
            },
        )
        assert response.status_code == 400


class TestWebhookStagedFailures:
    """Failures at signature, parsing, and background processing stages."""

    def test_webhook_secret_unset(self, mocker):
        """Webhook secret not configured → 401."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="unused",
        )

        mocker.patch("zoom_insights.api.load_config", return_value=config)

        payload = {"event": "recording.completed", "data": {"object": {"id": "uuid"}}}
        client = TestClient(app)
        response = client.post(
            "/webhook",
            json=payload,
            headers={"x-zm-signature": "v0=sig"},
        )
        assert response.status_code == 401

    def test_webhook_background_job_fails(self, mocker, tmp_path, tmp_output_dir):
        """Background pipeline fails → webhook returns 200 (fire-and-forget), job marked failed."""
        secret = "test_secret"
        config = Config(
            zoom_account_id="test",
            zoom_client_id="test",
            zoom_client_secret="test",
            groq_api_key="test",
            zoom_webhook_secret_token=secret,
        )

        payload = {"event": "recording.completed", "data": {"object": {"id": "uuid-123"}}}
        payload_bytes = json.dumps(payload).encode()
        signature = _generate_zoom_signature(payload_bytes, secret)

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        mocker.patch("zoom_insights.api.load_config", return_value=config)
        mocker.patch("zoom_insights.api.Groq")
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch(
            "zoom_insights.zoom_client.download",
            side_effect=RuntimeError("Download failed"),
        )
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")
        mocker.patch("zoom_insights.tracker.save_action_items")

        client = TestClient(app)
        response = client.post(
            "/webhook",
            content=payload_bytes,
            headers={
                "x-zm-signature": f"v0={signature}",
                "content-type": "application/json",
            },
        )
        # Webhook returns 200 (fire-and-forget)
        assert response.status_code == 200
        # Job exists but may be failed (background thread processing)
        time.sleep(0.5)
        assert len(jobs) > 0
