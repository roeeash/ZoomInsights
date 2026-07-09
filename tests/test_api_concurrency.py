"""Tests for bounded job concurrency in API server (Cycle 43)."""

import json
import os
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from zoom_insights.api import app, jobs, _executor_lock
from zoom_insights.config import Config


pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def reset_executor():
    """Reset the global executor before each test."""
    import zoom_insights.api
    with _executor_lock:
        if zoom_insights.api._executor is not None:
            # Use wait=False to prevent hanging on stuck futures
            zoom_insights.api._executor.shutdown(wait=False)
        zoom_insights.api._executor = None

    # Also clear jobs dict
    jobs.clear()

    yield

    # Cleanup after test
    with _executor_lock:
        if zoom_insights.api._executor is not None:
            # Use wait=False to prevent hanging on stuck futures
            zoom_insights.api._executor.shutdown(wait=False)
        zoom_insights.api._executor = None
    jobs.clear()


class TestConcurrentJobs:
    """Tests for bounded concurrency control."""

    def test_jobs_queue_beyond_worker_cap(self, synthetic_wav, tmp_output_dir, mocker, tmp_path):
        """Submit more jobs than max_concurrent_jobs; assert excess jobs show 'queued' status."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
            max_concurrent_jobs=2,  # Set low cap for testing
        )

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        # Slow mock to keep workers busy
        def slow_summarize(*args, **kwargs):
            time.sleep(1.0)
            return {
                "summary": "Team sync",
                "key_points": ["Point 1"],
                "decisions": ["Approved"],
                "action_items": [{"owner": "Alice", "task": "Task 1", "due": "2025-08-15"}],
                "open_questions": ["Q1"],
                "notable_quotes": ["Quote 1"],
            }

        mocker.patch("zoom_insights.api.load_config", return_value=config)
        mocker.patch("zoom_insights.api.Groq")
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.is_completed", return_value=False)
        mocker.patch("zoom_insights.cli.mark_completed")
        mocker.patch("zoom_insights.cli.transcribe", return_value="Alice: hello")
        mocker.patch("zoom_insights.cli.summarize", side_effect=slow_summarize)

        # Reset executor to use our test config
        import zoom_insights.api
        with _executor_lock:
            zoom_insights.api._executor = ThreadPoolExecutor(max_workers=config.max_concurrent_jobs)

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            client = TestClient(app)

            # Submit 5 jobs (2 will run immediately, 3 will queue)
            job_ids = []
            for i in range(5):
                response = client.post(
                    "/process",
                    json={"file_path": str(synthetic_wav), "jira": False},
                )
                assert response.status_code == 202
                job_ids.append(response.json()["job_id"])

            # Check job statuses immediately
            queued_count = 0
            for job_id in job_ids:
                job = client.get(f"/jobs/{job_id}").json()
                if job["status"] == "queued":
                    queued_count += 1

            # At least some jobs should be queued (not all running)
            assert queued_count > 0, "Expected some jobs to remain queued beyond worker cap"

        finally:
            os.chdir(original_cwd)

    def test_endpoint_still_returns_immediately_under_load(self, synthetic_wav, tmp_output_dir, mocker, tmp_path):
        """POST /process under heavy load still returns immediately (fire-and-forget preserved)."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
            max_concurrent_jobs=2,
        )

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        # Slow mock to accumulate queue
        def slow_summarize(*args, **kwargs):
            time.sleep(0.5)
            return {
                "summary": "Team sync",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

        mocker.patch("zoom_insights.api.load_config", return_value=config)
        mocker.patch("zoom_insights.api.Groq")
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.is_completed", return_value=False)
        mocker.patch("zoom_insights.cli.mark_completed")
        mocker.patch("zoom_insights.cli.transcribe", return_value="Alice: hello")
        mocker.patch("zoom_insights.cli.summarize", side_effect=slow_summarize)

        # Reset executor
        import zoom_insights.api
        with _executor_lock:
            zoom_insights.api._executor = ThreadPoolExecutor(max_workers=config.max_concurrent_jobs)

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            client = TestClient(app)

            # Submit 10 jobs and measure response times
            response_times = []
            for i in range(10):
                start = time.time()
                response = client.post(
                    "/process",
                    json={"file_path": str(synthetic_wav), "jira": False},
                )
                elapsed = time.time() - start
                response_times.append(elapsed)
                assert response.status_code == 202, f"Job {i} failed: {response.text}"

            # All responses should be very fast (< 200ms each)
            # This verifies fire-and-forget semantics are preserved
            for i, elapsed in enumerate(response_times):
                assert elapsed < 0.2, f"Job {i} took {elapsed:.3f}s, expected < 0.2s"

        finally:
            os.chdir(original_cwd)

    def test_queued_job_eventually_processes(self, tmp_output_dir, mocker, tmp_path):
        """A queued job (beyond initial cap) transitions queued → processing → done."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
            max_concurrent_jobs=1,  # Very low cap to force queueing
        )

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        # Create two separate WAV files to avoid idempotency issues
        import struct
        import wave

        wav_paths = []
        for i in range(2):
            wav_path = tmp_path / f"test_{i}.wav"
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                # 1 second of silence
                frames = struct.pack("<h", 0) * 16000
                wav_file.writeframes(frames)
            wav_paths.append(str(wav_path))

        # First job gets slow summarize, second gets quick one
        call_count = [0]

        def slow_then_quick_summarize(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First job sleeps to hold the worker
                time.sleep(0.5)
            return {
                "summary": "Team sync",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

        mocker.patch("zoom_insights.api.load_config", return_value=config)
        mocker.patch("zoom_insights.api.Groq")
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.is_completed", return_value=False)
        mocker.patch("zoom_insights.cli.mark_completed")
        mocker.patch("zoom_insights.cli.transcribe", return_value="Alice: hello")
        mocker.patch("zoom_insights.cli.summarize", side_effect=slow_then_quick_summarize)

        # Reset executor
        import zoom_insights.api
        with _executor_lock:
            zoom_insights.api._executor = ThreadPoolExecutor(max_workers=config.max_concurrent_jobs)

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            client = TestClient(app)

            # Submit 2 jobs: first will run and hold worker, second will queue
            response1 = client.post("/process", json={"file_path": wav_paths[0], "jira": False})
            job_id1 = response1.json()["job_id"]

            # Poll job 1 until it reaches processing state (worker has started)
            start = time.time()
            while time.time() - start < 5:
                job1_check = client.get(f"/jobs/{job_id1}").json()
                if job1_check["status"] == "processing":
                    break
                time.sleep(0.01)

            response2 = client.post("/process", json={"file_path": wav_paths[1], "jira": False})
            job_id2 = response2.json()["job_id"]

            # Job 2 should be queued immediately after submission (job 1 still processing)
            job2_immediate = client.get(f"/jobs/{job_id2}").json()
            assert job2_immediate["status"] == "queued", f"Job 2 should start queued, but is {job2_immediate['status']}"

            # Poll job 2 until it completes (will start once job 1 finishes)
            start = time.time()
            while time.time() - start < 10:
                job2_check = client.get(f"/jobs/{job_id2}").json()
                if job2_check["status"] == "done":
                    break
                time.sleep(0.1)

            # Should eventually reach done
            assert job2_check["status"] == "done", f"Job 2 ended in state: {job2_check['status']}"

        finally:
            os.chdir(original_cwd)

    def test_worker_cap_not_exceeded_under_burst(self, tmp_output_dir, mocker, tmp_path):
        """Burst of 10 requests with max_concurrent_jobs=3; verify ≤3 concurrent executions."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
            max_concurrent_jobs=3,
        )

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0
        count_lock = Lock()

        def tracked_summarize(*args, **kwargs):
            nonlocal concurrent_count, max_concurrent
            with count_lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)

            # Hold the worker busy briefly
            time.sleep(0.2)

            with count_lock:
                concurrent_count -= 1

            return {
                "summary": "Team sync",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

        mocker.patch("zoom_insights.api.load_config", return_value=config)
        mocker.patch("zoom_insights.api.Groq")
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.is_completed", return_value=False)
        mocker.patch("zoom_insights.cli.mark_completed")
        mocker.patch("zoom_insights.cli.transcribe", return_value="Alice: hello")
        mocker.patch("zoom_insights.cli.summarize", side_effect=tracked_summarize)

        # Reset executor with test config
        import zoom_insights.api
        with _executor_lock:
            zoom_insights.api._executor = ThreadPoolExecutor(max_workers=config.max_concurrent_jobs)

        # Create 10 unique WAV files for this test
        import struct
        import wave
        wav_paths = []
        for i in range(10):
            wav_path = tmp_path / f"test_{i}.wav"
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                # 1 second of silence
                frames = struct.pack("<h", 0) * 16000
                wav_file.writeframes(frames)
            wav_paths.append(str(wav_path))

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            client = TestClient(app)

            # Submit 10 jobs in rapid succession
            for i in range(10):
                response = client.post(
                    "/process",
                    json={"file_path": wav_paths[i], "jira": False},
                )
                assert response.status_code == 202

            # Wait for all jobs to complete
            time.sleep(3.0)

            # Verify that we never exceeded the worker cap
            assert max_concurrent <= config.max_concurrent_jobs, (
                f"Concurrent execution exceeded cap: "
                f"max_concurrent={max_concurrent}, cap={config.max_concurrent_jobs}"
            )

        finally:
            os.chdir(original_cwd)
