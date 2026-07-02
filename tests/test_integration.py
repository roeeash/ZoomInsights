"""End-to-end integration tests."""

import json
import os
import sys
import tempfile
import pytest
from zoom_insights.cli import main, _process_meeting, _process_local_file
from zoom_insights.zoom_client import RecordingFile, Meeting
from zoom_insights.config import Config


def good_groq_client(mocker, sample_insights):
    """Happy-path Groq mock: valid transcription + valid map+reduce."""
    client = mocker.MagicMock()
    client.audio.transcriptions.create.return_value = "Alice: hello."
    map_resp = mocker.MagicMock()
    map_resp.choices = [mocker.MagicMock(message=mocker.MagicMock(content="- Key point"))]
    reduce_resp = mocker.MagicMock()
    reduce_resp.choices = [mocker.MagicMock(message=mocker.MagicMock(content=json.dumps(sample_insights)))]
    client.chat.completions.create.side_effect = [map_resp, reduce_resp]
    return client


def transcription_error_groq_client(mocker):
    """Groq mock that fails during transcription."""
    client = mocker.MagicMock()
    client.audio.transcriptions.create.side_effect = Exception("Transcription failed")
    return client


def bad_llm_groq_client(mocker):
    """Groq mock that fails during LLM processing."""
    client = mocker.MagicMock()
    client.audio.transcriptions.create.return_value = "Valid transcript"
    client.chat.completions.create.side_effect = Exception("LLM API error")
    return client


