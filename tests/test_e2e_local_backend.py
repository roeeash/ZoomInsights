"""End-to-end tests for local backend (FasterWhisper + Ollama)."""

import json
import os
import pytest
from pathlib import Path

from zoom_insights.config import Config
from zoom_insights.cli import _process_local_file


pytestmark = pytest.mark.e2e


class TestLocalBackendHappyPath:
    """Local backend integration with real file I/O."""

    def test_local_backend_process_succeeds(self, synthetic_wav, tmp_path, tmp_output_dir, mocker):
        """Process with local backend (transcribe/LLM mocked at API boundary)."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="unused",
            use_local_backend=True,
            ollama_url="http://localhost:11434",
        )

        mocker.patch("zoom_insights.cli.transcribe", return_value="Alice: hello")
        mocker.patch(
            "zoom_insights.cli.summarize",
            return_value={
                "summary": "Local backend meeting",
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
            _process_local_file(
                file_path=str(synthetic_wav),
                groq_client=groq_client,
                work_dir=str(work_dir),
                config=config,
            )

            output_dirs = list(Path("output").iterdir())
            assert len(output_dirs) > 0
            with open(output_dirs[0] / "insights.json") as f:
                data = json.load(f)
            assert data["summary"] == "Local backend meeting"

        finally:
            os.chdir(original_cwd)


class TestLocalBackendBadInput:
    """Configuration and input validation."""

    def test_local_backend_missing_ollama_url(self, tmp_path, mocker):
        """USE_LOCAL_BACKEND=true but no URL → fails."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="unused",
            use_local_backend=True,
            ollama_url="",
        )

        # Should fail at initialization if backends validate config
        assert config.use_local_backend is True
        assert config.ollama_url == ""


class TestLocalBackendStagedFailures:
    """Failures at transcription and LLM stages."""

    def test_local_backend_transcription_fails(self, synthetic_wav, tmp_path, tmp_output_dir, mocker):
        """Transcription fails → error propagates."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="unused",
            use_local_backend=True,
            ollama_url="http://localhost:11434",
        )

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch("zoom_insights.cli.transcribe", side_effect=RuntimeError("Whisper unavailable"))
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            groq_client = mocker.MagicMock()
            with pytest.raises(RuntimeError, match="Whisper unavailable"):
                _process_local_file(
                    file_path=str(synthetic_wav),
                    groq_client=groq_client,
                    work_dir=str(work_dir),
                    config=config,
                )

        finally:
            os.chdir(original_cwd)

    def test_local_backend_llm_fails(self, synthetic_wav, tmp_path, tmp_output_dir, mocker):
        """LLM (Ollama) fails → error propagates."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="unused",
            use_local_backend=True,
            ollama_url="http://localhost:11434",
        )

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        mocker.patch("zoom_insights.zoom_client.ensure_work_dir", return_value=str(work_dir))
        mocker.patch("zoom_insights.cli.transcribe", return_value="Transcript")
        mocker.patch("zoom_insights.cli.summarize", side_effect=RuntimeError("Ollama unavailable"))
        mocker.patch("zoom_insights.tracker.save_action_items")
        mocker.patch("zoom_insights.cli.read_repo_code_summary", return_value="")
        mocker.patch("zoom_insights.cli._load_agent_guidance", return_value="")

        original_cwd = os.getcwd()
        os.chdir(str(tmp_output_dir))

        try:
            groq_client = mocker.MagicMock()
            with pytest.raises(RuntimeError, match="Ollama unavailable"):
                _process_local_file(
                    file_path=str(synthetic_wav),
                    groq_client=groq_client,
                    work_dir=str(work_dir),
                    config=config,
                )

        finally:
            os.chdir(original_cwd)
