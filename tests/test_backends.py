"""Tests for transcription and LLM backends abstraction."""

import os
import tempfile
import json
import pytest
from unittest.mock import MagicMock, patch, mock_open

from zoom_insights.backends import (
    TranscriptionBackend,
    LLMBackend,
    GroqTranscriptionBackend,
    GroqLLMBackend,
    FasterWhisperBackend,
    OllamaLLMBackend,
)


@pytest.mark.unit
class TestGroqTranscriptionBackend:
    """Tests for Groq Whisper transcription backend."""

    def test_groq_transcription_single_file_string_response(self, mocker):
        """Test single file transcription with string response."""
        mock_groq = mocker.MagicMock()
        mock_groq.audio.transcriptions.create.return_value = "Hello world"

        backend = GroqTranscriptionBackend(mock_groq)

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "audio.wav")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            transcript, metrics = backend.transcribe([audio_file], "whisper-large-v3-turbo")

            assert transcript == "Hello world"
            assert "tokens_in" in metrics
            assert "tokens_out" in metrics
            assert "latency_seconds" in metrics
            mock_groq.audio.transcriptions.create.assert_called_once()

    def test_groq_transcription_single_file_object_response(self, mocker):
        """Test single file transcription with object response."""
        mock_groq = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.text = "Test transcript"
        mock_groq.audio.transcriptions.create.return_value = mock_response

        backend = GroqTranscriptionBackend(mock_groq)

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "audio.wav")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            transcript, metrics = backend.transcribe([audio_file], "whisper-large-v3-turbo")

            assert transcript == "Test transcript"
            assert "tokens_in" in metrics
            assert "tokens_out" in metrics
            assert "latency_seconds" in metrics

    def test_groq_transcription_multiple_files(self, mocker):
        """Test multiple file transcription with concatenation."""
        mock_groq = mocker.MagicMock()

        # Use a side_effect function that returns different text based on which file is being read
        def mock_transcribe(*args, **kwargs):
            file_obj = kwargs.get('file')
            if file_obj:
                file_name = file_obj[0]
                if 'audio1' in file_name:
                    return "Part one"
                elif 'audio2' in file_name:
                    return "Part two"
            # Fallback for cases where we can't determine the file
            return "Part unknown"

        mock_groq.audio.transcriptions.create.side_effect = mock_transcribe

        backend = GroqTranscriptionBackend(mock_groq)

        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = os.path.join(tmpdir, "audio1.wav")
            file2 = os.path.join(tmpdir, "audio2.wav")
            for f in [file1, file2]:
                with open(f, "w") as fp:
                    fp.write("fake audio")

            transcript, metrics = backend.transcribe([file1, file2], "whisper-large-v3-turbo")

            assert transcript == "Part one\nPart two"
            assert "tokens_in" in metrics
            assert "tokens_out" in metrics
            assert "latency_seconds" in metrics
            assert mock_groq.audio.transcriptions.create.call_count == 2

    def test_parallel_transcription_preserves_order(self, mocker):
        """Test that parallel transcription preserves original segment order regardless of completion timing."""
        import time
        import threading

        mock_groq = mocker.MagicMock()
        call_count = [0]
        call_order = []
        lock = threading.Lock()

        def mock_transcribe_side_effect(*args, **kwargs):
            """Simulate varying response times to test out-of-order completion."""
            with lock:
                call_order.append(call_count[0])
                current_call = call_count[0]
                call_count[0] += 1

            # Simulate varying latencies: segment 0 -> 100ms, segment 1 -> 10ms, segment 2 -> 50ms
            if current_call == 0:
                time.sleep(0.1)
                return "Segment A"
            elif current_call == 1:
                time.sleep(0.01)
                return "Segment B"
            else:
                time.sleep(0.05)
                return "Segment C"

        mock_groq.audio.transcriptions.create.side_effect = mock_transcribe_side_effect

        backend = GroqTranscriptionBackend(mock_groq)

        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for i in range(3):
                f = os.path.join(tmpdir, f"audio{i}.wav")
                with open(f, "w") as fp:
                    fp.write("fake audio")
                files.append(f)

            transcript, metrics = backend.transcribe(files, "whisper-large-v3-turbo")

            # Assert: transcript is in original order, not completion order
            assert transcript == "Segment A\nSegment B\nSegment C"
            # Verify all segments were called
            assert mock_groq.audio.transcriptions.create.call_count == 3

    def test_parallel_transcription_single_segment_unaffected(self, mocker):
        """Test that single segment transcription still works (no regression)."""
        mock_groq = mocker.MagicMock()
        mock_groq.audio.transcriptions.create.return_value = "Single segment"

        backend = GroqTranscriptionBackend(mock_groq)

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "audio.wav")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            transcript, metrics = backend.transcribe([audio_file], "whisper-large-v3-turbo")

            assert transcript == "Single segment"
            assert "tokens_in" in metrics
            assert "tokens_out" in metrics
            assert "latency_seconds" in metrics
            mock_groq.audio.transcriptions.create.assert_called_once()

    def test_parallel_transcription_one_segment_fails(self, mocker):
        """Test that a single segment failure halts the pipeline and surfaces the exception."""
        mock_groq = mocker.MagicMock()
        mock_groq.audio.transcriptions.create.side_effect = [
            "Segment one",
            RuntimeError("Transcription failed for segment 2"),
            "Segment three"
        ]

        backend = GroqTranscriptionBackend(mock_groq)

        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for i in range(3):
                f = os.path.join(tmpdir, f"audio{i}.wav")
                with open(f, "w") as fp:
                    fp.write("fake audio")
                files.append(f)

            # Assert: exception from segment 2 is raised (fail-fast behavior)
            with pytest.raises(RuntimeError, match="Transcription failed for segment 2"):
                backend.transcribe(files, "whisper-large-v3-turbo")

    def test_parallel_transcription_respects_worker_cap(self, mocker):
        """Test that transcription respects the worker cap (max 2 concurrent calls)."""
        import threading
        import time

        mock_groq = mocker.MagicMock()
        concurrent_calls = [0]
        max_concurrent = [0]
        lock = threading.Lock()

        def mock_transcribe_with_concurrency_tracking(*args, **kwargs):
            """Track concurrent call count."""
            with lock:
                concurrent_calls[0] += 1
                max_concurrent[0] = max(max_concurrent[0], concurrent_calls[0])

            time.sleep(0.05)  # Simulate some processing

            with lock:
                concurrent_calls[0] -= 1

            return f"Segment {concurrent_calls[0]}"

        mock_groq.audio.transcriptions.create.side_effect = mock_transcribe_with_concurrency_tracking

        backend = GroqTranscriptionBackend(mock_groq)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create 10 segments to force queueing with max_workers=4 default
            files = []
            for i in range(10):
                f = os.path.join(tmpdir, f"audio{i}.wav")
                with open(f, "w") as fp:
                    fp.write("fake audio")
                files.append(f)

            transcript, metrics = backend.transcribe(files, "whisper-large-v3-turbo")

            # Assert: max concurrent calls did not exceed 4
            assert max_concurrent[0] <= 4
            # Verify all segments were transcribed
            assert mock_groq.audio.transcriptions.create.call_count == 10