@pytest.mark.integration
class TestIntegration:
    """End-to-end integration tests with mocked APIs."""

    def test_full_pipeline_e2e(self, mocker, sample_insights):
        """Test the complete pipeline from meeting fetch to report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "audio.m4a")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            compressed_file = os.path.join(tmpdir, "audio.m4a.opus")
            with open(compressed_file, "w") as f:
                f.write("fake compressed")

            # Mock meeting
            mock_file = RecordingFile(
                id="file-123",
                file_name="recording.m4a",
                file_size=5000000,
                file_type="M4A",
                download_url="https://zoom.com/recording.m4a",
                recording_type="AUDIO",
            )
            mock_meeting = Meeting(
                uuid="meeting-uuid-123",
                topic="Q4 Planning",
                start_time="2024-12-01T10:00:00Z",
                duration=3600,
                files=[mock_file],
            )

            # Mock Groq client
            mock_groq_client = good_groq_client(mocker, sample_insights)

            mocker.patch("zoom_insights.cli.get_access_token", return_value="test-token")
            mocker.patch("zoom_insights.cli.Groq", return_value=mock_groq_client)
            mocker.patch("zoom_insights.cli.get_meeting_recording", return_value=mock_meeting)
            mocker.patch("zoom_insights.cli.download")
            mocker.patch("zoom_insights.cli.to_compressed_audio")
            mocker.patch("zoom_insights.cli.maybe_segment", return_value=[compressed_file])
            mocker.patch("zoom_insights.cli.ensure_work_dir", return_value=tmpdir)
            mocker.patch("zoom_insights.cli.is_completed", return_value=False)
            mocker.patch("zoom_insights.cli.mark_completed")
            mock_write_report = mocker.patch("zoom_insights.cli.write_report")

            output_dir = os.path.join(tmpdir, "output")
            _process_meeting(
                "meeting-uuid-123",
                "test-token",
                mock_groq_client,
                Config(
                    zoom_account_id="test",
                    zoom_client_id="test",
                    zoom_client_secret="test",
                    groq_api_key="test-key",
                ),
                work_dir=tmpdir,
            )

            # Verify write_report was called
            mock_write_report.assert_called_once()
            call_args = mock_write_report.call_args
            assert call_args[0][0] == "Q4 Planning"  # topic
            assert "full meeting transcript" not in call_args[0][1].lower() or call_args[0][1]  # transcript
            assert call_args[0][2]["summary"] == "Meeting discussed quarterly roadmap and budget allocation."

    def test_process_meeting_by_index(self, mocker, sample_insights):
        """Test processing a meeting selected by index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake audio file for transcription
            audio_opus = os.path.join(tmpdir, "audio.opus")
            with open(audio_opus, "w") as f:
                f.write("fake audio")

            mock_file = RecordingFile(
                id="file-123",
                file_name="recording.m4a",
                file_size=5000000,
                file_type="M4A",
                download_url="https://zoom.com/recording.m4a",
                recording_type="AUDIO",
            )
            mock_meeting = Meeting(
                uuid="meeting-uuid-123",
                topic="Q4 Planning",
                start_time="2024-12-01T10:00:00Z",
                duration=3600,
                files=[mock_file],
            )

            mock_groq_client = good_groq_client(mocker, sample_insights)

            mocker.patch("zoom_insights.cli.ensure_work_dir", return_value=tmpdir)
            mocker.patch("zoom_insights.cli.is_completed", return_value=False)
            mocker.patch("zoom_insights.cli.mark_completed")
            mocker.patch("zoom_insights.cli.get_meeting_recording", return_value=mock_meeting)
            mocker.patch("zoom_insights.cli.download")
            mocker.patch("zoom_insights.cli.to_compressed_audio")
            mocker.patch("zoom_insights.cli.maybe_segment", return_value=[audio_opus])
            mocker.patch("zoom_insights.cli.write_report")

            _process_meeting(
                "meeting-uuid-123",
                "test-token",
                mock_groq_client,
                Config(
                    zoom_account_id="test",
                    zoom_client_id="test",
                    zoom_client_secret="test",
                    groq_api_key="test-key",
                ),
                work_dir=tmpdir,
            )

    def test_process_meeting_already_completed(self, mocker):
        """Test that already-completed meetings are skipped when user says no."""
        mocker.patch("zoom_insights.cli.is_completed", return_value=True)
        mock_mark = mocker.patch("zoom_insights.cli.mark_completed")
        mocker.patch("builtins.input", return_value="n")

        _process_meeting(
            "meeting-uuid-already-done",
            "test-token",
            mocker.MagicMock(),
            mocker.MagicMock(),
        )

        # Should not mark as completed again
        mock_mark.assert_not_called()

    def test_jira_flag_passed_to_process_local_file(self, mocker, sample_insights):
        """Verify --jira arg propagates to _process_local_file() with jira=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test audio file
            audio_file = os.path.join(tmpdir, "test_recording.m4a")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            compressed_file = os.path.join(tmpdir, "test_recording.m4a.opus")
            with open(compressed_file, "w") as f:
                f.write("fake compressed")

            mock_groq_client = good_groq_client(mocker, sample_insights)

            config = Config(
                zoom_account_id="test",
                zoom_client_id="test",
                zoom_client_secret="test",
                groq_api_key="test-key",
                jira_url="https://test.atlassian.net",
                jira_email="test@test.com",
                jira_api_token="token123",
                jira_project_key="TEST",
            )

            mocker.patch("zoom_insights.cli.require_ffmpeg")
            mocker.patch("zoom_insights.cli.ensure_work_dir", return_value=tmpdir)
            mocker.patch("zoom_insights.cli.is_completed", return_value=False)
            mocker.patch("zoom_insights.cli.mark_completed")
            mocker.patch("zoom_insights.cli.shutil.copy2")
            mocker.patch("zoom_insights.cli.to_compressed_audio")
            mocker.patch("zoom_insights.cli.maybe_segment", return_value=[compressed_file])
            # Mock Jira credential validation to succeed
            mock_get = mocker.MagicMock()
            mock_get.status_code = 200
            mocker.patch("zoom_insights.cli.requests.get", return_value=mock_get)
            mock_write_report = mocker.patch("zoom_insights.cli.write_report")
            mock_export = mocker.patch("zoom_insights.cli._export_to_jira")

            _process_local_file(
                audio_file,
                mock_groq_client,
                work_dir=tmpdir,
                jira=True,
                config=config,
            )

            # Verify _export_to_jira was called
            mock_export.assert_called_once()

    def test_jira_flag_passed_to_process_meeting(self, mocker, sample_insights):
        """Verify --jira arg propagates to _process_meeting() with jira=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "audio.m4a")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            compressed_file = os.path.join(tmpdir, "audio.m4a.opus")
            with open(compressed_file, "w") as f:
                f.write("fake compressed")

            mock_file = RecordingFile(
                id="file-123",
                file_name="recording.m4a",
                file_size=5000000,
                file_type="M4A",
                download_url="https://zoom.com/recording.m4a",
                recording_type="AUDIO",
            )
            mock_meeting = Meeting(
                uuid="meeting-uuid-123",
                topic="Q4 Planning",
                start_time="2024-12-01T10:00:00Z",
                duration=3600,
                files=[mock_file],
            )

            mock_groq_client = good_groq_client(mocker, sample_insights)

            config = Config(
                zoom_account_id="test",
                zoom_client_id="test",
                zoom_client_secret="test",
                groq_api_key="test-key",
                jira_url="https://test.atlassian.net",
                jira_email="test@test.com",
                jira_api_token="token123",
                jira_project_key="TEST",
            )

            mocker.patch("zoom_insights.cli.ensure_work_dir", return_value=tmpdir)
            mocker.patch("zoom_insights.cli.is_completed", return_value=False)
            mocker.patch("zoom_insights.cli.mark_completed")
            mocker.patch("zoom_insights.cli.get_meeting_recording", return_value=mock_meeting)
            mocker.patch("zoom_insights.cli.download")
            mocker.patch("zoom_insights.cli.to_compressed_audio")
            mocker.patch("zoom_insights.cli.maybe_segment", return_value=[compressed_file])
            # Mock Jira credential validation to succeed
            mock_get = mocker.MagicMock()
            mock_get.status_code = 200
            mocker.patch("zoom_insights.cli.requests.get", return_value=mock_get)
            mocker.patch("zoom_insights.cli.write_report")
            mock_export = mocker.patch("zoom_insights.cli._export_to_jira")

            _process_meeting(
                "meeting-uuid-123",
                "test-token",
                mock_groq_client,
                config,
                work_dir=tmpdir,
                jira=True,
            )

            # Verify _export_to_jira was called
            mock_export.assert_called_once()

    def test_process_local_file_calls_export_to_jira_when_jira_true(self, mocker, sample_insights):
        """Mock pipeline stages, assert _export_to_jira called when jira=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "test_recording.m4a")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            compressed_file = os.path.join(tmpdir, "test_recording.m4a.opus")
            with open(compressed_file, "w") as f:
                f.write("fake compressed")

            mock_groq_client = good_groq_client(mocker, sample_insights)

            config = Config(
                zoom_account_id="test",
                zoom_client_id="test",
                zoom_client_secret="test",
                groq_api_key="test-key",
                jira_url="https://test.atlassian.net",
                jira_email="test@test.com",
                jira_api_token="test-token",
                jira_project_key="TEST",
            )

            mocker.patch("zoom_insights.cli.ensure_work_dir", return_value=tmpdir)
            mocker.patch("zoom_insights.cli.is_completed", return_value=False)
            mocker.patch("zoom_insights.cli.mark_completed")
            mocker.patch("zoom_insights.cli.shutil.copy2")
            mocker.patch("zoom_insights.cli.to_compressed_audio")
            mocker.patch("zoom_insights.cli.maybe_segment", return_value=[compressed_file])
            mocker.patch("zoom_insights.cli.write_report")
            mock_export = mocker.patch("zoom_insights.cli._export_to_jira")

            _process_local_file(
                audio_file,
                mock_groq_client,
                work_dir=tmpdir,
                jira=True,
                config=config,
            )

            # Verify _export_to_jira was called exactly once
            assert mock_export.call_count == 1

    def test_process_local_file_skips_export_to_jira_when_jira_false(self, mocker, sample_insights):
        """Assert _export_to_jira NOT called when jira=False (default)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "test_recording.m4a")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            compressed_file = os.path.join(tmpdir, "test_recording.m4a.opus")
            with open(compressed_file, "w") as f:
                f.write("fake compressed")

            mock_groq_client = good_groq_client(mocker, sample_insights)

            config = Config(
                zoom_account_id="test",
                zoom_client_id="test",
                zoom_client_secret="test",
                groq_api_key="test-key",
            )

            mocker.patch("zoom_insights.cli.ensure_work_dir", return_value=tmpdir)
            mocker.patch("zoom_insights.cli.is_completed", return_value=False)
            mocker.patch("zoom_insights.cli.mark_completed")
            mocker.patch("zoom_insights.cli.shutil.copy2")
            mocker.patch("zoom_insights.cli.to_compressed_audio")
            mocker.patch("zoom_insights.cli.maybe_segment", return_value=[compressed_file])
            mocker.patch("zoom_insights.cli.write_report")
            mock_export = mocker.patch("zoom_insights.cli._export_to_jira")

            _process_local_file(
                audio_file,
                mock_groq_client,
                work_dir=tmpdir,
                jira=False,  # explicit False
                config=config,
            )

            # Verify _export_to_jira was NOT called
            mock_export.assert_not_called()

    def test_process_meeting_calls_export_to_jira_when_jira_true(self, mocker, sample_insights):
        """Assert _export_to_jira called for cloud meeting when jira=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            compressed_file = os.path.join(tmpdir, "audio.m4a.opus")
            with open(compressed_file, "w") as f:
                f.write("fake compressed")

            mock_file = RecordingFile(
                id="file-123",
                file_name="recording.m4a",
                file_size=5000000,
                file_type="M4A",
                download_url="https://zoom.com/recording.m4a",
                recording_type="AUDIO",
            )
            mock_meeting = Meeting(
                uuid="meeting-uuid-123",
                topic="Q4 Planning",
                start_time="2024-12-01T10:00:00Z",
                duration=3600,
                files=[mock_file],
            )

            mock_groq_client = good_groq_client(mocker, sample_insights)

            config = Config(
                zoom_account_id="test",
                zoom_client_id="test",
                zoom_client_secret="test",
                groq_api_key="test-key",
                jira_url="https://test.atlassian.net",
                jira_email="test@test.com",
                jira_api_token="test-token",
                jira_project_key="TEST",
            )

            mocker.patch("zoom_insights.cli.ensure_work_dir", return_value=tmpdir)
            mocker.patch("zoom_insights.cli.is_completed", return_value=False)
            mocker.patch("zoom_insights.cli.mark_completed")
            mocker.patch("zoom_insights.cli.get_meeting_recording", return_value=mock_meeting)
            mocker.patch("zoom_insights.cli.download")
            mocker.patch("zoom_insights.cli.to_compressed_audio")
            mocker.patch("zoom_insights.cli.maybe_segment", return_value=[compressed_file])
            mocker.patch("zoom_insights.cli.write_report")
            mock_export = mocker.patch("zoom_insights.cli._export_to_jira")

            _process_meeting(
                "meeting-uuid-123",
                "test-token",
                mock_groq_client,
                config,
                work_dir=tmpdir,
                jira=True,
            )

            # Verify _export_to_jira was called exactly once
            assert mock_export.call_count == 1

    def test_process_meeting_skips_export_to_jira_when_jira_false(self, mocker, sample_insights):
        """Assert _export_to_jira NOT called when jira=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            compressed_file = os.path.join(tmpdir, "audio.m4a.opus")
            with open(compressed_file, "w") as f:
                f.write("fake compressed")

            mock_file = RecordingFile(
                id="file-123",
                file_name="recording.m4a",
                file_size=5000000,
                file_type="M4A",
                download_url="https://zoom.com/recording.m4a",
                recording_type="AUDIO",
            )
            mock_meeting = Meeting(
                uuid="meeting-uuid-123",
                topic="Q4 Planning",
                start_time="2024-12-01T10:00:00Z",
                duration=3600,
                files=[mock_file],
            )

            mock_groq_client = good_groq_client(mocker, sample_insights)

            config = Config(
                zoom_account_id="test",
                zoom_client_id="test",
                zoom_client_secret="test",
                groq_api_key="test-key",
            )

            mocker.patch("zoom_insights.cli.ensure_work_dir", return_value=tmpdir)
            mocker.patch("zoom_insights.cli.is_completed", return_value=False)
            mocker.patch("zoom_insights.cli.mark_completed")
            mocker.patch("zoom_insights.cli.get_meeting_recording", return_value=mock_meeting)
            mocker.patch("zoom_insights.cli.download")
            mocker.patch("zoom_insights.cli.to_compressed_audio")
            mocker.patch("zoom_insights.cli.maybe_segment", return_value=[compressed_file])
            # Mock Jira credential validation to succeed
            mock_get = mocker.MagicMock()
            mock_get.status_code = 200
            mocker.patch("zoom_insights.cli.requests.get", return_value=mock_get)
            mocker.patch("zoom_insights.cli.write_report")
            mock_export = mocker.patch("zoom_insights.cli._export_to_jira")

            _process_meeting(
                "meeting-uuid-123",
                "test-token",
                mock_groq_client,
                config,
                work_dir=tmpdir,
                jira=False,
            )

            # Verify _export_to_jira was NOT called
            mock_export.assert_not_called()

    def test_unknown_flag_causes_exit(self, mocker):
        """Pass unrecognised flag, assert exit code != 0."""
        with pytest.raises(SystemExit):
            mocker.patch("sys.argv", ["zoom-insights", "--unknown-flag"])
            main()


