"""Merge diarization results with transcripts to label speakers."""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    """A segment of transcript with speaker information.

    Attributes:
        timestamp_ms: Time offset in milliseconds
        text: The spoken text
        speaker_id: Speaker identifier (0-based) or None if unknown
    """
    timestamp_ms: int
    text: str
    speaker_id: Optional[int] = None


def merge_diarization_with_transcript(
    transcript: str,
    diarization_segments: list,
    audio_path: str = ""
) -> str:
    """Merge diarization speaker labels with transcript.

    This is a simplified implementation that prepends speaker labels
    to transcript sections. A full implementation would align word-level
    timestamps from Whisper with diarization segments.

    Args:
        transcript: Full transcript text
        diarization_segments: List of DiarizationResult from diarizer
        audio_path: Path to audio (for logging; unused in basic impl)

    Returns:
        Transcript with speaker labels prepended (e.g., "[Speaker 0] Hello...")
    """
    if not diarization_segments:
        logger.debug("No diarization segments; returning transcript unchanged")
        return transcript

    logger.info(f"Merging {len(diarization_segments)} diarization segments with transcript")

    # Basic implementation: split transcript into sentences and label by time
    # In a production system, this would use Whisper's word-level timestamps
    # to precisely align each word with a speaker.

    sentences = transcript.split(". ")
    if not sentences:
        return transcript

    # Group diarization segments by speaker for simple labeling
    speakers_by_time = {}
    for seg in diarization_segments:
        # Map time range to speaker
        for ms in range(seg.start_ms, seg.end_ms, 100):  # 100ms granularity
            speakers_by_time[ms] = seg.speaker_id

    # Reconstruct transcript with speaker labels
    labeled_parts = []
    current_speaker = None
    time_offset = 0

    for sentence in sentences:
        if not sentence.strip():
            continue

        # Estimate time for this sentence (very rough: ~150 chars per 5 seconds)
        estimated_duration_ms = int((len(sentence) / 150) * 5000)

        # Find the dominant speaker during this sentence
        speaker = speakers_by_time.get(time_offset)
        if speaker is None and speakers_by_time:
            # Find nearest speaker
            nearest = min(speakers_by_time.keys(), key=lambda t: abs(t - time_offset))
            speaker = speakers_by_time[nearest]

        # Prepend speaker label if it changed
        if speaker != current_speaker and speaker is not None:
            labeled_parts.append(f"\n[Speaker {speaker}] ")
            current_speaker = speaker

        labeled_parts.append(sentence + ". ")
        time_offset += estimated_duration_ms

    result = "".join(labeled_parts).strip()
    logger.info(f"Transcript merged with diarization: {len(result)} characters, {len(set(seg.speaker_id for seg in diarization_segments))} speakers")
    return result