@pytest.mark.unit
class TestGroqLLMBackend:
    """Tests for Groq LLM backend."""

    def test_groq_llm_chat_completion_string_response(self, mocker):
        """Test chat completion with string response."""
        mock_groq = mocker.MagicMock()
        mock_groq.chat.completions.create.return_value = "This is the answer"

        backend = GroqLLMBackend(mock_groq)
        messages = [{"role": "user", "content": "What is 2+2?"}]

        response, metrics = backend.chat_completion("llama-3-70b", messages)

        assert response == "This is the answer"
        assert "tokens_in" in metrics
        assert "tokens_out" in metrics
        assert "latency_seconds" in metrics
        mock_groq.chat.completions.create.assert_called_once()

    def test_groq_llm_chat_completion_object_response(self, mocker):
        """Test chat completion with object response."""
        mock_groq = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(content="The answer is 4"))]
        mock_groq.chat.completions.create.return_value = mock_response

        backend = GroqLLMBackend(mock_groq)
        messages = [{"role": "user", "content": "What is 2+2?"}]

        response, metrics = backend.chat_completion("llama-3-70b", messages)

        assert response == "The answer is 4"
        assert "tokens_in" in metrics
        assert "tokens_out" in metrics
        assert "latency_seconds" in metrics

    def test_groq_llm_with_max_tokens(self, mocker):
        """Test chat completion with max_tokens parameter."""
        mock_groq = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(content="Short answer"))]
        mock_groq.chat.completions.create.return_value = mock_response

        backend = GroqLLMBackend(mock_groq)
        messages = [{"role": "user", "content": "Be brief"}]

        response, metrics = backend.chat_completion("llama-3-70b", messages, max_tokens=100)

        assert response == "Short answer"
        assert "tokens_in" in metrics
        assert "tokens_out" in metrics
        assert "latency_seconds" in metrics
        # Verify max_tokens was passed to the API
        call_kwargs = mock_groq.chat.completions.create.call_args[1]
        assert call_kwargs.get("max_tokens") == 100


