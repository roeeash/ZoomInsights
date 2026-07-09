"""Abstraction layer for transcription and LLM backends.

Allows swapping between Groq API and local implementations (faster-whisper, Ollama)
without changing core pipeline logic.
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

logger = logging.getLogger(__name__)


class TranscriptionBackend(ABC):
    """Abstract base class for transcription backends."""

    @abstractmethod
    def transcribe(self, paths: list[str], model: str, max_workers: int = 4) -> tuple[str, dict]:
        """Transcribe one or more audio files.

        Args:
            paths: List of audio file paths to transcribe.
            model: Model identifier (backend-specific).
            max_workers: Maximum number of concurrent transcription workers (default: 4).

        Returns:
            Tuple of (transcript_text, metrics_dict) where metrics_dict contains:
            - 'tokens_in': int (input tokens, 0 for local models)
            - 'tokens_out': int (output tokens, 0 for local models)
            - 'latency_seconds': float (wall-clock time)

        Raises:
            RuntimeError: on transcription failure.
        """
        pass


class LLMBackend(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    def chat_completion(
        self, model: str, messages: list[dict], max_tokens: Optional[int] = None
    ) -> tuple[str, dict]:
        """Make a chat completion request.

        Args:
            model: Model identifier (backend-specific).
            messages: List of message dicts with 'role' and 'content' keys.
            max_tokens: Optional max tokens in response.

        Returns:
            Tuple of (response_text, metrics_dict) where metrics_dict contains:
            - 'tokens_in': int (input tokens)
            - 'tokens_out': int (output tokens)
            - 'latency_seconds': float (wall-clock time)

        Raises:
            RuntimeError: on API failure.
        """
        pass


class GroqTranscriptionBackend(TranscriptionBackend):
    """Transcription backend using Groq Whisper API."""

    def __init__(self, groq_client: Any):
        """Initialize with a Groq client.

        Args:
            groq_client: An initialized Groq API client.
        """
        self.groq_client = groq_client

    def transcribe(self, paths: list[str], model: str, max_workers: int = 4) -> tuple[str, dict]:
        """Transcribe using Groq Whisper API.

        Args:
            paths: List of audio file paths to transcribe.
            model: Model identifier.
            max_workers: Maximum number of concurrent transcription workers (default: 4).
        """
        import time
        from pathlib import Path
        from zoom_insights.retry import with_retry

        def transcribe_segment(index: int, path: str) -> tuple[int, str, float, int, int]:
            """Transcribe a single segment and return (index, text, latency, tokens_in, tokens_out)."""
            logger.info(f"Transcribing {path} with Groq")
            start_time = time.time()

            with open(path, "rb") as audio_file:
                response = with_retry(
                    self.groq_client.audio.transcriptions.create,
                    file=(Path(path).name, audio_file),
                    model=model,
                    response_format="text",
                )

            latency = time.time() - start_time

            # Handle both string and object responses
            if isinstance(response, str):
                text = response
            else:
                text = getattr(response, "text", str(response))

            # Try to extract token counts from response
            tokens_in = 0
            tokens_out = 0
            if hasattr(response, "usage"):
                tokens_in = getattr(response.usage, "prompt_tokens", 0)
                tokens_out = getattr(response.usage, "completion_tokens", 0)

            logger.debug(f"Segment transcribed: {len(text)} characters in {latency:.2f}s")
            return index, text, latency, tokens_in, tokens_out

        # Use ThreadPoolExecutor to transcribe segments concurrently
        transcript_dict = {}
        total_input_tokens = 0
        total_output_tokens = 0
        total_latency = 0.0
        max_concurrent_workers = max(1, min(len(paths), max_workers))

        with ThreadPoolExecutor(max_workers=max_concurrent_workers) as executor:
            # Submit all transcription tasks
            futures = {
                executor.submit(transcribe_segment, idx, path): idx
                for idx, path in enumerate(paths)
            }

            # Collect results, preserving order and propagating exceptions
            for future in as_completed(futures):
                try:
                    idx, text, latency, tokens_in, tokens_out = future.result()
                    transcript_dict[idx] = text
                    total_latency += latency
                    total_input_tokens += tokens_in
                    total_output_tokens += tokens_out
                except Exception as e:
                    # Fail-fast: any segment exception halts the pipeline
                    raise e

        # Reassemble transcript in original segment order
        transcript_parts = [transcript_dict[i] for i in range(len(paths))]
        full_transcript = "\n".join(transcript_parts)
        logger.info(f"Full transcript: {len(full_transcript)} characters")

        metrics = {
            "tokens_in": total_input_tokens,
            "tokens_out": total_output_tokens,
            "latency_seconds": total_latency,
        }

        return full_transcript, metrics


class GroqLLMBackend(LLMBackend):
    """LLM backend using Groq chat completions API."""

    def __init__(self, groq_client: Any):
        """Initialize with a Groq client.

        Args:
            groq_client: An initialized Groq API client.
        """
        self.groq_client = groq_client

    def chat_completion(
        self, model: str, messages: list[dict], max_tokens: Optional[int] = None
    ) -> tuple[str, dict]:
        """Make a chat completion using Groq."""
        import time
        from zoom_insights.retry import with_retry

        kwargs = {"model": model, "messages": messages}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        start_time = time.time()
        response = with_retry(self.groq_client.chat.completions.create, **kwargs)
        latency = time.time() - start_time

        # Extract text from response
        if isinstance(response, str):
            content = response
            tokens_in = 0
            tokens_out = 0
        else:
            # Handle Groq response object
            if hasattr(response, "choices") and response.choices:
                content = response.choices[0].message.content
            else:
                content = str(response)

            # Extract token counts
            tokens_in = 0
            tokens_out = 0
            if hasattr(response, "usage"):
                tokens_in = getattr(response.usage, "prompt_tokens", 0)
                tokens_out = getattr(response.usage, "completion_tokens", 0)

        metrics = {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_seconds": latency,
        }

        return content, metrics


class FasterWhisperBackend(TranscriptionBackend):
    """Transcription backend using faster-whisper (local)."""

    def __init__(self, model_size: str = "large-v3"):
        """Initialize with a model size.

        Args:
            model_size: Faster-whisper model size (tiny, base, small, medium, large-v3, etc.)
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError(
                "faster-whisper not installed. Install with: pip install faster-whisper"
            )

        self.model = WhisperModel(model_size, device="auto", compute_type="auto")
        self.model_size = model_size

    def transcribe(self, paths: list[str], model: str, max_workers: int = 4) -> tuple[str, dict]:
        """Transcribe using faster-whisper locally.

        Args:
            paths: List of audio file paths to transcribe.
            model: Model identifier (ignored; uses initialized model size).
            max_workers: Maximum number of concurrent transcription workers (default: 4).
        """
        import time

        def transcribe_segment(index: int, path: str) -> tuple[int, str, float]:
            """Transcribe a single segment and return (index, text, latency)."""
            logger.info(f"Transcribing {path} with faster-whisper (model: {self.model_size})")
            start_time = time.time()

            segments, info = self.model.transcribe(path, beam_size=5)
            text = "".join([segment.text for segment in segments])

            latency = time.time() - start_time
            logger.debug(f"Segment transcribed: {len(text)} characters in {latency:.2f}s")
            return index, text, latency

        # Use ThreadPoolExecutor to transcribe segments concurrently
        transcript_dict = {}
        total_latency = 0.0
        max_concurrent_workers = max(1, min(len(paths), max_workers))

        with ThreadPoolExecutor(max_workers=max_concurrent_workers) as executor:
            # Submit all transcription tasks
            futures = {
                executor.submit(transcribe_segment, idx, path): idx
                for idx, path in enumerate(paths)
            }

            # Collect results, preserving order and propagating exceptions
            for future in as_completed(futures):
                try:
                    idx, text, latency = future.result()
                    transcript_dict[idx] = text
                    total_latency += latency
                except Exception as e:
                    # Fail-fast: any segment exception halts the pipeline
                    raise e

        # Reassemble transcript in original segment order
        transcript_parts = [transcript_dict[i] for i in range(len(paths))]
        full_transcript = "\n".join(transcript_parts)
        logger.info(f"Full transcript: {len(full_transcript)} characters")

        metrics = {
            "tokens_in": 0,  # Local model, no token counts
            "tokens_out": 0,
            "latency_seconds": total_latency,
        }

        return full_transcript, metrics