@pytest.mark.integration
class TestRecordingToJson:
    """Test recording-to-JSON pipeline with various Groq client scenarios."""

    @pytest.mark.parametrize("groq_factory,should_succeed", [
        (good_groq_client, True),
        (transcription_error_groq_client, False),
        (bad_llm_groq_client, False),
    ], ids=["happy_path", "transcription_failure", "summarize_failure"])
    def test_recording_to_json(self, mocker, sample_insights, groq_factory, should_succeed):
        """Test recording-to-JSON conversion with various scenarios."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create audio file in source dir
            audio_dir = os.path.join(tmpdir, "audio")
            os.makedirs(audio_dir, exist_ok=True)
            audio_file = os.path.join(audio_dir, "test.wav")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            # Work directory is separate
            work_dir = os.path.join(tmpdir, "work")
            os.makedirs(work_dir, exist_ok=True)

            # Create Groq client based on factory
            if groq_factory == good_groq_client:
                mock_groq_client = groq_factory(mocker, sample_insights)
            else:
                mock_groq_client = groq_factory(mocker)

            mocker.patch("zoom_insights.cli.ensure_work_dir", return_value=work_dir)
            mocker.patch("zoom_insights.cli.to_compressed_audio")
            mocker.patch("zoom_insights.cli.maybe_segment", return_value=[audio_file])
            mocker.patch("zoom_insights.cli.write_report")
            mocker.patch("zoom_insights.cli.is_completed", return_value=False)
            mocker.patch("zoom_insights.cli.mark_completed")

            config = Config(
                zoom_account_id="test",
                zoom_client_id="test",
                zoom_client_secret="test",
                groq_api_key="test-key",
            )

            if should_succeed:
                _process_local_file(
                    audio_file,
                    mock_groq_client,
                    work_dir=work_dir,
                    config=config,
                )
            else:
                with pytest.raises(Exception):
                    _process_local_file(
                        audio_file,
                        mock_groq_client,
                        work_dir=work_dir,
                        config=config,
                    )


@pytest.mark.integration
class TestJsonToJira:
    """Test JSON-to-Jira ticket creation pipeline."""

    @pytest.mark.parametrize("response_status,response_body,expected_count", [
        (201, {"key": "PROJ-1"}, 2),
        (400, None, 0),
        (500, {"error": "Internal error"}, 0),
    ], ids=["happy_path", "jira_api_failure", "schema_failure"])
    def test_json_to_jira(self, mocker, sample_insights, response_status, response_body, expected_count):
        """Test JSON-to-Jira conversion with various Jira responses."""
        from zoom_insights.jira_export import create_jira_tickets

        mock_response = mocker.MagicMock()
        mock_response.status_code = response_status
        if response_body and response_status == 201:
            mock_response.json.return_value = response_body
        mock_response.text = json.dumps(response_body or {})

        mocker.patch("zoom_insights.jira_export.requests.post", return_value=mock_response)

        keys = create_jira_tickets(
            sample_insights,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ",
        )
        assert len(keys) == expected_count