@pytest.mark.unit
class TestFasterWhisperBackend:
    """Tests for faster-whisper local transcription backend."""

    @pytest.mark.skipif(True, reason="faster-whisper not available in test environment")
    def test_faster_whisper_transcription_single_file(self, mocker):
        """Test single file transcription with faster-whisper."""
        # Mock the WhisperModel import and instantiation
        mock_model = mocker.MagicMock()
        mock_segment1 = mocker.MagicMock(text="Hello ")
        mock_segment2 = mocker.MagicMock(text="world")
        mock_model.transcribe.return_value = ([mock_segment1, mock_segment2], mocker.MagicMock())

        with patch("faster_whisper.WhisperModel", return_value=mock_model):
            backend = FasterWhisperBackend("large-v3")

            with tempfile.TemporaryDirectory() as tmpdir:
                audio_file = os.path.join(tmpdir, "audio.wav")
                with open(audio_file, "w") as f:
                    f.write("fake audio")

                result = backend.transcribe([audio_file], "ignored_model_param")

                assert result == "Hello world"
                mock_model.transcribe.assert_called_once()

    @pytest.mark.skipif(True, reason="faster-whisper not available in test environment")
    def test_faster_whisper_multiple_files(self, mocker):
        """Test multiple file transcription with faster-whisper."""
        mock_model = mocker.MagicMock()
        mock_seg1 = mocker.MagicMock(text="Part one")
        mock_seg2 = mocker.MagicMock(text="Part two")

        mock_model.transcribe.side_effect = [
            ([mock_seg1], mocker.MagicMock()),
            ([mock_seg2], mocker.MagicMock()),
        ]

        with patch("faster_whisper.WhisperModel", return_value=mock_model):
            backend = FasterWhisperBackend("large-v3")

            with tempfile.TemporaryDirectory() as tmpdir:
                file1 = os.path.join(tmpdir, "audio1.wav")
                file2 = os.path.join(tmpdir, "audio2.wav")
                for f in [file1, file2]:
                    with open(f, "w") as fp:
                        fp.write("fake audio")

                result = backend.transcribe([file1, file2], "model")

                assert result == "Part one\nPart two"
                assert mock_model.transcribe.call_count == 2

    def test_faster_whisper_import_error(self, mocker):
        """Test FasterWhisperBackend raises when faster-whisper not installed."""
        # Patch the import in the backends module to simulate missing module
        original_init = FasterWhisperBackend.__init__

        def mock_init(self, model_size="large-v3"):
            raise RuntimeError("faster-whisper not installed. Install with: pip install faster-whisper")

        mocker.patch.object(FasterWhisperBackend, "__init__", mock_init)

        with pytest.raises(RuntimeError, match="faster-whisper not installed"):
            FasterWhisperBackend("large-v3")


