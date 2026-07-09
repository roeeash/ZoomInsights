"""End-to-end tests for FastAPI wrapper: job lifecycle with real file I/O."""

import json
import os
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from zoom_insights.api import app, jobs
from zoom_insights.config import Config


pytestmark = pytest.mark.e2e


class TestHappyPath:
    """Real e2e: POST /process → real file I/O → verify output on disk."""

    def test_happy_path_process_and_status(self, synthetic_wav, tmp_path, tmp_output_dir, mocker):
        """POST /process → poll /jobs/{id} → verify real output JSON on disk."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
        )

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        mocker.patch("zoom_insights.api.load_config", return_value=config)
        mocker.patch("zoom_insights.api.Groq")
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.transcribe", return_value="Alice: hello\nBob: hi")
        mocker.patch(
            "zoom_insights.cli.summarize",
            return_value={
                "summary": "Team sync",
                "key_points": ["Point 1"],
                "decisions": ["Approved"],
                "action_items": [{"owner": "Alice", "task": "Task 1", "due": "2025-08-15"}],
                "open_questions": ["Q1"],
                "notable_quotes": ["Quote 1"],
            },
        )

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            client = TestClient(app)
            response = client.post(
                "/process",
                json={"file_path": str(synthetic_wav), "jira": False},
            )
            assert response.status_code == 202
            job_id = response.json()["job_id"]

            # Poll until done
            start = time.time()
            while time.time() - start < 10:
                get_response = client.get(f"/jobs/{job_id}")
                job = get_response.json()
                if job["status"] in ("done", "failed"):
                    break
                time.sleep(0.2)

            assert job["status"] == "done", f"Failed: {job.get('error')}"
            assert job["result"]["summary"] == "Team sync"

            # Verify real output file on disk
            output_dirs = list(Path("output").iterdir())
            assert len(output_dirs) > 0
            with open(output_dirs[0] / "insights.json") as f:
                disk_data = json.load(f)
            assert disk_data["summary"] == "Team sync"

        finally:
            os.chdir(original_cwd)


class TestBadInput:
    """Early request validation failures."""

    def test_bad_input_missing_field(self):
        """Empty body → 422."""
        client = TestClient(app)
        response = client.post("/process", json={})
        assert response.status_code == 422

    def test_bad_input_unknown_id(self):
        """Unknown job ID → 404."""
        client = TestClient(app)
        response = client.get("/jobs/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_bad_input_nonexistent_file(self):
        """Nonexistent file path → 422."""
        client = TestClient(app)
        response = client.post(
            "/process",
            json={"file_path": "/does/not/exist.mp4", "jira": False},
        )
        assert response.status_code == 422


class TestStagedFailures:
    """Pipeline failures at different stages."""

    def test_stage_failure_validation(self):
        """Invalid request → 422, no job created."""
        initial_count = len(jobs)
        client = TestClient(app)
        response = client.post("/process", json={})
        assert response.status_code == 422
        assert len(jobs) == initial_count

    def test_stage_failure_summarize_raises(self, synthetic_wav, tmp_output_dir, mocker, tmp_path):
        """Summarize fails → job marked failed, error visible."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
        )

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        mocker.patch("zoom_insights.api.load_config", return_value=config)
        mocker.patch("zoom_insights.api.Groq")
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.transcribe", return_value="Alice: hello")
        mocker.patch("zoom_insights.cli.summarize", side_effect=RuntimeError("API rate limited"))

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            client = TestClient(app)
            response = client.post(
                "/process",
                json={"file_path": str(synthetic_wav), "jira": False},
            )
            assert response.status_code == 202
            job_id = response.json()["job_id"]

            start = time.time()
            while time.time() - start < 5:
                get_response = client.get(f"/jobs/{job_id}")
                job = get_response.json()
                if job["status"] == "failed":
                    break
                time.sleep(0.2)

            assert job["status"] == "failed"
            assert "API rate limited" in job["error"]
            # Server remains healthy
            assert client.get("/health").status_code == 200

        finally:
            os.chdir(original_cwd)

    def test_stage_failure_status_read_mid_processing(self, synthetic_wav, tmp_output_dir, mocker, tmp_path):
        """GET /jobs/{id} before completion → intermediate status."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
        )

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        def slow_write(*args, **kwargs):
            time.sleep(0.5)

        mocker.patch("zoom_insights.api.load_config", return_value=config)
        mocker.patch("zoom_insights.api.Groq")
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.transcribe", return_value="Alice: hello")
        mocker.patch(
            "zoom_insights.cli.summarize",
            return_value={"summary": "S", "key_points": [], "decisions": [], "action_items": [], "open_questions": [], "notable_quotes": []},
        )
        mocker.patch("zoom_insights.cli.write_report", side_effect=slow_write)

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            client = TestClient(app)
            response = client.post(
                "/process",
                json={"file_path": str(synthetic_wav), "jira": False},
            )
            assert response.status_code == 202
            job_id = response.json()["job_id"]

            time.sleep(0.05)
            early_job = client.get(f"/jobs/{job_id}").json()
            assert early_job["status"] in ("queued", "processing")
            assert early_job["result"] is None

            time.sleep(1.0)
            final_job = client.get(f"/jobs/{job_id}").json()
            assert final_job["status"] in ("done", "failed")

        finally:
            os.chdir(original_cwd)