class OllamaLLMBackend(LLMBackend):
    """LLM backend using Ollama API (local)."""

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        """Initialize with Ollama server URL.

        Args:
            ollama_url: Base URL of Ollama server (default: localhost:11434).
        """
        self.ollama_url = ollama_url.rstrip("/")

    def chat_completion(
        self, model: str, messages: list[dict], max_tokens: Optional[int] = None
    ) -> tuple[str, dict]:
        """Make a chat completion using Ollama.

        Args:
            model: Model name in Ollama (e.g., 'neural-chat', 'mistral').
            messages: List of message dicts with 'role' and 'content'.
            max_tokens: Optional max tokens (Ollama uses 'num_predict').

        Returns:
            Tuple of (response_text, metrics_dict).

        Raises:
            RuntimeError: if Ollama is unreachable or returns error.
        """
        import time

        try:
            logger.info(f"Making LLM call to Ollama model: {model}")
            start_time = time.time()

            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
            }

            if max_tokens is not None:
                payload["num_predict"] = max_tokens

            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=300,
            )

            latency = time.time() - start_time

            if response.status_code != 200:
                raise RuntimeError(
                    f"Ollama API error (HTTP {response.status_code}): {response.text}"
                )

            data = response.json()
            content = data.get("message", {}).get("content", "")
            logger.debug(f"Ollama response: {len(content)} characters in {latency:.2f}s")

            metrics = {
                "tokens_in": 0,  # Ollama doesn't expose token counts in standard API
                "tokens_out": 0,
                "latency_seconds": latency,
            }

            return content, metrics

        except requests.ConnectionError as e:
            raise RuntimeError(
                f"Could not connect to Ollama at {self.ollama_url}. "
                "Is Ollama running? Start with: ollama serve"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Ollama LLM call failed: {e}") from e
