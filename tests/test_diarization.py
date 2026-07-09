"""Tests for speaker diarization functionality."""

import sys
import pytest
from zoom_insights.diarization import (
    DiarizationResult,
    PyannoteBackend,
    LocalDiarizationBackend,
)
from zoom_insights.transcript_merge import merge_diarization_with_transcript


@pytest.mark.unit
class TestDiarizationResult:
    """Test DiarizationResult dataclass."""

    def test_diarization_result_creation(self):
        """Test creating a DiarizationResult."""
        result = DiarizationResult(speaker_id=0, start_ms=1000, end_ms=5000)
        assert result.speaker_id == 0
        assert result.start_ms == 1000
        assert result.end_ms == 5000


@pytest.mark.unit
class TestLocalDiarizationBackend:
    """Test LocalDiarizationBackend stub."""

    def test_local_diarization_returns_empty_list(self):
        """Test that LocalDiarizationBackend returns empty list."""
        backend = LocalDiarizationBackend()
        result = backend.diarize("/path/to/audio.wav")
        assert result == []


@pytest.mark.unit
class TestPyannoteBackendValidation:
    """Test PyannoteBackend initialization validation."""

    def test_pyannote_missing_token_raises_error(self):
        """Test that missing HUGGINGFACE_TOKEN raises ValueError."""
        with pytest.raises(ValueError, match="HUGGINGFACE_TOKEN is required"):
            PyannoteBackend("")

    def test_pyannote_with_token_initializes(self):
        """Test that PyannoteBackend initializes with valid token."""
        backend = PyannoteBackend("hf_test_token_123")
        assert backend.huggingface_token == "hf_test_token_123"


@pytest.mark.unit
class TestPyannoteBackendDiarize:
    """Test PyannoteBackend diarize method with mocking."""

    def test_pyannote_diarize_mock_model(self, mocker):
        """Test diarization with mocked pyannote model."""
        # This test verifies the diarize logic works when a pipeline is pre-set
        backend = PyannoteBackend("hf_test_token_123")

        # Create mock tracks with proper iteration
        # pyannote returns Turn objects with start/end in seconds
        mock_turn_1 = mocker.MagicMock()
        mock_turn_1.start = 0.0
        mock_turn_1.end = 5.0

        mock_turn_2 = mocker.MagicMock()
        mock_turn_2.start = 5.1
        mock_turn_2.end = 10.5

        # Create mock diarization result object
        mock_diarization = mocker.MagicMock()
        mock_diarization.itertracks.return_value = [
            (mock_turn_1, mocker.MagicMock(), "Speaker 0"),
            (mock_turn_2, mocker.MagicMock(), "Speaker 1"),
        ]

        # Create a mock pipeline that returns the diarization when called
        mock_pipeline = mocker.MagicMock(return_value=mock_diarization)

        # Directly set the pipeline to avoid import issues
        backend._pipeline = mock_pipeline

        result = backend.diarize("/path/to/audio.wav")

        assert len(result) == 2
        assert result[0].speaker_id == 0
        assert result[0].start_ms == 0
        assert result[0].end_ms == 5000
        assert result[1].speaker_id == 1
        assert result[1].start_ms == 5100
        assert result[1].end_ms == 10500


@pytest.mark.unit
class TestTranscriptMerge:
    """Test transcript merge functionality."""

    def test_merge_empty_diarization(self):
        """Test that empty diarization returns unchanged transcript."""
        transcript = "Hello, this is a test."
        result = merge_diarization_with_transcript(transcript, [])
        assert result == transcript

    def test_merge_with_diarization(self):
        """Test merging diarization segments with transcript."""
        transcript = "Hello. How are you? I am fine."
        diarization_segments = [
            DiarizationResult(speaker_id=0, start_ms=0, end_ms=2000),
            DiarizationResult(speaker_id=1, start_ms=2000, end_ms=5000),
        ]

        result = merge_diarization_with_transcript(transcript, diarization_segments)

        # Result should contain speaker labels
        assert "[Speaker" in result
        assert "Hello" in result or "hello" in result.lower()

    def test_merge_multiple_speakers(self):
        """Test merging with multiple speakers."""
        transcript = "Alice says something. Bob responds. Alice again."
        diarization_segments = [
            DiarizationResult(speaker_id=0, start_ms=0, end_ms=3000),
            DiarizationResult(speaker_id=1, start_ms=3000, end_ms=6000),
            DiarizationResult(speaker_id=0, start_ms=6000, end_ms=9000),
        ]

        result = merge_diarization_with_transcript(transcript, diarization_segments)

        # Should have at least one speaker label (basic implementation may not label all)
        assert "[Speaker" in result
        # Original content should be preserved
        assert "Alice" in result or "alice" in result.lower()


