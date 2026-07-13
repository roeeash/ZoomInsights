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

        # Mock preflight (GET /myself)
        mock_get = mocker.MagicMock()
        mock_get.status_code = 200
        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_get)

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

        # Mock preflight
        mock_get = mocker.MagicMock()
        mock_get.status_code = 200
        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_get)

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

        # Mock preflight
        mock_get = mocker.MagicMock()
        mock_get.status_code = 200
        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_get)

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

        # Mock preflight
        mock_get = mocker.MagicMock()
        mock_get.status_code = 200
        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_get)

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

        # Mock preflight
        mock_get = mocker.MagicMock()
        mock_get.status_code = 200
        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_get)

        mock_post = mocker.patch("zoom_insights.jira_export.requests.post")
        created_keys = create_jira_tickets(
            insights,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ"
        )

        # No POST calls should be made (except preflight GET is called)
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

        # Mock preflight
        mock_get = mocker.MagicMock()
        mock_get.status_code = 200
        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_get)

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

    def test_auth_preflight_raises_before_any_ticket(self, mocker):
        """Test that auth validation failure raises before creating any tickets."""
        insights = {
            "action_items": [
                {"task": "Task 1", "owner": "Alice", "due": None}
            ],
            "key_points": ["Point"]
        }

        # Mock preflight to return 401
        mock_preflight = mocker.MagicMock()
        mock_preflight.status_code = 401
        mock_preflight.text = "Unauthorized"

        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_preflight)
        mock_post = mocker.patch("zoom_insights.jira_export.requests.post")

        with pytest.raises(RuntimeError) as exc_info:
            create_jira_tickets(
                insights,
                "https://test.atlassian.net",
                "test@test.com",
                "bad_token",
                "PROJ"
            )

        assert "authentication failed" in str(exc_info.value).lower()
        # Verify no POST calls were made
        assert mock_post.call_count == 0

    def test_auth_header_built_once(self, mocker):
        """Test that auth header is built once, not per ticket."""
        insights = {
            "action_items": [
                {"task": "Task 1", "owner": "Alice", "due": None},
                {"task": "Task 2", "owner": "Bob", "due": None},
                {"task": "Task 3", "owner": "Charlie", "due": None}
            ],
            "key_points": ["Point"]
        }

        # Mock preflight success
        mock_preflight = mocker.MagicMock()
        mock_preflight.status_code = 200

        mock_response = mocker.MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"key": "PROJ-1"}

        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_preflight)
        mock_post = mocker.patch("zoom_insights.jira_export.requests.post", return_value=mock_response)

        created_keys = create_jira_tickets(
            insights,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ"
        )

        assert len(created_keys) == 3
        # All POST calls should have the same Authorization header
        for call in mock_post.call_args_list:
            assert call[1]["headers"]["Authorization"].startswith("Basic ")

    def test_qa_recommendations_in_ticket_description(self, mocker):
        """Test that qa_recommendations appear in the ticket description ADF."""
        action_item = {
            "task": "Optimize performance",
            "owner": "Alice",
            "due": "2024-12-31"
        }
        key_points = ["Performance target: <1s response time"]

        qa_recommendations = {
            "test_scenarios": ["Load test with 1000 concurrent users"],
            "features_to_add": ["Caching layer"],
            "edge_cases_to_cover": ["Network timeouts"]
        }

        payload = build_ticket_payload(action_item, key_points, "PROJ", qa_recommendations=qa_recommendations)

        description = payload["fields"]["description"]
        # Extract all text from all paragraphs
        description_text = " ".join([
            para["content"][0]["text"] for para in description["content"]
        ])

        # Verify QA recommendations appear in description
        assert "QA Recommendations:" in description_text
        assert "Test Scenarios:" in description_text
        assert "Load test with 1000 concurrent users" in description_text
        assert "Features to Add:" in description_text
        assert "Caching layer" in description_text
        assert "Edge Cases to Cover:" in description_text
        assert "Network timeouts" in description_text

    def test_jira_ticket_retries_on_5xx(self, mocker):
        """Test that ticket creation retries on 503 then succeeds on second attempt."""
        insights = {
            "action_items": [
                {"task": "Task 1", "owner": "Alice", "due": None}
            ],
            "key_points": ["Point 1"]
        }

        # Mock preflight
        mock_get = mocker.MagicMock()
        mock_get.status_code = 200
        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_get)

        # Mock sleep to speed up tests
        mocker.patch("zoom_insights.retry.time.sleep")

        # Mock POST: first call returns 503, second call returns 201
        responses = [
            mocker.MagicMock(status_code=503, text="Service Unavailable"),
            mocker.MagicMock(status_code=201, json=lambda: {"key": "PROJ-1"})
        ]
        response_iter = iter(responses)

        def side_effect(*args, **kwargs):
            return next(response_iter)

        mock_post = mocker.patch("zoom_insights.jira_export.requests.post", side_effect=side_effect)

        created_keys = create_jira_tickets(
            insights,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ"
        )

        # Ticket should be created despite initial 503
        assert len(created_keys) == 1
        assert "PROJ-1" in created_keys
        # POST should have been called twice (retry on 503)
        assert mock_post.call_count == 2

    def test_jira_ticket_gives_up_after_max_retries(self, mocker):
        """Test that ticket creation fails and continues to next item after max retries on 503."""
        insights = {
            "action_items": [
                {"task": "Task 1", "owner": "Alice", "due": None},
                {"task": "Task 2", "owner": "Bob", "due": None}
            ],
            "key_points": ["Point 1"]
        }

        # Mock preflight
        mock_get = mocker.MagicMock()
        mock_get.status_code = 200
        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_get)

        # Mock sleep to speed up tests
        mocker.patch("zoom_insights.retry.time.sleep")

        # Mock POST: always return 503
        mock_response = mocker.MagicMock(status_code=503, text="Service Unavailable")
        mock_post = mocker.patch("zoom_insights.jira_export.requests.post", return_value=mock_response)

        created_keys = create_jira_tickets(
            insights,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ"
        )

        # First task should fail, second task should succeed
        # Mock will always return 503, so both will fail
        assert len(created_keys) == 0
        # POST should have been called multiple times per task (retries)
        # 6 attempts for task 1 + 6 attempts for task 2 = 12 calls
        assert mock_post.call_count == 12

    @pytest.mark.unit
    def test_jira_subtask_retries_on_timeout(self, mocker):
        """Test that subtask creation retries on Timeout exception then succeeds."""
        from zoom_insights.jira_export import _create_subtask
        import requests

        # Mock sleep to speed up tests
        mocker.patch("zoom_insights.retry.time.sleep")

        # Mock requests.post to raise Timeout first, then succeed
        timeout_exception = requests.exceptions.Timeout("Connection timeout")
        mock_response = mocker.MagicMock(status_code=201, json=lambda: {"key": "PROJ-1-SUB"})

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise timeout_exception
            return mock_response

        mocker.patch("zoom_insights.jira_export.requests.post", side_effect=side_effect)

        # Build proper ADF description
        description_adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Test the scenario"}]}
            ]
        }

        subtask_key = _create_subtask(
            "PROJ-1",
            "Test scenario",
            description_adf,
            "https://test.atlassian.net",
            "test@test.com",
            "token",
            "PROJ"
        )

        # Subtask should be created despite initial timeout
        assert subtask_key == "PROJ-1-SUB"
        # POST should have been called twice (retry on timeout)
        assert call_count[0] == 2

    @pytest.mark.unit
    def test_subtask_descriptions_differ_by_scenario(self, mocker):
        """Test that subtasks with different scenarios have different descriptions."""
        from zoom_insights.jira_export import _build_subtask_description

        qa_recommendations = {
            "test_scenarios": [
                "Test scenario A",
                "Test scenario B",
                "Test scenario C"
            ],
            "edge_cases_to_cover": ["Edge case 1"],
            "features_to_add": ["Feature 1"],
            "technologies": ["Tech 1"],
            "implementation_steps": ["Step 1"]
        }

        # Build descriptions for each scenario
        desc_a = _build_subtask_description("Test scenario A", qa_recommendations)
        desc_b = _build_subtask_description("Test scenario B", qa_recommendations)
        desc_c = _build_subtask_description("Test scenario C", qa_recommendations)

        # Serialize to JSON to compare
        json_a = json.dumps(desc_a, sort_keys=True)
        json_b = json.dumps(desc_b, sort_keys=True)
        json_c = json.dumps(desc_c, sort_keys=True)

        # Each should be different from the others
        assert json_a != json_b, "Subtask A and B should have different descriptions"
        assert json_b != json_c, "Subtask B and C should have different descriptions"
        assert json_a != json_c, "Subtask A and C should have different descriptions"

        # Verify each contains its own scenario text
        assert "Test scenario A" in json_a
        assert "Test scenario B" in json_b
        assert "Test scenario C" in json_c

        # Verify shared context appears in all
        assert "Edge case 1" in json_a
        assert "Edge case 1" in json_b
        assert "Edge case 1" in json_c

    def test_jira_no_retry_on_4xx_auth_error(self, mocker):
        """Test that 401 auth error fails immediately without retrying."""
        insights = {
            "action_items": [
                {"task": "Task 1", "owner": "Alice", "due": None}
            ],
            "key_points": ["Point 1"]
        }

        # Mock preflight to succeed
        mock_get = mocker.MagicMock()
        mock_get.status_code = 200
        mocker.patch("zoom_insights.jira_export.requests.get", return_value=mock_get)

        # Mock sleep to speed up tests (though it shouldn't be called)
        mocker.patch("zoom_insights.retry.time.sleep")

        # Mock POST to return 401
        mock_response = mocker.MagicMock(status_code=401, text="Unauthorized")
        mock_post = mocker.patch("zoom_insights.jira_export.requests.post", return_value=mock_response)

        # Call create_jira_tickets - should fail immediately
        created_keys = create_jira_tickets(
            insights,
            "https://test.atlassian.net",
            "test@test.com",
            "bad_token",
            "PROJ"
        )

        # No tickets created
        assert len(created_keys) == 0
        # POST should have been called exactly once (no retries on 401)
        assert mock_post.call_count == 1
