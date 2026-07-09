"""Tests for FastAPI REST API endpoint."""

import hashlib
import hmac
import json
import os
import pytest
from fastapi.testclient import TestClient

from zoom_insights.api import app, _verify_zoom_signature


@pytest.mark.unit
class TestAPIHealth:
    """Test the health endpoint."""

    def test_health_returns_ok(self):
        """GET /health returns 200 with status=ok."""
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.unit
class TestAPIProcess:
    """Test the POST /process endpoint."""

    def test_process_missing_file_returns_422(self):
        """POST /process with non-existent file returns 422."""
        client = TestClient(app)
        response = client.post(
            "/process",
            json={"file_path": "/nonexistent/file.mp4", "jira": False},
        )
        assert response.status_code == 422
        assert "File not found" in response.json()["detail"]

    def test_process_returns_202_and_job_id(self, tmp_path):
        """POST /process with valid path returns 202 with job_id."""
        # Create a temporary file
        test_file = tmp_path / "test.mp4"
        test_file.write_text("fake audio")

        client = TestClient(app)
        response = client.post(
            "/process",
            json={"file_path": str(test_file), "jira": False},
        )

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert len(data["job_id"]) > 0

        # Verify it's a valid UUID-like string
        assert len(data["job_id"].split("-")) == 5  # UUID format


