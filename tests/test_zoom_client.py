"""Tests for Zoom API client authentication and recording retrieval."""

import pytest
import base64
import json
import os
import tempfile
from zoom_insights.config import Config
from zoom_insights.zoom_client import (
    get_access_token,
    list_recent_recordings,
    get_meeting_recording,
    pick_file,
    download,
    ensure_work_dir,
    download_path,
    RecordingFile,
    Meeting,
)


@pytest.fixture
def config():
    """Create a test config object."""
    return Config(
        zoom_account_id="test_account_id",
        zoom_client_id="test_client_id",
        zoom_client_secret="test_client_secret",
        groq_api_key="test_groq_key",
    )


@pytest.mark.unit
class TestGetAccessToken:
    """Tests for get_access_token() function."""

    def test_get_access_token_success(self, config, mocker):
        """Test successful token retrieval with correct Basic auth header."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "test_token_12345"}

        mock_post = mocker.patch("zoom_insights.zoom_client.requests.post", return_value=mock_response)
        token = get_access_token(config)

        assert token == "test_token_12345"

        # Verify the request was made correctly
        call_kwargs = mock_post.call_args.kwargs
        call_args = mock_post.call_args.args

        # Check URL
        assert call_args[0] == "https://zoom.us/oauth/token"

        # Check Basic auth header
        expected_creds = "test_client_id:test_client_secret"
        expected_encoded = base64.b64encode(expected_creds.encode()).decode()
        assert call_kwargs["headers"]["Authorization"] == f"Basic {expected_encoded}"

        # Check params
        assert call_kwargs["params"]["grant_type"] == "account_credentials"
        assert call_kwargs["params"]["account_id"] == "test_account_id"

    def test_get_access_token_malformed_response(self, config, mocker):
        """Test that missing access_token key in response raises error."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # Missing access_token key

        mocker.patch("zoom_insights.zoom_client.requests.post", return_value=mock_response)
        with pytest.raises(RuntimeError) as exc_info:
            get_access_token(config)
        assert "access_token" in str(exc_info.value)

    def test_get_access_token_non_200(self, config, mocker):
        """Test that non-200 status codes raise error with Zoom error body."""
        error_body = '{"error": "invalid_client", "error_description": "Client authentication failed"}'
        mock_response = mocker.MagicMock()
        mock_response.status_code = 401
        mock_response.text = error_body

        mocker.patch("zoom_insights.zoom_client.requests.post", return_value=mock_response)
        with pytest.raises(RuntimeError) as exc_info:
            get_access_token(config)
        error_msg = str(exc_info.value)
        assert "401" in error_msg or "Failed to obtain" in error_msg
        assert error_body in error_msg

    def test_get_access_token_forbidden(self, config, mocker):
        """Test that 403 Forbidden includes error details."""
        error_body = '{"error": "access_denied"}'
        mock_response = mocker.MagicMock()
        mock_response.status_code = 403
        mock_response.text = error_body

        mocker.patch("zoom_insights.zoom_client.requests.post", return_value=mock_response)
        with pytest.raises(RuntimeError) as exc_info:
            get_access_token(config)
        assert error_body in str(exc_info.value)

    def test_get_access_token_connection_error(self, config, mocker):
        """Test that ConnectionError is propagated."""
        mocker.patch("zoom_insights.zoom_client.requests.post", side_effect=ConnectionError("Connection refused"))
        with pytest.raises(ConnectionError):
            get_access_token(config)


