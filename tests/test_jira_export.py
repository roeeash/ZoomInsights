"""Tests for Jira Cloud export functionality."""

import json
import base64
import pytest
from zoom_insights.jira_export import build_ticket_payload, create_jira_tickets


@pytest.mark.unit
class TestBuildTicketPayload:
    """Tests for build_ticket_payload() function."""

    def test_task_goes_into_title_not_description(self):
        """Test that action item task becomes ticket summary, not in description text."""
        action_item = {
            "task": "Review budget proposal",
            "owner": "Alice",
            "due": "2024-12-20"
        }
        key_points = ["Budget approved at $2M", "Timeline: Oct-Dec"]

        payload = build_ticket_payload(action_item, key_points, "PROJ")

        # Task should be in summary
        assert payload["fields"]["summary"] == "Review budget proposal"

        # Task should appear in description text content
        description = payload["fields"]["description"]
        assert description["type"] == "doc"
        assert description["version"] == 1
        # Extract all text from all paragraphs
        description_text = " ".join([
            para["content"][0]["text"] for para in description["content"]
        ])
        # Task appears as "Task: Review budget proposal" in context
        assert "Task:" in description_text
        assert "Review budget proposal" in description_text

    def test_key_points_go_into_description_not_title(self):
        """Test that key_points appear in description, not in summary."""
        action_item = {
            "task": "Send report",
            "owner": "Bob",
            "due": None
        }
        key_points = ["Q4 strategy finalized", "Budget allocated"]

        payload = build_ticket_payload(action_item, key_points, "PROJ")

        # Key points should be in description
        description = payload["fields"]["description"]
        # Extract all text from all paragraphs
        description_text = " ".join([
            para["content"][0]["text"] for para in description["content"]
        ])
        assert "Q4 strategy finalized" in description_text
        assert "Budget allocated" in description_text

        # Key points should NOT be in summary
        assert payload["fields"]["summary"] == "Send report"
        assert "Q4 strategy" not in payload["fields"]["summary"]
        assert "Budget allocated" not in payload["fields"]["summary"]

    def test_build_ticket_payload_no_owner_shows_unassigned(self):
        """Test that None owner renders 'Unassigned' in description, not in summary."""
        action_item = {
            "task": "Update documentation",
            "owner": None,
            "due": "2024-12-25"
        }
        key_points = ["All docs approved"]

        payload = build_ticket_payload(action_item, key_points, "PROJ")

        # Description should contain "Unassigned"
        description = payload["fields"]["description"]
        # Extract all text from all paragraphs
        description_text = " ".join([
            para["content"][0]["text"] for para in description["content"]
        ])
        assert "Owner: Unassigned" in description_text

        # Summary should only be the task
        assert payload["fields"]["summary"] == "Update documentation"
        assert "Unassigned" not in payload["fields"]["summary"]

    @pytest.mark.parametrize("bad_task", ["", None, "   "], ids=["empty_string", "none_value", "whitespace_only"])
    def test_build_ticket_payload_validates_bad_task(self, bad_task):
        """Test that bad task values raise ValueError."""
        action_item = {
            "task": bad_task,
            "owner": "Alice",
            "due": None
        }
        key_points = ["Key point 1"]

        with pytest.raises(ValueError) as exc_info:
            build_ticket_payload(action_item, key_points, "PROJ")
        assert "empty" in str(exc_info.value).lower()

    def test_build_ticket_payload_adf_format(self):
        """Test that ADF description is correctly formatted."""
        action_item = {
            "task": "Review proposal",
            "owner": "Charlie",
            "due": "2024-12-31"
        }
        key_points = ["Point A", "Point B"]

        payload = build_ticket_payload(action_item, key_points, "TEST")

        description = payload["fields"]["description"]

        # Check ADF structure
        assert description["type"] == "doc"
        assert description["version"] == 1
        # Should have: Context, 2 key points, Task, Owner = 5 paragraphs
        assert len(description["content"]) == 5

        # Check first paragraph (Context)
        paragraph = description["content"][0]
        assert paragraph["type"] == "paragraph"
        assert len(paragraph["content"]) == 1

        text = paragraph["content"][0]
        assert text["type"] == "text"
        assert text["text"] == "Context:"

    def test_build_ticket_payload_project_and_issuetype(self):
        """Test that project key and issue type are set correctly."""
        action_item = {
            "task": "Do something",
            "owner": "Dave",
            "due": None
        }
        key_points = ["Info"]

        payload = build_ticket_payload(action_item, key_points, "MYPROJ")

        assert payload["fields"]["project"]["key"] == "MYPROJ"
        assert payload["fields"]["issuetype"]["name"] == "Task"

    def test_build_ticket_payload_formats_description_correctly(self):
        """Test that description formatting includes context and task info."""
        action_item = {
            "task": "Implement feature X",
            "owner": "Eve",
            "due": "2024-12-31"
        }
        key_points = ["Design complete", "Budget approved"]

        payload = build_ticket_payload(action_item, key_points, "PROJ")

        description = payload["fields"]["description"]
        # Extract all text from all paragraphs
        description_text = " ".join([
            para["content"][0]["text"] for para in description["content"]
        ])

        # Check all components are present
        assert "Context:" in description_text
        assert "- Design complete" in description_text
        assert "- Budget approved" in description_text
        assert "Task: Implement feature X" in description_text
        assert "Owner: Eve" in description_text


