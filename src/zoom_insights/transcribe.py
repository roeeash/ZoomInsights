"""Transcription using Groq Whisper API."""

import logging
import requests
from pathlib import Path
from typing import Any, Optional
from zoom_insights.retry import with_retry

logger = logging.getLogger(__name__)


def transcribe(
    paths: list[str],
    client: Any,
    use_vtt: bool = False,
    meeting_uuid: str = "",
    files: Optional[list] = None,
    token: str = "",
    model: str = "whisper-large-v3-turbo",
) -> str:
    """Transcribe one or more audio segments using Groq Whisper and concatenate.

    Args:
        paths: List of audio file paths to transcribe.
        client: Groq API client.
        use_vtt: If True, attempt to use Zoom VTT transcript instead of Whisper.
        meeting_uuid: UUID of the meeting (needed for VTT download).
        files: List of RecordingFile objects (needed for VTT download).
        token: Zoom OAuth access token (needed for VTT download).
        model: Whisper model name to use.

    Returns:
        Full transcript as a string.
    """
    if use_vtt and files and token:
        logger.info("Attempting to use Zoom VTT transcript")
        vtt_text = download_and_parse_vtt(meeting_uuid, files, token)
        if vtt_text:
            logger.info("Successfully used Zoom VTT transcript")
            return vtt_text
        logger.info("VTT transcript not available; falling back to Whisper")

    transcript_parts = []

    for path in paths:
        logger.info(f"Transcribing {path}")

        with open(path, "rb") as audio_file:
            response = with_retry(
                client.audio.transcriptions.create,
                file=(Path(path).name, audio_file),
                model=model,
                response_format="text",
            )

        # Handle both string and object responses
        if isinstance(response, str):
            text = response
        else:
            # Handle object response with .text attribute
            text = getattr(response, "text", str(response))

        transcript_parts.append(text)
        logger.debug(f"Segment transcribed: {len(text)} characters")

    full_transcript = "\n".join(transcript_parts)
    logger.info(f"Full transcript: {len(full_transcript)} characters")

    return full_transcript


def parse_vtt(vtt_content: str) -> str:
    """Parse VTT content and extract plain text without timestamps or cue numbers."""
    lines = vtt_content.split("\n")
    text_lines = []

    for line in lines:
        line = line.strip()
        # Skip empty lines, WEBVTT header, timestamps, cue numbers, and NOTE lines
        if (
            line
            and not line.startswith("WEBVTT")
            and not line.startswith("NOTE")
            and "-->" not in line
            and not line.isdigit()
        ):
            text_lines.append(line)

    return " ".join(text_lines)


def download_and_parse_vtt(meeting_uuid: str, files: list, token: str) -> str:
    """Download and parse Zoom VTT transcript for a meeting.

    Args:
        meeting_uuid: UUID of the meeting.
        files: List of RecordingFile objects from zoom_client.
        token: Zoom OAuth access token.

    Returns:
        Parsed transcript text, or empty string if VTT not available.
    """
    # Find TRANSCRIPT file in the recording files
    transcript_file = None
    for file in files:
        if file.recording_type == "TRANSCRIPT":
            transcript_file = file
            break

    if not transcript_file:
        logger.debug("No TRANSCRIPT file found in meeting recording")
        return ""

    logger.info(f"Downloading VTT transcript from {transcript_file.file_name}")

    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            transcript_file.download_url,
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            logger.warning(f"Failed to download VTT: HTTP {response.status_code}")
            return ""

        vtt_content = response.text
        parsed_text = parse_vtt(vtt_content)
        logger.info(f"VTT transcript parsed: {len(parsed_text)} characters")

        return parsed_text

    except Exception as e:
        logger.warning(f"Error downloading VTT transcript: {e}")
        return ""
