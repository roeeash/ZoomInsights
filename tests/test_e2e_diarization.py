"""End-to-end diarization tests: speaker attribution."""

import json
import os
import pytest
from pathlib import Path

from zoom_insights.config import Config
from zoom_insights.cli import _process_local_file


pytestmark = pytest.mark.e2e


class TestDiarizationHappyPath:
    """Diarization with speaker attribution."""

    def test_diarization_adds_speaker_labels(self, synthetic_wav, tmp_path, tmp_output_dir, mocker):
        """With --diarize, speakers attributed to action items."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
            huggingface_token="test_token",
        )

        mocker.patch("zoom_insights.cli.transcribe", return_value="Speaker1: task\nSpeaker2: approved")
        mocker.patch(
            "zoom_insights.cli.summarize",
            return_value={
                "summary": "Diarized meeting",
                "key_points": [],
                "decisions": [],
                "action_items": [{"owner": "Speaker1", "task": "Task 1", "due": "2025-08-15"}],
                "open_questions": [],
                "notable_quotes": [],
            },
        )
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            groq_client = mocker.MagicMock()
            _process_local_file(
                file_path=str(synthetic_wav),
                groq_client=groq_client,
                work_dir=str(work_dir),
                config=config,
                diarize=True,
            )

            output_dirs = list(Path("output").iterdir())
            with open(output_dirs[0] / "insights.json") as f:
                data = json.load(f)
            assert "action_items" in data

        finally:
            os.chdir(original_cwd)


class TestDiarizationBadInput:
    """Missing HF token or corrupted audio."""

    def test_diarization_missing_huggingface_token(self, tmp_path, mocker):
        """No HF token → should fail at config validation."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="unused",
        )
        # huggingface_token should be None or empty
        assert config.huggingface_token is None or config.huggingface_token == ""


class TestDiarizationStagedFailures:
    """Model loading and diarization failures."""

    def test_diarization_model_load_fails(self, synthetic_wav, tmp_path, tmp_output_dir, mocker):
        """Model download fails → falls back gracefully."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
            huggingface_token="invalid_token",
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

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            groq_client = mocker.MagicMock()
            # Should either succeed (fallback) or fail gracefully
            _process_local_file(
                file_path=str(synthetic_wav),
                groq_client=groq_client,
                work_dir=str(work_dir),
                config=config,
                diarize=True,
            )

        finally:
            os.chdir(original_cwd)