@pytest.mark.unit
class TestListRecentRecordings:
    """Tests for list_recent_recordings() function."""

    def test_list_recent_recordings_single_page(self, mocker):
        """Test listing recordings on a single page."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "from": "2025-05-01T00:00:00Z",
            "to": "2025-06-28T23:59:59Z",
            "page_size": 30,
            "total_records": 2,
            "meetings": [
                {
                    "uuid": "meeting1",
                    "topic": "Team Standup",
                    "start_time": "2025-06-28T10:00:00Z",
                    "duration": 30,
                    "files": [
                        {
                            "id": "file1",
                            "file_name": "audio.m4a",
                            "file_size": 10485760,
                            "file_type": "M4A",
                            "download_url": "https://zoom.us/download/1",
                            "recording_type": "audio_only",
                        }
                    ],
                }
            ],
        }

        mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
        meetings = list_recent_recordings("fake_token", days_back=60)

        assert len(meetings) == 1
        assert meetings[0].uuid == "meeting1"
        assert meetings[0].topic == "Team Standup"
        assert len(meetings[0].files) == 1

    def test_list_recent_recordings_with_pagination(self, mocker):
        """Test that pagination is handled correctly."""
        # First page response
        page1_response = mocker.MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            "meetings": [
                {
                    "uuid": "meeting1",
                    "topic": "Meeting 1",
                    "start_time": "2025-06-28T10:00:00Z",
                    "duration": 30,
                    "files": [],
                }
            ],
            "next_page_token": "token_page2",
        }

        # Second page response
        page2_response = mocker.MagicMock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            "meetings": [
                {
                    "uuid": "meeting2",
                    "topic": "Meeting 2",
                    "start_time": "2025-06-27T10:00:00Z",
                    "duration": 60,
                    "files": [],
                }
            ],
        }

        mocker.patch("zoom_insights.zoom_client.requests.get", side_effect=[page1_response, page2_response])
        meetings = list_recent_recordings("fake_token")

        assert len(meetings) == 2
        assert meetings[0].uuid == "meeting1"
        assert meetings[1].uuid == "meeting2"

    def test_list_recent_recordings_empty(self, mocker):
        """Test handling of empty recordings list."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"meetings": []}

        mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
        meetings = list_recent_recordings("fake_token")

        assert len(meetings) == 0

    def test_list_recent_recordings_api_error(self, mocker):
        """Test error handling on failed API call."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 401
        mock_response.text = '{"error": "invalid_token"}'

        mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
        with pytest.raises(RuntimeError) as exc_info:
            list_recent_recordings("bad_token")
        assert "Failed to list recordings" in str(exc_info.value)

    def test_list_recent_recordings_uses_correct_url_and_headers(self, mocker):
        """Test that the correct URL and auth header are used."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"meetings": []}

        mock_get = mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
        list_recent_recordings("test_token", days_back=30)

        call_args = mock_get.call_args
        assert call_args.args[0] == "https://zoom.us/v2/users/me/recordings"
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer test_token"


