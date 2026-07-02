"""Tests for audio preparation module."""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest
from zoom_insights.audio import (
    require_ffmpeg,
    to_compressed_audio,
    maybe_segment,
    GROQ_UPLOAD_CAP_MB,
    SEGMENT_DURATION_SECONDS,
)


@pytest.mark.unit
class TestRequireFFmpeg:
    """Tests for require_ffmpeg guard function."""

    def test_require_ffmpeg_present(self, mocker):
        """Test that no error is raised when ffmpeg is available."""
        mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
        # Should not raise
        require_ffmpeg()

    def test_require_ffmpeg_missing(self, mocker):
        """Test that a clear error is raised when ffmpeg is missing."""
        mocker.patch("shutil.which", return_value=None)
        with pytest.raises(RuntimeError) as exc_info:
            require_ffmpeg()
        assert "ffmpeg not found" in str(exc_info.value)
        assert "brew install ffmpeg" in str(exc_info.value)


@pytest.mark.unit
class TestToCompressedAudio:
    """Tests for audio compression function."""

    def test_to_compressed_audio_calls_ffmpeg_with_correct_args(self, mocker):
        """Test that ffmpeg is called with the correct arguments."""
        mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
        mock_run = mocker.patch("subprocess.run")
        to_compressed_audio("/input/audio.m4a", "/output/audio.opus")

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]

        # Verify key arguments are present
        assert "ffmpeg" in cmd
        assert "/input/audio.m4a" in cmd
        assert "/output/audio.opus" in cmd
        assert "-ar" in cmd
        assert "16000" in cmd
        assert "-ac" in cmd
        assert "1" in cmd
        assert "-c:a" in cmd
        assert "libopus" in cmd
        assert "-b:a" in cmd
        assert "16k" in cmd

    def test_to_compressed_audio_raises_on_ffmpeg_error(self, mocker):
        """Test that a RuntimeError is raised if ffmpeg fails."""
        mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "ffmpeg", stderr="Invalid input")
        )

        with pytest.raises(RuntimeError) as exc_info:
            to_compressed_audio("/input/audio.m4a", "/output/audio.opus")
        assert "ffmpeg compression failed" in str(exc_info.value)


@pytest.mark.unit
class TestMaybeSegment:
    """Tests for audio segmentation function."""

    def test_maybe_segment_under_cap_returns_single_file(self, mocker):
        """Test that a file under the cap is returned as a single-item list."""
        mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
        mocker.patch("os.path.getsize", return_value=(GROQ_UPLOAD_CAP_MB - 1) * 1024 * 1024)
        result = maybe_segment("/audio.opus")
        assert result == ["/audio.opus"]

    def test_maybe_segment_over_cap_returns_multiple_files(self, mocker):
        """Test that a file over the cap is segmented into multiple files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake audio file
            audio_path = os.path.join(tmpdir, "audio.opus")
            with open(audio_path, "w") as f:
                f.write("fake audio data")

            mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
            mocker.patch("os.path.getsize", return_value=(GROQ_UPLOAD_CAP_MB + 10) * 1024 * 1024)
            mocker.patch("subprocess.run")
            # Create segment files in the output directory
            segments_dir = os.path.join(tmpdir, "audio_segments")
            os.makedirs(segments_dir, exist_ok=True)
            segment_1 = os.path.join(segments_dir, "audio_000.opus")
            segment_2 = os.path.join(segments_dir, "audio_001.opus")
            segment_3 = os.path.join(segments_dir, "audio_002.opus")
            Path(segment_1).touch()
            Path(segment_2).touch()
            Path(segment_3).touch()

            result = maybe_segment(audio_path)

            assert len(result) == 3
            assert segment_1 in result
            assert segment_2 in result
            assert segment_3 in result

    def test_maybe_segment_calls_ffmpeg_with_segment_time(self, mocker):
        """Test that ffmpeg is called with correct segmentation parameters."""
        mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
        mocker.patch("os.path.getsize", return_value=(GROQ_UPLOAD_CAP_MB + 10) * 1024 * 1024)
        mock_run = mocker.patch("subprocess.run")
        mocker.patch("pathlib.Path.glob", return_value=[])
        mocker.patch("pathlib.Path.mkdir")

        maybe_segment("/audio.opus")

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]

        assert "ffmpeg" in cmd
        assert "-f" in cmd
        assert "segment" in cmd
        assert "-segment_time" in cmd
        assert str(SEGMENT_DURATION_SECONDS) in cmd

    def test_maybe_segment_raises_on_ffmpeg_error(self, mocker):
        """Test that a RuntimeError is raised if ffmpeg segmentation fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio.opus")
            with open(audio_path, "w") as f:
                f.write("fake audio")

            mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
            mocker.patch("os.path.getsize", return_value=(GROQ_UPLOAD_CAP_MB + 10) * 1024 * 1024)
            mocker.patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "ffmpeg", stderr="Error")
            )
            with pytest.raises(RuntimeError) as exc_info:
                maybe_segment(audio_path)
            assert "ffmpeg segmentation failed" in str(exc_info.value)

    def test_maybe_segment_creates_output_directory(self, mocker):
        """Test that output directory is created for segments."""
        mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
        mocker.patch("os.path.getsize", return_value=(GROQ_UPLOAD_CAP_MB + 10) * 1024 * 1024)
        mocker.patch("subprocess.run")
        mocker.patch("pathlib.Path.glob", return_value=[])
        mock_mkdir = mocker.patch("pathlib.Path.mkdir")
        maybe_segment("/audio/audio.opus")
        mock_mkdir.assert_called()

    def test_maybe_segment_at_exact_cap(self, mocker):
        """Test that file at exactly the cap is not segmented."""
        mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
        mocker.patch("os.path.getsize", return_value=GROQ_UPLOAD_CAP_MB * 1024 * 1024)
        result = maybe_segment("/audio.opus")
        assert result == ["/audio.opus"]