@pytest.mark.unit
class TestAPIJobStatus:
    """Test the GET /jobs/{job_id} endpoint."""

    def test_get_job_unknown_id_returns_404(self):
        """GET /jobs/unknown returns 404."""
        client = TestClient(app)
        response = client.get("/jobs/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        assert "Job not found" in response.json()["detail"]

    def test_get_job_returns_queued_immediately(self, tmp_path, mocker):
        """POST then GET returns queued or running status."""
        # Create a temporary file
        test_file = tmp_path / "test.mp4"
        test_file.write_text("fake audio")

        # Mock threading.Thread to prevent background execution
        mock_thread = mocker.MagicMock()
        mocker.patch("zoom_insights.api.threading.Thread", return_value=mock_thread)

        client = TestClient(app)

        # POST to create job
        post_response = client.post(
            "/process",
            json={"file_path": str(test_file), "jira": False},
        )
        job_id = post_response.json()["job_id"]

        # GET immediately (before thread runs)
        get_response = client.get(f"/jobs/{job_id}")
        assert get_response.status_code == 200

        job = get_response.json()
        assert job["id"] == job_id
        assert job["status"] == "queued"
        assert job["result"] is None
        assert job["error"] is None
        assert "created_at" in job

    def test_job_transitions_to_done(self, tmp_path, mocker):
        """Mock pipeline; job transitions to done with result."""
        from zoom_insights.api import jobs, jobs_lock

        # Create a temporary file
        test_file = tmp_path / "test.mp4"
        test_file.write_text("fake audio")

        insights_data = {
            "summary": "Test meeting",
            "key_points": ["Point 1"],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }

        # Mock threading.Thread to call our pipeline synchronously for testing
        def make_thread(*args, **kwargs):
            target = kwargs.get("target")
            thread_args = kwargs.get("args", ())

            # Call the pipeline function immediately
            if target and thread_args:
                target(*thread_args)

            # Return a mock thread that does nothing on start
            mock_thread = mocker.MagicMock()
            return mock_thread

        mocker.patch("zoom_insights.api.threading.Thread", side_effect=make_thread)

        # Mock all the imports inside _run_pipeline to avoid actual API calls
        mock_config = mocker.MagicMock()
        mock_config.groq_api_key = "test_key"
        mocker.patch("zoom_insights.api.load_config", return_value=mock_config)
        mocker.patch("zoom_insights.api.Groq", return_value=mocker.MagicMock())

        # Mock ensure_work_dir at its source (zoom_client)
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value="work")

        # Mock the core pipeline functions to avoid audio processing
        mocker.patch("zoom_insights.cli.require_ffmpeg", return_value=None)
        mocker.patch("zoom_insights.cli.to_compressed_audio", return_value=None)
        mocker.patch("zoom_insights.cli.maybe_segment", return_value=["dummy"])
        # transcribe() returns (transcript, metrics_dict)
        mocker.patch("zoom_insights.cli.transcribe", return_value="dummy transcript")
        # summarize() returns (insights, MetricsCollector)
        from zoom_insights.metrics import MetricsCollector
        mock_metrics = MetricsCollector()
        mocker.patch("zoom_insights.cli.summarize", return_value=insights_data)
        mocker.patch("zoom_insights.cli.write_report", return_value=None)
        mocker.patch("zoom_insights.cli.is_completed", return_value=False)
        mocker.patch("zoom_insights.cli.mark_completed", return_value=None)
        mocker.patch("zoom_insights.cli.shutil.copy2", return_value=None)
        mocker.patch("zoom_insights.tracker.save_action_items", return_value=None)

        # Change to temp directory for the pipeline to write outputs
        import os
        original_cwd = os.getcwd()
        os.chdir(str(tmp_path))

        try:
            # Create insights file in expected location
            output_dir = tmp_path / "output" / "test"
            output_dir.mkdir(parents=True, exist_ok=True)
            insights_file = output_dir / "insights.json"
            with open(insights_file, "w") as f:
                json.dump(insights_data, f)

            mocker.patch("zoom_insights.report.sanitize_topic", return_value="test")

            client = TestClient(app)

            # POST to create job
            post_response = client.post(
                "/process",
                json={"file_path": str(test_file), "jira": False},
            )
            job_id = post_response.json()["job_id"]

            # Give time for sync execution
            import time

            time.sleep(0.1)

            # GET to check status
            get_response = client.get(f"/jobs/{job_id}")
            assert get_response.status_code == 200

            job = get_response.json()
            assert job["status"] == "done"
        finally:
            os.chdir(original_cwd)

    def test_job_transitions_to_failed(self, tmp_path, mocker):
        """Mock pipeline failure; job transitions to failed with error."""
        # Create a temporary file
        test_file = tmp_path / "test.mp4"
        test_file.write_text("fake audio")

        # Mock threading.Thread to call our pipeline synchronously for testing
        def make_thread(*args, **kwargs):
            target = kwargs.get("target")
            thread_args = kwargs.get("args", ())

            # Call the pipeline function immediately
            if target and thread_args:
                target(*thread_args)

            # Return a mock thread that does nothing on start
            mock_thread = mocker.MagicMock()
            return mock_thread

        mocker.patch("zoom_insights.api.threading.Thread", side_effect=make_thread)

        # Mock all the imports inside _run_pipeline to avoid actual API calls
        mock_config = mocker.MagicMock()
        mock_config.groq_api_key = "test_key"
        mocker.patch("zoom_insights.api.load_config", return_value=mock_config)
        mocker.patch("zoom_insights.api.Groq", return_value=mocker.MagicMock())

        # Mock ensure_work_dir at its source (zoom_client)
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value="work")

        # Mock the core pipeline functions to fail
        mocker.patch("zoom_insights.cli.require_ffmpeg", return_value=None)
        mocker.patch(
            "zoom_insights.cli.to_compressed_audio",
            side_effect=RuntimeError("Test error: audio processing failed"),
        )

        client = TestClient(app)

        # POST to create job
        post_response = client.post(
            "/process",
            json={"file_path": str(test_file), "jira": False},
        )
        job_id = post_response.json()["job_id"]

        # Give time for sync execution
        import time

        time.sleep(0.1)

        # GET to check status
        get_response = client.get(f"/jobs/{job_id}")
        assert get_response.status_code == 200

        job = get_response.json()
        assert job["status"] == "failed"
        assert job["error"] is not None
        assert "audio processing failed" in job["error"]

    def test_multiple_jobs_are_independent(self, tmp_path, mocker):
        """Two jobs track independently."""
        from zoom_insights.api import jobs, jobs_lock

        # Create two temporary files
        test_file1 = tmp_path / "test1.mp4"
        test_file1.write_text("fake audio 1")

        test_file2 = tmp_path / "test2.mp4"
        test_file2.write_text("fake audio 2")

        # Mock threading.Thread to do nothing (just skip pipeline execution)
        def make_thread(*args, **kwargs):
            mock_thread = mocker.MagicMock()
            return mock_thread

        mocker.patch("zoom_insights.api.threading.Thread", side_effect=make_thread)

        client = TestClient(app)

        # Create first job
        post_response1 = client.post(
            "/process",
            json={"file_path": str(test_file1), "jira": False},
        )
        job_id1 = post_response1.json()["job_id"]

        # Create second job
        post_response2 = client.post(
            "/process",
            json={"file_path": str(test_file2), "jira": False},
        )
        job_id2 = post_response2.json()["job_id"]

        # Both jobs should exist and be independent
        assert job_id1 != job_id2

        # Check both jobs can be retrieved
        get_response1 = client.get(f"/jobs/{job_id1}")
        assert get_response1.status_code == 200
        assert get_response1.json()["id"] == job_id1

        get_response2 = client.get(f"/jobs/{job_id2}")
        assert get_response2.status_code == 200
        assert get_response2.json()["id"] == job_id2