@pytest.mark.unit
class TestCreateJiraTickets:
    """Tests for create_jira_tickets() function."""

    def test_create_jira_tickets_calls_correct_endpoint(self, mocker):
        """Test that POST is made to correct Jira endpoint with Basic Auth."""
        insights = {
            "action_items": [
                {
                    "task": "First task",
                    "owner": "Alice",
                    "due": None
                }
            ],
            "key_points": ["Point 1"]
        }

        mock_response = mocker.MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"key": "PROJ-1"}

        mock_post = mocker.patch("zoom_insights.jira_export.requests.post", return_value=mock_response)
        created_keys = create_jira_tickets(
            insights,
            "https://company.atlassian.net",
            "user@company.com",
            "test_token_123",
            "PROJ"
        )

        # Check endpoint
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://company.atlassian.net/rest/api/3/issue"

        # Check Basic Auth header
        headers = call_args[1]["headers"]
        auth_str = "user@company.com:test_token_123"
        expected_auth = base64.b64encode(auth_str.encode()).decode()
        assert headers["Authorization"] == f"Basic {expected_auth}"

        assert created_keys == ["PROJ-1"]

    def test_create_jira_tickets_returns_keys(self, mocker):
        """Test that function returns list of created ticket keys."""
        insights = {
            "action_items": [
                {"task": "Task 1", "owner": "Alice", "due": None},
                {"task": "Task 2", "owner": "Bob", "due": "2024-12-20"},
                {"task": "Task 3", "owner": None, "due": None}
            ],
            "key_points": ["Point A", "Point B"]
        }

        mock_response = mocker.MagicMock()
        mock_response.status_code = 201

        def side_effect(*args, **kwargs):
            # Extract task from payload to generate appropriate key
            payload = kwargs["json"]
            task = payload["fields"]["summary"]
            if task == "Task 1":
                mock_response.json.return_value = {"key": "PROJ-100"}
            elif task == "Task 2":
                mock_response.json.return_value = {"key": "PROJ-101"}
            elif task == "Task 3":
                mock_response.json.return_value = {"key": "PROJ-102"}
            return mock_response

        mocker.patch("zoom_insights.jira_export.requests.post", side_effect=side_effect)
        created_keys = create_jira_tickets(
            insights,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ"
        )

        assert len(created_keys) == 3
        assert "PROJ-100" in created_keys
        assert "PROJ-101" in created_keys
        assert "PROJ-102" in created_keys

    def test_create_jira_tickets_skips_empty_task(self, mocker):
        """Test that action items with empty task are skipped."""
        insights = {
            "action_items": [
                {"task": "Valid task", "owner": "Alice", "due": None},
                {"task": "", "owner": "Bob", "due": None},
                {"task": None, "owner": "Charlie", "due": None},
                {"task": "Another valid", "owner": None, "due": None}
            ],
            "key_points": ["Point"]
        }

        mock_response = mocker.MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"key": "PROJ-1"}

        mock_post = mocker.patch("zoom_insights.jira_export.requests.post", return_value=mock_response)
        created_keys = create_jira_tickets(
            insights,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ"
        )

        # Only 2 tickets should be created (valid task and another valid)
        assert len(created_keys) == 2
        # Only 2 POST calls should be made
        assert mock_post.call_count == 2

    def test_create_jira_tickets_continues_on_error(self, mocker):
        """Test that function continues to next item if one returns error."""
        insights = {
            "action_items": [
                {"task": "Task 1", "owner": "Alice", "due": None},
                {"task": "Task 2", "owner": "Bob", "due": None},
                {"task": "Task 3", "owner": "Charlie", "due": None}
            ],
            "key_points": ["Point"]
        }

        # Mock responses: success, error, success
        responses = [
            (201, {"key": "PROJ-1"}),
            (400, None),  # Error response
            (201, {"key": "PROJ-3"})
        ]
        response_iter = iter(responses)

        def side_effect(*args, **kwargs):
            status, body = next(response_iter)
            mock_response = mocker.MagicMock()
            mock_response.status_code = status
            if body:
                mock_response.json.return_value = body
            mock_response.text = "Bad request"
            return mock_response

        mocker.patch("zoom_insights.jira_export.requests.post", side_effect=side_effect)
        created_keys = create_jira_tickets(
            insights,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ"
        )

        # Should have created 2 tickets despite error in middle
        assert len(created_keys) == 2
        assert "PROJ-1" in created_keys
        assert "PROJ-3" in created_keys

    def test_create_jira_tickets_missing_action_items_key(self):
        """Test that missing action_items raises ValueError."""
        insights = {
            "key_points": ["Point"]
            # Missing action_items
        }

        with pytest.raises(ValueError) as exc_info:
            create_jira_tickets(
                insights,
                "https://test.atlassian.net",
                "test@test.com",
                "token",
                "PROJ"
            )
        assert "action_items" in str(exc_info.value)

    def test_create_jira_tickets_missing_key_points_key(self):
        """Test that missing key_points raises ValueError."""
        insights = {
            "action_items": [
                {"task": "Task", "owner": "Alice", "due": None}
            ]
            # Missing key_points
        }

        with pytest.raises(ValueError) as exc_info:
            create_jira_tickets(
                insights,
                "https://test.atlassian.net",
                "test@test.com",
                "token",
                "PROJ"
            )
        assert "key_points" in str(exc_info.value)

    def test_create_jira_tickets_empty_action_items_list(self, mocker):
        """Test that empty action_items list returns empty list of created keys."""
        insights = {
            "action_items": [],
            "key_points": ["Point"]
        }

        mock_post = mocker.patch("zoom_insights.jira_export.requests.post")
        created_keys = create_jira_tickets(
            insights,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ"
        )

        # No POST calls should be made
        assert mock_post.call_count == 0
        assert created_keys == []

    def test_create_jira_tickets_passes_payload_correctly(self, mocker):
        """Test that payload is correctly passed to requests.post."""
        insights = {
            "action_items": [
                {"task": "Review docs", "owner": "Alice", "due": "2024-12-20"}
            ],
            "key_points": ["Docs complete"]
        }

        mock_response = mocker.MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"key": "PROJ-42"}

        mock_post = mocker.patch("zoom_insights.jira_export.requests.post", return_value=mock_response)
        created_keys = create_jira_tickets(
            insights,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ"
        )

        # Verify payload structure
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]

        assert payload["fields"]["summary"] == "Review docs"
        assert payload["fields"]["project"]["key"] == "PROJ"
        assert payload["fields"]["issuetype"]["name"] == "Task"

        # Description should be ADF format
        description = payload["fields"]["description"]
        assert description["type"] == "doc"
        assert description["version"] == 1

        assert created_keys == ["PROJ-42"]