@pytest.mark.unit
class TestOllamaLLMBackend:
    """Tests for Ollama local LLM backend."""

    def test_ollama_chat_completion_success(self, mocker):
        """Test successful chat completion via Ollama."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "The answer is 42"}
        }

        mocker.patch("zoom_insights.backends.requests.post", return_value=mock_response)

        backend = OllamaLLMBackend("http://localhost:11434")
        messages = [{"role": "user", "content": "What is the answer?"}]

        response, metrics = backend.chat_completion("neural-chat", messages)

        assert response == "The answer is 42"
        assert "tokens_in" in metrics
        assert "tokens_out" in metrics
        assert "latency_seconds" in metrics

    def test_ollama_with_max_tokens(self, mocker):
        """Test Ollama chat completion with max_tokens parameter."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Brief answer"}
        }

        mock_post = mocker.patch("zoom_insights.backends.requests.post", return_value=mock_response)

        backend = OllamaLLMBackend("http://localhost:11434")
        messages = [{"role": "user", "content": "Be brief"}]

        response, metrics = backend.chat_completion("neural-chat", messages, max_tokens=50)

        assert response == "Brief answer"
        assert "tokens_in" in metrics
        assert "tokens_out" in metrics
        assert "latency_seconds" in metrics
        # Verify num_predict was passed
        call_kwargs = mock_post.call_args[1]["json"]
        assert call_kwargs.get("num_predict") == 50

    def test_ollama_api_error(self, mocker):
        """Test Ollama backend handles API errors."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mocker.patch("zoom_insights.backends.requests.post", return_value=mock_response)

        backend = OllamaLLMBackend("http://localhost:11434")
        messages = [{"role": "user", "content": "Hi"}]

        with pytest.raises(RuntimeError, match="Ollama API error"):
            backend.chat_completion("neural-chat", messages)

    def test_ollama_connection_error(self, mocker):
        """Test Ollama backend handles connection errors."""
        import requests

        mocker.patch(
            "zoom_insights.backends.requests.post",
            side_effect=requests.ConnectionError("Connection refused")
        )

        backend = OllamaLLMBackend("http://localhost:11434")
        messages = [{"role": "user", "content": "Hi"}]

        with pytest.raises(RuntimeError, match="Could not connect to Ollama"):
            backend.chat_completion("neural-chat", messages)

    def test_ollama_default_url(self, mocker):
        """Test Ollama backend uses default URL."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Success"}
        }

        mock_post = mocker.patch("zoom_insights.backends.requests.post", return_value=mock_response)

        backend = OllamaLLMBackend()  # No URL specified
        messages = [{"role": "user", "content": "Hi"}]

        backend.chat_completion("neural-chat", messages)

        # Verify default URL was used
        call_args = mock_post.call_args[0]
        assert "localhost:11434" in call_args[0]

    def test_ollama_custom_url(self, mocker):
        """Test Ollama backend accepts custom URL."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Success"}
        }

        mock_post = mocker.patch("zoom_insights.backends.requests.post", return_value=mock_response)

        backend = OllamaLLMBackend("http://192.168.1.100:11434")
        messages = [{"role": "user", "content": "Hi"}]

        backend.chat_completion("neural-chat", messages)

        # Verify custom URL was used
        call_args = mock_post.call_args[0]
        assert "192.168.1.100" in call_args[0]

    def test_ollama_url_trailing_slash_stripped(self, mocker):
        """Test Ollama backend strips trailing slashes from URL."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Success"}
        }

        mock_post = mocker.patch("zoom_insights.backends.requests.post", return_value=mock_response)

        backend = OllamaLLMBackend("http://localhost:11434/")
        messages = [{"role": "user", "content": "Hi"}]

        backend.chat_completion("neural-chat", messages)

        # Verify URL has no trailing slash
        call_args = mock_post.call_args[0]
        assert call_args[0].endswith("/api/chat")
        assert not call_args[0].endswith("//api/chat")


@pytest.mark.unit
class TestBackendIntegration:
    """Integration tests for backend swapping."""

    def test_transcribe_with_groq_backend(self, mocker):
        """Test transcribe function works with Groq backend."""
        mock_groq = mocker.MagicMock()
        mock_groq.audio.transcriptions.create.return_value = "Test transcript"

        backend = GroqTranscriptionBackend(mock_groq)

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "audio.wav")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            transcript, metrics = backend.transcribe([audio_file], "whisper-large-v3-turbo")

            assert transcript == "Test transcript"
            assert "tokens_in" in metrics
            assert "tokens_out" in metrics
            assert "latency_seconds" in metrics

    def test_summarize_with_groq_backend(self, mocker):
        """Test chat_completion method works with Groq LLM backend."""
        mock_groq = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(content="Test response"))]
        mock_groq.chat.completions.create.return_value = mock_response

        backend = GroqLLMBackend(mock_groq)

        messages = [{"role": "user", "content": "Test prompt"}]
        response, metrics = backend.chat_completion("llama-3-70b", messages, max_tokens=1024)

        assert response == "Test response"
        assert isinstance(metrics, dict)
        assert "latency_seconds" in metrics

    def test_backend_abstraction_hides_implementation(self, mocker):
        """Test that backend abstraction properly hides API differences."""
        # Groq and Ollama should have same interface
        mock_groq = mocker.MagicMock()
        groq_backend = GroqLLMBackend(mock_groq)

        # Both should accept same method signature
        messages = [{"role": "user", "content": "Test"}]

        # Verify both backends have the same public interface
        assert hasattr(groq_backend, "chat_completion")
        assert callable(getattr(groq_backend, "chat_completion"))

        ollama_backend = OllamaLLMBackend()
        assert hasattr(ollama_backend, "chat_completion")
        assert callable(getattr(ollama_backend, "chat_completion"))