@pytest.mark.unit
class TestWebhook:
    """Test the POST /webhook endpoint."""

    def test_webhook_missing_signature_header_returns_401(self, mocker):
        """POST /webhook without x-zm-signature header returns 401."""
        mocker.patch("zoom_insights.api.load_config")
        client = TestClient(app)

        webhook_payload = {
            "event": "recording.completed",
            "data": {"object": {"id": "meeting-uuid-123"}},
        }

        response = client.post(
            "/webhook",
            json=webhook_payload,
            headers={},  # No signature header
        )

        assert response.status_code == 401
        assert "signature" in response.json()["detail"].lower()

    def test_webhook_invalid_signature_returns_401(self, mocker):
        """POST /webhook with wrong HMAC signature returns 401."""
        mock_config = mocker.MagicMock()
        mock_config.zoom_webhook_secret_token = "correct_secret"
        mocker.patch("zoom_insights.api.load_config", return_value=mock_config)

        client = TestClient(app)

        webhook_payload = {
            "event": "recording.completed",
            "data": {"object": {"id": "meeting-uuid-123"}},
        }

        payload_bytes = json.dumps(webhook_payload).encode("utf-8")
        wrong_signature = "wrong_signature_here"

        response = client.post(
            "/webhook",
            content=payload_bytes,
            headers={
                "x-zm-signature": wrong_signature,
                "content-type": "application/json",
            },
        )

        assert response.status_code == 401
        assert "signature" in response.json()["detail"].lower()

    def test_webhook_valid_signature_enqueues_job(self, mocker):
        """POST /webhook with correct HMAC signature returns 200 and creates job."""
        mock_config = mocker.MagicMock()
        webhook_secret = "test_webhook_secret"
        mock_config.zoom_webhook_secret_token = webhook_secret
        mocker.patch("zoom_insights.api.load_config", return_value=mock_config)

        # Mock threading.Thread to prevent background execution
        mock_thread = mocker.MagicMock()
        mocker.patch("zoom_insights.api.threading.Thread", return_value=mock_thread)

        client = TestClient(app)

        webhook_payload = {
            "event": "recording.completed",
            "data": {"object": {"id": "meeting-uuid-456"}},
        }

        payload_bytes = json.dumps(webhook_payload).encode("utf-8")
        correct_signature = hmac.new(
            webhook_secret.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()

        response = client.post(
            "/webhook",
            content=payload_bytes,
            headers={
                "x-zm-signature": correct_signature,
                "content-type": "application/json",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

        # Verify job was created
        from zoom_insights.api import jobs

        assert len(jobs) > 0
        job_id = list(jobs.keys())[-1]
        job = jobs[job_id]
        assert job["status"] == "queued"
        assert job["meeting_uuid"] == "meeting-uuid-456"

    def test_webhook_starts_background_job(self, mocker):
        """POST /webhook starts a background _run_pipeline thread."""
        mock_config = mocker.MagicMock()
        webhook_secret = "test_webhook_secret"
        mock_config.zoom_webhook_secret_token = webhook_secret
        mocker.patch("zoom_insights.api.load_config", return_value=mock_config)

        # Track Thread calls
        mock_thread = mocker.MagicMock()
        mock_thread_class = mocker.patch(
            "zoom_insights.api.threading.Thread", return_value=mock_thread
        )

        client = TestClient(app)

        webhook_payload = {
            "event": "recording.completed",
            "data": {"object": {"id": "meeting-uuid-789"}},
        }

        payload_bytes = json.dumps(webhook_payload).encode("utf-8")
        correct_signature = hmac.new(
            webhook_secret.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()

        response = client.post(
            "/webhook",
            content=payload_bytes,
            headers={
                "x-zm-signature": correct_signature,
                "content-type": "application/json",
            },
        )

        assert response.status_code == 200

        # Assert Thread was created with _run_pipeline as target
        mock_thread_class.assert_called_once()
        call_kwargs = mock_thread_class.call_args[1]
        assert call_kwargs["target"].__name__ == "_run_pipeline"
        assert call_kwargs["daemon"] is True
        assert "meeting_uuid" in call_kwargs["kwargs"]
        assert call_kwargs["kwargs"]["meeting_uuid"] == "meeting-uuid-789"

        # Assert .start() was called
        mock_thread.start.assert_called_once()
