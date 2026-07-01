"""Zoom Cloud Recording API client for authentication and file retrieval."""

import base64
import logging
import os
import urllib.parse
from dataclasses import dataclass
from typing import Optional
import requests
from zoom_insights.config import Config

logger = logging.getLogger(__name__)


@dataclass
class RecordingFile:
    """Represents a single file in a Zoom recording."""

    id: str
    file_name: str
    file_size: int
    file_type: str
    download_url: str
    recording_type: str


@dataclass
class Meeting:
    """Represents a Zoom meeting with its recordings."""

    uuid: str
    topic: str
    start_time: str
    duration: int
    files: list[RecordingFile]


def get_access_token(config: Config) -> str:
    """Obtain a Zoom access token from Server-to-Server OAuth credentials."""
    logger.info("Obtaining Zoom access token")

    credentials = f"{config.zoom_client_id}:{config.zoom_client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()

    headers = {"Authorization": f"Basic {encoded}"}
    params = {
        "grant_type": "account_credentials",
        "account_id": config.zoom_account_id,
    }

    response = requests.post(
        "https://zoom.us/oauth/token",
        headers=headers,
        params=params,
    )

    logger.debug(f"HTTP status code: {response.status_code}")

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to obtain Zoom access token: {response.text}"
        )

    data = response.json()
    if "access_token" not in data:
        raise RuntimeError("Zoom response missing 'access_token' key")

    return data["access_token"]


def list_recent_recordings(token: str, days_back: int = 60) -> list[Meeting]:
    """List recent cloud recordings from the authenticated user."""
    logger.info(f"Fetching recordings from last {days_back} days")

    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "from": _format_date_ago(days_back),
        "to": _format_date_now(),
        "page_size": 30,
    }

    all_meetings = []

    while True:
        response = requests.get(
            "https://zoom.us/v2/users/me/recordings",
            headers=headers,
            params=params,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to list recordings: {response.text}"
            )

        data = response.json()
        meetings_data = data.get("meetings", [])

        for meeting_data in meetings_data:
            meeting = _parse_meeting(meeting_data)
            all_meetings.append(meeting)

        next_token = data.get("next_page_token")
        if not next_token:
            break

        params["next_page_token"] = next_token
        del params["from"]
        del params["to"]

    logger.info(f"Retrieved {len(all_meetings)} meetings")
    return all_meetings


def get_meeting_recording(token: str, meeting_uuid: str) -> Meeting:
    """Retrieve a specific meeting recording by UUID, handling double-encoding."""
    logger.info(f"Fetching recording for meeting {meeting_uuid}")

    encoded_uuid = _encode_uuid(meeting_uuid)
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(
        f"https://zoom.us/v2/users/me/recordings/{encoded_uuid}",
        headers=headers,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to get meeting recording: {response.text}"
        )

    data = response.json()
    meeting = _parse_meeting(data)
    return meeting


def pick_file(files: list[RecordingFile], *types: str) -> Optional[RecordingFile]:
    """Pick a file from a list by preferred type; return None if no match."""
    if not types:
        return files[0] if files else None

    for file_type in types:
        for file in files:
            if file.file_type == file_type:
                return file

    return None


def _format_date_ago(days: int) -> str:
    """Format a date string for N days ago in ISO 8601."""
    from datetime import datetime, timedelta
    dt = datetime.utcnow() - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_date_now() -> str:
    """Format today's date in ISO 8601."""
    from datetime import datetime
    dt = datetime.utcnow()
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _encode_uuid(uuid: str) -> str:
    """Handle UUID double-encoding per Zoom rules."""
    if uuid.startswith("/") or "//" in uuid:
        return urllib.parse.quote(urllib.parse.quote(uuid, safe=""), safe="")
    return urllib.parse.quote(uuid, safe="")


def _parse_meeting(data: dict) -> Meeting:
    """Parse a meeting dict from Zoom API into a Meeting dataclass."""
    files = []
    for file_data in data.get("files", []):
        file = RecordingFile(
            id=file_data.get("id", ""),
            file_name=file_data.get("file_name", ""),
            file_size=file_data.get("file_size", 0),
            file_type=file_data.get("file_type", ""),
            download_url=file_data.get("download_url", ""),
            recording_type=file_data.get("recording_type", ""),
        )
        files.append(file)

    return Meeting(
        uuid=data.get("uuid", ""),
        topic=data.get("topic", ""),
        start_time=data.get("start_time", ""),
        duration=data.get("duration", 0),
        files=files,
    )


def download(file: RecordingFile, token: str, out_path: str) -> None:
    """Download a recording file to disk, streaming in 1 MB chunks.

    Args:
        file: RecordingFile object containing download_url and metadata.
        token: Zoom OAuth access token.
        out_path: Destination file path.

    Raises:
        RuntimeError: On 403 (Forbidden), 401 (Unauthorized), or other HTTP errors.
        ConnectionError: On network issues.
    """
    logger.info(f"Downloading file {file.file_name} to {out_path}")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(
            file.download_url,
            headers=headers,
            stream=True,
            timeout=30,
        )
    except (requests.Timeout, requests.ConnectionError) as e:
        raise ConnectionError(f"Failed to connect to download URL: {str(e)}")

    if response.status_code == 403:
        raise RuntimeError(
            f"Access Forbidden (403): Your account may not own this recording, "
            f"or the token lacks recording scope. Check that you are the recording owner and "
            f"your OAuth app has 'cloud_recording:read' scopes."
        )
    elif response.status_code == 401:
        raise RuntimeError(
            f"Unauthorized (401): Your access token has expired or is invalid. "
            f"Please obtain a fresh token and try again."
        )
    elif response.status_code != 200:
        raise RuntimeError(
            f"Failed to download file: HTTP {response.status_code} {response.text}"
        )

    # Write file in 1 MB chunks
    chunk_size = 1024 * 1024  # 1 MB
    bytes_written = 0

    try:
        with open(out_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    bytes_written += len(chunk)

        logger.info(f"Downloaded {bytes_written} bytes to {out_path}")
    except IOError as e:
        raise RuntimeError(f"Failed to write to {out_path}: {str(e)}")


def ensure_work_dir(base_path: str = "work") -> str:
    """Ensure work directory exists; create if missing.

    Args:
        base_path: Base path for work directory (default: "work").

    Returns:
        The absolute path to the work directory.
    """
    os.makedirs(base_path, exist_ok=True)
    logger.debug(f"Work directory ensured: {base_path}")
    return os.path.abspath(base_path)


def download_path(file: RecordingFile, base_dir: str = "work") -> str:
    """Compute a deterministic download path for a recording file.

    The path is: base_dir/{file.file_name}

    Args:
        file: RecordingFile object.
        base_dir: Base directory for downloads (default: "work").

    Returns:
        Full path to where the file should be saved.
    """
    return os.path.join(base_dir, file.file_name)