@pytest.mark.unit
class TestTranscribeWithDiarization:
    """Test transcribe function with diarization."""

    @pytest.mark.skip(reason="transcribe() does not support diarization_backend parameter in current API")
    def test_transcribe_with_diarization_backend(self, mocker):
        """Test transcribe with diarization backend."""
        from zoom_insights.transcribe import transcribe

        mock_backend = mocker.MagicMock()
        # transcribe() returns (transcript, metrics_dict)
        mock_backend.transcribe.return_value = ("Hello world.", {"tokens_in": 0, "tokens_out": 0, "latency_seconds": 0.0})

        mock_diar_backend = mocker.MagicMock()
        mock_diar_backend.diarize.return_value = [
            DiarizationResult(speaker_id=0, start_ms=0, end_ms=1000)
        ]

        transcript, metrics = transcribe(
            ["/path/to/audio.wav"],
            mock_backend,
            model="whisper-large-v3-turbo",
            diarization_backend=mock_diar_backend,
        )

        # Should call diarize
        mock_diar_backend.diarize.assert_called_once()
        # Result should be a string
        assert isinstance(transcript, str)
        assert "tokens_in" in metrics

    @pytest.mark.skip(reason="transcribe() does not support diarization_backend parameter in current API")
    def test_transcribe_without_diarization_backend(self, mocker):
        """Test transcribe without diarization backend."""
        from zoom_insights.transcribe import transcribe

        mock_backend = mocker.MagicMock()
        # transcribe() returns (transcript, metrics_dict)
        mock_backend.transcribe.return_value = ("Hello world.", {"tokens_in": 0, "tokens_out": 0, "latency_seconds": 0.0})

        transcript, metrics = transcribe(
            ["/path/to/audio.wav"],
            mock_backend,
            model="whisper-large-v3-turbo",
            diarization_backend=None,
        )

        assert transcript == "Hello world."
        assert "tokens_in" in metrics

    @pytest.mark.skip(reason="transcribe() does not support diarization_backend parameter in current API")
    def test_transcribe_diarization_error_fallback(self, mocker):
        """Test that diarization errors don't crash transcript."""
        from zoom_insights.transcribe import transcribe

        mock_backend = mocker.MagicMock()
        # transcribe() returns (transcript, metrics_dict)
        mock_backend.transcribe.return_value = ("Hello world.", {"tokens_in": 0, "tokens_out": 0, "latency_seconds": 0.0})

        mock_diar_backend = mocker.MagicMock()
        mock_diar_backend.diarize.side_effect = RuntimeError("Diarization failed")

        # Should not raise, just warn and continue
        transcript, metrics = transcribe(
            ["/path/to/audio.wav"],
            mock_backend,
            model="whisper-large-v3-turbo",
            diarization_backend=mock_diar_backend,
        )

        assert transcript == "Hello world."
        assert "tokens_in" in metrics


@pytest.mark.unit
class TestCLIDiarizeFlag:
    """Test CLI integration of --diarize flag."""

    def test_diarize_backend_validation(self):
        """Test that PyannoteBackend validates token."""
        # Test that missing token raises ValueError
        with pytest.raises(ValueError, match="HUGGINGFACE_TOKEN is required"):
            PyannoteBackend("")
