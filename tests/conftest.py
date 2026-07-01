"""Pytest configuration and shared fixtures."""

import sys
import os
import struct
import wave
import json
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

# Load .env file before checking environment variables
load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zoom_insights.config import Config


class MockerWrapper:
    """Minimal mocker wrapper using unittest.mock for pytest-mock compatibility."""

    def MagicMock(self, *args, **kwargs):
        """Create a MagicMock."""
        from unittest.mock import MagicMock
        return MagicMock(*args, **kwargs)

    def patch(self, target, *args, **kwargs):
        """Patch a target and return the mock."""
        patcher = patch(target, *args, **kwargs)
        return patcher.start()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        patch.stopall()


@pytest.fixture
def mocker():
    """Provide a mocker fixture that wraps unittest.mock."""
    m = MockerWrapper()
    yield m
    patch.stopall()


@pytest.fixture(scope="session")
def zoom_credentials():
    """
    Session-scoped fixture: returns dict with Zoom API credentials from env.
    Skips test session if any credential is missing.
    """
    zoom_account_id = os.getenv("ZOOM_ACCOUNT_ID")
    zoom_client_id = os.getenv("ZOOM_CLIENT_ID")
    zoom_client_secret = os.getenv("ZOOM_CLIENT_SECRET")

    if not (zoom_account_id and zoom_client_id and zoom_client_secret):
        pytest.skip("Zoom credentials not set in environment")

    return {
        "ZOOM_ACCOUNT_ID": zoom_account_id,
        "ZOOM_CLIENT_ID": zoom_client_id,
        "ZOOM_CLIENT_SECRET": zoom_client_secret,
    }


@pytest.fixture(scope="session")
def jira_credentials():
    """
    Session-scoped fixture: returns dict with Jira API credentials from env.
    Skips test session if any credential is missing.
    """
    jira_url = os.getenv("JIRA_URL")
    jira_email = os.getenv("JIRA_EMAIL")
    jira_api_token = os.getenv("JIRA_API_TOKEN")
    jira_project_key = os.getenv("JIRA_PROJECT_KEY")

    if not (jira_url and jira_email and jira_api_token and jira_project_key):
        pytest.skip("Jira credentials not set in environment")

    return {
        "url": jira_url,
        "email": jira_email,
        "api_token": jira_api_token,
        "project_key": jira_project_key,
    }


@pytest.fixture(scope="session")
def groq_api_key():
    """
    Session-scoped fixture: returns GROQ_API_KEY from env.
    Skips test session if not set.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        pytest.skip("GROQ_API_KEY not set in environment")
    return api_key


@pytest.fixture(scope="function")
def sample_insights():
    """
    Function-scoped fixture: returns dict with all 6 insights keys,
    each with non-empty values.
    """
    return {
        "summary": "Meeting discussed quarterly roadmap and budget allocation.",
        "key_points": [
            "Q4 objectives defined",
            "Budget approved for initiatives",
        ],
        "decisions": [
            "Proceed with cloud migration",
            "Allocate $500K for new team",
        ],
        "action_items": [
            {"owner": "Alice", "task": "Draft migration plan", "due": "2025-07-15"},
            {"owner": "Bob", "task": "Prepare budget doc", "due": "2025-07-20"},
        ],
        "open_questions": [
            "What is the timeline for full migration?",
            "How will we manage vendor selection?",
        ],
        "notable_quotes": [
            "We need to move fast without sacrificing quality.",
            "This quarter is critical for our growth.",
        ],
    }


@pytest.fixture(scope="function")
def sample_transcript():
    """
    Function-scoped fixture: returns a multi-line meeting transcript string.
    """
    return (
        "Alice: Hello everyone, thanks for joining today.\n"
        "Bob: Hi Alice, good to see you.\n"
        "Alice: We need to discuss the Q4 roadmap.\n"
        "Bob: Yes, I have a few thoughts on that.\n"
        "Alice: Let's start with the timeline.\n"
    )


@pytest.fixture(scope="function")
def tmp_output_dir(tmp_path):
    """
    Function-scoped fixture: creates and returns an output directory path.
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    return str(output_dir)


@pytest.fixture(scope="function")
def synthetic_wav(tmp_path):
    """
    Function-scoped fixture: creates a 5-second 16kHz mono WAV file
    programmatically using stdlib wave and struct modules.
    Returns path as string.
    """
    wav_path = tmp_path / "test_audio.wav"

    # 5 seconds at 16kHz = 80000 samples
    sample_rate = 16000
    duration = 5
    num_samples = sample_rate * duration

    # Open WAV file for writing
    with wave.open(str(wav_path), "w") as wav_file:
        wav_file.setnchannels(1)  # mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)

        # Write simple silence (zeros) for 5 seconds
        frames = struct.pack(f"<{num_samples}h", *([0] * num_samples))
        wav_file.writeframes(frames)

    return str(wav_path)


@pytest.fixture(scope="function")
def mock_config():
    """
    Function-scoped fixture: returns a Config object with test values.
    """
    return Config(
        zoom_account_id="test",
        zoom_client_id="test",
        zoom_client_secret="test",
        groq_api_key="test",
        jira_url="https://test.atlassian.net",
        jira_email="test@test.com",
        jira_api_token="test",
        jira_project_key="TEST",
    )


@pytest.fixture(scope="function")
def mock_groq_client(mocker, sample_insights):
    """
    Function-scoped fixture: returns a mocked Groq client with pre-wired
    valid transcription and map+reduce responses.
    """
    client = mocker.MagicMock()

    # Mock transcription response
    client.audio.transcriptions.create.return_value = "Sample transcript"

    # Mock map phase response
    map_response = mocker.MagicMock()
    map_response.choices = [
        mocker.MagicMock(
            message=mocker.MagicMock(content="- Key point from chunk")
        )
    ]

    # Mock reduce phase response
    reduce_response = mocker.MagicMock()
    reduce_response.choices = [
        mocker.MagicMock(
            message=mocker.MagicMock(content=json.dumps(sample_insights))
        )
    ]

    # Wire up chat completions to return map then reduce responses
    client.chat.completions.create.side_effect = [map_response, reduce_response]

    return client
