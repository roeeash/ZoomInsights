"""Tests for audio transcription module."""

import os
import tempfile
from pathlib import Path
import pytest
from zoom_insights.transcribe import (
    transcribe,
    parse_vtt,
    download_and_parse_vtt,
)


@pytest.mark.unit
class TestTranscribe:
    """Tests for the transcribe function."""

    def test_transcribe_single_segment_string_response(self, mocker):
        """Test transcribing a single segment with string response from Groq."""
        mock_client = mocker.MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Hello, this is a test."

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "audio.wav")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            result = transcribe([audio_file], mock_client)

            assert result == "Hello, this is a test."
            mock_client.audio.transcriptions.create.assert_called_once()

    def test_transcribe_single_segment_object_response(self, mocker):
        """Test transcribing a single segment with object response from Groq."""
        mock_response = mocker.MagicMock()
        mock_response.text = "Hello, this is a test."

        mock_client = mocker.MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "audio.wav")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            result = transcribe([audio_file], mock_client)

            assert result == "Hello, this is a test."

    def test_transcribe_multiple_segments(self, mocker):
        """Test transcribing multiple segments and joining them."""
        mock_client = mocker.MagicMock()
        mock_client.audio.transcriptions.create.side_effect = [
            "First segment.",
            "Second segment.",
            "Third segment.",
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_files = []
            for i in range(3):
                audio_file = os.path.join(tmpdir, f"audio_{i}.wav")
                with open(audio_file, "w") as f:
                    f.write("fake audio")
                audio_files.append(audio_file)

            result = transcribe(audio_files, mock_client)

            assert "First segment." in result
            assert "Second segment." in result
            assert "Third segment." in result
            assert mock_client.audio.transcriptions.create.call_count == 3

    def test_transcribe_calls_with_correct_model(self, mocker):
        """Test that transcribe uses the correct Groq model."""
        mock_client = mocker.MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Test"

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "audio.wav")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            transcribe([audio_file], mock_client)

            call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
            assert call_kwargs["model"] == "whisper-large-v3-turbo"
            assert call_kwargs["response_format"] == "text"

    def test_transcribe_empty_list_returns_empty_string(self, mocker):
        """Test that an empty list of paths returns an empty string."""
        mock_client = mocker.MagicMock()

        result = transcribe([], mock_client)

        assert result == ""


@pytest.mark.unit
class TestParseVTT:
    """Tests for VTT parsing function."""

    def test_parse_vtt_removes_webvtt_header(self):
        """Test that WEBVTT header is removed."""
        vtt_content = """WEBVTT

00:00:00.000 --> 00:00:02.000
Hello, world."""

        result = parse_vtt(vtt_content)

        assert "WEBVTT" not in result
        assert "Hello, world" in result

    def test_parse_vtt_removes_timestamps(self):
        """Test that timestamps are removed."""
        vtt_content = """00:00:00.000 --> 00:00:02.000
Hello, world.

00:00:02.000 --> 00:00:04.000
This is a test."""

        result = parse_vtt(vtt_content)

        assert "-->" not in result
        assert "Hello, world" in result
        assert "This is a test" in result

    def test_parse_vtt_removes_cue_numbers(self):
        """Test that cue numbers are removed."""
        vtt_content = """WEBVTT

1
00:00:00.000 --> 00:00:02.000
Hello, world.

2
00:00:02.000 --> 00:00:04.000
This is a test."""

        result = parse_vtt(vtt_content)

        # Numbers should not be in the output (they're filtered as digits-only lines)
        assert "Hello, world" in result
        assert "This is a test" in result

    def test_parse_vtt_preserves_text(self):
        """Test that actual text content is preserved."""
        vtt_content = """WEBVTT

1
00:00:00.000 --> 00:00:02.000
This is a meeting transcript.

2
00:00:02.000 --> 00:00:05.000
We discussed important topics."""

        result = parse_vtt(vtt_content)

        assert "This is a meeting transcript" in result
        assert "We discussed important topics" in result

    def test_parse_vtt_empty_string(self):
        """Test parsing empty VTT content."""
        result = parse_vtt("")
        assert result == ""

    def test_parse_vtt_only_metadata(self):
        """Test parsing VTT with only metadata and no content."""
        vtt_content = """WEBVTT

NOTE This file was generated by Zoom."""

        result = parse_vtt(vtt_content)
        assert result == ""


