"""Speaker diarization infrastructure using pyannote.audio or stub."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DiarizationResult:
    """Result of speaker diarization for a segment of audio.

    Attributes:
        speaker_id: Integer identifier for the speaker (e.g., 0, 1, 2)
        start_ms: Start time in milliseconds
        end_ms: End time in milliseconds
    """
    speaker_id: int
    start_ms: int
    end_ms: int


class DiarizeAudioBackend(ABC):
    """Abstract base class for audio diarization backends."""

    @abstractmethod
    def diarize(self, audio_path: str) -> list[DiarizationResult]:
        """Diarize an audio file to identify speakers.

        Args:
            audio_path: Path to the audio file

        Returns:
            List of DiarizationResult objects with speaker segments
        """
        pass


class PyannoteBackend(DiarizeAudioBackend):
    """Speaker diarization using pyannote.audio (requires HUGGINGFACE_TOKEN)."""

    def __init__(self, huggingface_token: str):
        """Initialize the pyannote backend.

        Args:
            huggingface_token: HuggingFace API token for accessing pyannote models

        Raises:
            ValueError: if huggingface_token is empty
        """
        if not huggingface_token:
            raise ValueError(
                "HUGGINGFACE_TOKEN is required for pyannote diarization. "
                "Get a token from https://huggingface.co/settings/tokens"
            )
        self.huggingface_token = huggingface_token
        self._pipeline = None

    def _get_pipeline(self):
        """Lazily load the pyannote.audio pipeline."""
        if self._pipeline is None:
            try:
                from pyannote.audio import Pipeline
            except ImportError:
                raise ImportError(
                    "pyannote.audio is not installed. Install with: pip install pyannote.audio"
                )

            logger.info("Loading pyannote.audio pipeline")
            try:
                self._pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=self.huggingface_token
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load pyannote pipeline: {e}. "
                    f"Check that HUGGINGFACE_TOKEN is valid."
                )

        return self._pipeline

    def diarize(self, audio_path: str) -> list[DiarizationResult]:
        """Diarize an audio file using pyannote.audio.

        Args:
            audio_path: Path to the audio file

        Returns:
            List of DiarizationResult objects with speaker segments
        """
        logger.info(f"Diarizing audio with pyannote: {audio_path}")

        pipeline = self._get_pipeline()

        try:
            diarization = pipeline(audio_path)
        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            raise RuntimeError(f"Diarization failed: {e}")

        results = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            # Extract speaker ID from label (format: "Speaker 0", "Speaker 1", etc.)
            speaker_id = int(speaker.split()[-1]) if speaker else 0

            # Convert seconds to milliseconds
            start_ms = int(turn.start * 1000)
            end_ms = int(turn.end * 1000)

            results.append(DiarizationResult(
                speaker_id=speaker_id,
                start_ms=start_ms,
                end_ms=end_ms
            ))

        logger.info(f"Diarization complete: {len(results)} segments, {len(set(r.speaker_id for r in results))} speakers")
        return results


class LocalDiarizationBackend(DiarizeAudioBackend):
    """Stub diarization backend that returns empty list (no diarization)."""

    def diarize(self, audio_path: str) -> list[DiarizationResult]:
        """Return empty list (diarization disabled).

        Args:
            audio_path: Path to the audio file (unused)

        Returns:
            Empty list
        """
        logger.debug("Diarization disabled (using LocalDiarizationBackend stub)")
        return []