@pytest.mark.unit
class TestGetMeetingRecording:
    """Tests for get_meeting_recording() function."""

    def test_get_meeting_recording_normal_uuid(self, mocker):
        """Test fetching a meeting with a normal UUID."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "uuid": "normal_uuid",
            "topic": "Project Review",
            "start_time": "2025-06-28T14:00:00Z",
            "duration": 120,
            "files": [],
        }

        mock_get = mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
        meeting = get_meeting_recording("token", "normal_uuid")

        assert meeting.uuid == "normal_uuid"
        assert meeting.topic == "Project Review"
        # Verify URL encoding was applied
        call_args = mock_get.call_args
        assert "normal_uuid" in call_args.args[0]

    def test_get_meeting_recording_uuid_starts_with_slash(self, mocker):
        """Test double-encoding for UUID starting with /."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "uuid": "/test_uuid",
            "topic": "Meeting with slash",
            "start_time": "2025-06-28T14:00:00Z",
            "duration": 60,
            "files": [],
        }

        mock_get = mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
        meeting = get_meeting_recording("token", "/test_uuid")

        assert meeting.uuid == "/test_uuid"
        # Verify double encoding was applied
        call_url = mock_get.call_args.args[0]
        # %252F is the double-encoded /
        assert "%252F" in call_url

    def test_get_meeting_recording_uuid_contains_double_slash(self, mocker):
        """Test double-encoding for UUID containing //."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "uuid": "test//uuid",
            "topic": "Meeting with double slash",
            "start_time": "2025-06-28T14:00:00Z",
            "duration": 90,
            "files": [],
        }

        mock_get = mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
        meeting = get_meeting_recording("token", "test//uuid")

        assert meeting.uuid == "test//uuid"
        # Verify double encoding was applied
        call_url = mock_get.call_args.args[0]
        # %252F is double-encoded /
        assert "%252F" in call_url

    def test_get_meeting_recording_api_error(self, mocker):
        """Test error handling on failed API call."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 404
        mock_response.text = '{"error": "meeting not found"}'

        mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
        with pytest.raises(RuntimeError) as exc_info:
            get_meeting_recording("token", "bad_uuid")
        assert "Failed to get meeting recording" in str(exc_info.value)

    def test_get_meeting_recording_uses_bearer_token(self, mocker):
        """Test that Bearer token is used in Authorization header."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "uuid": "uuid123",
            "topic": "Test",
            "start_time": "2025-06-28T14:00:00Z",
            "duration": 60,
            "files": [],
        }

        mock_get = mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
        get_meeting_recording("my_token", "uuid123")

        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer my_token"


@pytest.mark.unit
class TestPickFile:
    """Tests for pick_file() preference helper function."""

    def test_pick_file_with_preferred_type(self):
        """Test picking a file with specified preference."""
        files = [
            RecordingFile("id1", "video.mp4", 1000, "MP4", "url1", "speaker_view"),
            RecordingFile("id2", "audio.m4a", 500, "M4A", "url2", "audio_only"),
        ]

        # Prefer M4A
        result = pick_file(files, "M4A")
        assert result is not None
        assert result.file_type == "M4A"

    def test_pick_file_fallback_to_second_preference(self):
        """Test fallback to second preference when first not found."""
        files = [
            RecordingFile("id1", "video.mp4", 1000, "MP4", "url1", "speaker_view"),
            RecordingFile("id2", "audio.m4a", 500, "M4A", "url2", "audio_only"),
        ]

        # Prefer M4A first, then MP4
        result = pick_file(files, "M4A", "MP4")
        assert result is not None
        assert result.file_type == "M4A"

        # Prefer CHAT first (not present), then MP4
        result = pick_file(files, "CHAT", "MP4")
        assert result is not None
        assert result.file_type == "MP4"

    def test_pick_file_no_match_returns_none(self):
        """Test that None is returned when no preference matches."""
        files = [
            RecordingFile("id1", "video.mp4", 1000, "MP4", "url1", "speaker_view"),
        ]

        result = pick_file(files, "M4A", "TRANSCRIPT")
        assert result is None

    def test_pick_file_empty_list(self):
        """Test behavior with empty file list."""
        result = pick_file([], "M4A")
        assert result is None

    def test_pick_file_no_preferences_returns_first(self):
        """Test that first file is returned when no preferences given."""
        files = [
            RecordingFile("id1", "video.mp4", 1000, "MP4", "url1", "speaker_view"),
            RecordingFile("id2", "audio.m4a", 500, "M4A", "url2", "audio_only"),
        ]

        result = pick_file(files)
        assert result is not None
        assert result.id == "id1"


@pytest.mark.unit
class TestDataclasses:
    """Tests for RecordingFile and Meeting dataclasses."""

    def test_recording_file_creation(self):
        """Test creating a RecordingFile instance."""
        file = RecordingFile(
            id="file1",
            file_name="audio.m4a",
            file_size=1024,
            file_type="M4A",
            download_url="https://zoom.us/download",
            recording_type="audio_only",
        )

        assert file.id == "file1"
        assert file.file_name == "audio.m4a"
        assert file.file_size == 1024
        assert file.file_type == "M4A"

    def test_meeting_creation(self):
        """Test creating a Meeting instance."""
        files = [
            RecordingFile("id1", "audio.m4a", 1024, "M4A", "url1", "audio_only")
        ]
        meeting = Meeting(
            uuid="meeting1",
            topic="Team Meeting",
            start_time="2025-06-28T10:00:00Z",
            duration=60,
            files=files,
        )

        assert meeting.uuid == "meeting1"
        assert meeting.topic == "Team Meeting"
        assert meeting.duration == 60
        assert len(meeting.files) == 1


@pytest.mark.unit
class TestDownload:
    """Tests for download() function."""

    def test_download_success(self, mocker):
        """Test successful file download to disk."""
        file = RecordingFile(
            id="file1",
            file_name="audio.m4a",
            file_size=5242880,  # 5 MB
            file_type="M4A",
            download_url="https://zoom.us/download/file1",
            recording_type="audio_only",
        )

        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content = mocker.MagicMock(return_value=[b"test_data"])

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "audio.m4a")

            mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
            download(file, "test_token", out_path)

            assert os.path.exists(out_path)
            with open(out_path, "rb") as f:
                content = f.read()
            assert content == b"test_data"

    def test_download_creates_file(self, mocker):
        """Test that download creates the output file."""
        file = RecordingFile(
            id="file1",
            file_name="video.mp4",
            file_size=10485760,
            file_type="MP4",
            download_url="https://zoom.us/download/file1",
            recording_type="speaker_view",
        )

        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content = mocker.MagicMock(return_value=[b"chunk1", b"chunk2"])

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "video.mp4")

            mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
            download(file, "test_token", out_path)

            assert os.path.exists(out_path)
            assert os.path.getsize(out_path) == 12  # len("chunk1") + len("chunk2")

    def test_download_chunks_large_file(self, mocker):
        """Test that download handles multiple 1 MB chunks correctly."""
        file = RecordingFile(
            id="file1",
            file_name="large_audio.m4a",
            file_size=52428800,  # 50 MB
            file_type="M4A",
            download_url="https://zoom.us/download/file1",
            recording_type="audio_only",
        )

        # Simulate 5 chunks of 1 MB each
        chunk_size = 1024 * 1024
        chunks = [b"x" * chunk_size for _ in range(5)]

        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content = mocker.MagicMock(return_value=chunks)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "large_audio.m4a")

            mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
            download(file, "test_token", out_path)

            assert os.path.exists(out_path)
            expected_size = chunk_size * 5
            assert os.path.getsize(out_path) == expected_size

    def test_download_403_forbidden(self, mocker):
        """Test that 403 Forbidden error is handled with actionable message."""
        file = RecordingFile(
            id="file1",
            file_name="audio.m4a",
            file_size=1024,
            file_type="M4A",
            download_url="https://zoom.us/download/file1",
            recording_type="audio_only",
        )

        mock_response = mocker.MagicMock()
        mock_response.status_code = 403
        mock_response.text = '{"error": "access_denied"}'

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "audio.m4a")

            mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
            with pytest.raises(RuntimeError) as exc_info:
                download(file, "test_token", out_path)

            error_msg = str(exc_info.value)
            assert "403" in error_msg
            assert "owner" in error_msg.lower() or "scope" in error_msg.lower()

    def test_download_401_unauthorized(self, mocker):
        """Test that 401 Unauthorized error is handled with actionable message."""
        file = RecordingFile(
            id="file1",
            file_name="audio.m4a",
            file_size=1024,
            file_type="M4A",
            download_url="https://zoom.us/download/file1",
            recording_type="audio_only",
        )

        mock_response = mocker.MagicMock()
        mock_response.status_code = 401
        mock_response.text = '{"error": "invalid_token"}'

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "audio.m4a")

            mocker.patch("zoom_insights.zoom_client.requests.get", return_value=mock_response)
            with pytest.raises(RuntimeError) as exc_info:
                download(file, "test_token", out_path)

            error_msg = str(exc_info.value)
            assert "401" in error_msg
            assert "expired" in error_msg.lower() or "invalid" in error_msg.lower()

    def test_download_connection_error(self, mocker):
        """Test that connection errors are propagated as ConnectionError."""
        file = RecordingFile(
            id="file1",
            file_name="audio.m4a",
            file_size=1024,
            file_type="M4A",
            download_url="https://zoom.us/download/file1",
            recording_type="audio_only",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "audio.m4a")

            mocker.patch(
                "zoom_insights.zoom_client.requests.get",
                side_effect=ConnectionError("Connection refused"),
            )
            with pytest.raises(ConnectionError):
                download(file, "test_token", out_path)


@pytest.mark.unit
class TestEnsureWorkDir:
    """Tests for ensure_work_dir() function."""

    def test_ensure_work_dir_creates_directory(self):
        """Test that ensure_work_dir creates missing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_path = os.path.join(tmpdir, "work")
            assert not os.path.exists(work_path)

            result = ensure_work_dir(work_path)

            assert os.path.exists(work_path)
            assert os.path.isdir(work_path)
            assert os.path.abspath(work_path) == result

    def test_ensure_work_dir_idempotent(self):
        """Test that ensure_work_dir is idempotent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_path = os.path.join(tmpdir, "work")

            # Call twice
            result1 = ensure_work_dir(work_path)
            result2 = ensure_work_dir(work_path)

            # Both should return same path and directory should still exist
            assert result1 == result2
            assert os.path.exists(work_path)
            assert os.path.isdir(work_path)


@pytest.mark.unit
class TestDownloadPath:
    """Tests for download_path() function."""

    def test_download_path_deterministic(self):
        """Test that download_path returns deterministic path."""
        file = RecordingFile(
            id="file1",
            file_name="audio.m4a",
            file_size=1024,
            file_type="M4A",
            download_url="https://zoom.us/download/file1",
            recording_type="audio_only",
        )

        path1 = download_path(file, "work")
        path2 = download_path(file, "work")

        assert path1 == path2

    def test_download_path_uses_filename(self):
        """Test that download_path includes the filename."""
        file = RecordingFile(
            id="file1",
            file_name="my_recording.m4a",
            file_size=1024,
            file_type="M4A",
            download_url="https://zoom.us/download/file1",
            recording_type="audio_only",
        )

        path = download_path(file, "work")

        assert "my_recording.m4a" in path

    def test_download_path_includes_base_dir(self):
        """Test that download_path includes the base directory."""
        file = RecordingFile(
            id="file1",
            file_name="audio.m4a",
            file_size=1024,
            file_type="M4A",
            download_url="https://zoom.us/download/file1",
            recording_type="audio_only",
        )

        base_dir = "custom_base"
        path = download_path(file, base_dir)

        assert path.startswith(base_dir)
