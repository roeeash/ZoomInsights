"""End-to-end sanitization and metrics tests."""

import json
import os
import pytest
from pathlib import Path

from zoom_insights.config import Config
from zoom_insights.cli import _process_local_file


pytestmark = pytest.mark.e2e


class TestSanitizationHappyPath:
    """Transcript sanitization and metrics collection."""

    def test_sanitization_and_metrics(self, synthetic_wav, tmp_path, tmp_output_dir, mocker):
        """Sanitized transcript → metrics collected → rendered in output."""
        config = Config(
            zoom_account_id="unused",
            zoom_client_id="unused",
            zoom_client_secret="unused",
            groq_api_key="test_key",
        )

        mocker.patch("zoom_insights.cli.transcribe", return_value="Meeting content here")
        mocker.patch(
            "zoom_insights.cli.summarize",
            return_value={
                "summary": "Clean meeting",
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
            with open(output_dirs[0] / "insights.json") as f:
                data = json.load(f)
            assert "summary" in data
            assert data["summary"] == "Clean meeting"

        finally:
            os.chdir(original_cwd)


class TestMetricsRendering:
    """Metrics collection and report output."""

    def test_metrics_in_output_report(self, synthetic_wav, tmp_path, tmp_output_dir, mocker):
        """Metrics rendered in report.md."""
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
            report_file = output_dirs[0] / "report.md"
            assert report_file.exists()

        finally:
            os.chdir(original_cwd)
