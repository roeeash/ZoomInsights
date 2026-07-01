"""Audio preparation (compression, segmentation) for Groq Whisper upload."""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_UPLOAD_MB = 24
SEGMENT_LENGTH_SECONDS = 900


def require_ffmpeg() -> None:
    """Raise an error if ffmpeg is not installed."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found. Install it via: "
            "macOS: brew install ffmpeg, "
            "Linux: apt install ffmpeg, "
            "Windows: https://ffmpeg.org/download.html"
        )


def to_compressed_audio(src: str, dst: str) -> None:
    """Compress audio to 16 kHz mono Opus format."""
    require_ffmpeg()
    logger.info(f"Compressing {src} to {dst}")

    cmd = [
        "ffmpeg",
        "-i", src,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "libopus",
        "-b:a", "16k",
        "-y",
        dst,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(f"Compressed audio saved to {dst}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg compression failed: {e.stderr}")


def maybe_segment(path: str) -> list[str]:
    """Segment audio if larger than the Groq upload cap; else return a single-item list."""
    require_ffmpeg()

    file_size_mb = os.path.getsize(path) / (1024 * 1024)
    logger.debug(f"Audio file size: {file_size_mb:.2f} MB")

    if file_size_mb <= MAX_UPLOAD_MB:
        logger.info(f"Audio under {MAX_UPLOAD_MB} MB; no segmentation needed")
        return [path]

    logger.info(f"Audio over {MAX_UPLOAD_MB} MB; segmenting into {SEGMENT_LENGTH_SECONDS}s chunks")

    # Create output directory for segments
    base_path = Path(path)
    output_dir = base_path.parent / f"{base_path.stem}_segments"
    output_dir.mkdir(exist_ok=True)

    # Segment using ffmpeg
    segment_pattern = str(output_dir / f"{base_path.stem}_%03d.wav")
    cmd = [
        "ffmpeg",
        "-i", path,
        "-f", "segment",
        "-segment_time", str(SEGMENT_LENGTH_SECONDS),
        "-c", "copy",
        "-y",
        segment_pattern,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg segmentation failed: {e.stderr}")

    # Collect segment files in order
    segment_files = sorted(output_dir.glob(f"{base_path.stem}_*.wav"))
    logger.info(f"Created {len(segment_files)} segments")

    return [str(f) for f in segment_files]