@pytest.mark.unit
class TestDownloadAndParseVTT:
    """Tests for VTT download function."""

    def test_download_and_parse_vtt_with_transcript_file(self, mocker):
        """Test downloading and parsing VTT when TRANSCRIPT file exists."""
        from zoom_insights.zoom_client import RecordingFile

        mock_file = RecordingFile(
            id="123",
            file_name="transcript.vtt",
            file_size=5000,
            file_type="VTT",
            download_url="https://zoom.com/transcript.vtt",
            recording_type="TRANSCRIPT",
        )

        vtt_content = """WEBVTT

1
00:00:00.000 --> 00:00:02.000
Hello, world."""

        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.text = vtt_content
        mocker.patch("requests.get", return_value=mock_response)

        result = download_and_parse_vtt("test-uuid", [mock_file], "test-token")

        assert "Hello, world" in result
        assert "WEBVTT" not in result

    def test_download_and_parse_vtt_no_transcript_file(self, mocker):
        """Test that empty string is returned when no TRANSCRIPT file exists."""
        from zoom_insights.zoom_client import RecordingFile

        mock_file = RecordingFile(
            id="123",
            file_name="audio.m4a",
            file_size=5000000,
            file_type="M4A",
            download_url="https://zoom.com/audio.m4a",
            recording_type="AUDIO",
        )

        result = download_and_parse_vtt("test-uuid", [mock_file], "test-token")

        assert result == ""

    def test_download_and_parse_vtt_http_error(self, mocker):
        """Test that empty string is returned on HTTP error."""
        from zoom_insights.zoom_client import RecordingFile

        mock_file = RecordingFile(
            id="123",
            file_name="transcript.vtt",
            file_size=5000,
            file_type="VTT",
            download_url="https://zoom.com/transcript.vtt",
            recording_type="TRANSCRIPT",
        )

        mock_response = mocker.MagicMock()
        mock_response.status_code = 404
        mocker.patch("requests.get", return_value=mock_response)

        result = download_and_parse_vtt("test-uuid", [mock_file], "test-token")

        assert result == ""

    def test_transcribe_with_vtt_flag_succeeds(self, mocker):
        """Test that use_vtt flag uses VTT when available."""
        from zoom_insights.zoom_client import RecordingFile

        mock_vtt_file = RecordingFile(
            id="123",
            file_name="transcript.vtt",
            file_size=5000,
            file_type="VTT",
            download_url="https://zoom.com/transcript.vtt",
            recording_type="TRANSCRIPT",
        )

        vtt_content = """WEBVTT

1
00:00:00.000 --> 00:00:02.000
VTT transcript text."""

        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.text = vtt_content
        mocker.patch("requests.get", return_value=mock_response)

        mock_client = mocker.MagicMock()

        result = transcribe(
            [],
            mock_client,
            use_vtt=True,
            meeting_uuid="test-uuid",
            files=[mock_vtt_file],
            token="test-token",
        )

        assert "VTT transcript text" in result

    def test_transcribe_with_vtt_flag_falls_back_to_whisper(self, mocker):
        """Test that transcribe falls back to Whisper when VTT unavailable."""
        mock_client = mocker.MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Whisper transcript"

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "audio.wav")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            result = transcribe(
                [audio_file],
                mock_client,
                use_vtt=True,
                files=[],
                token="test-token",
            )

            assert "Whisper transcript" in result
