"""Jira Cloud export module for exporting insights as tickets."""

import base64
import json
import logging
from typing import Optional
import requests

from zoom_insights.retry import with_retry

logger = logging.getLogger(__name__)


def _build_auth_header(email: str, api_token: str) -> str:
    """Build a Basic auth header for Jira API.

    Args:
        email: Jira user email.
        api_token: Jira API token.

    Returns:
        Authorization header value (e.g., "Basic base64(...)").
    """
    auth_str = f"{email}:{api_token}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    return f"Basic {encoded_auth}"


def _render_bullet_section(header: str, items: list) -> list[dict]:
    """Build ADF paragraph nodes for a bullet section (header + bullets).

    Args:
        header: Section header text (e.g., "Test Scenarios:")
        items: List of items (strings or dicts with 'title'/'description' keys)

    Returns:
        List of ADF paragraph dicts (header + one bullet per item), or [] if items is empty/None
    """
    if not items:
        return []

    adf_content = [
        {"type": "paragraph", "content": [{"type": "text", "text": header}]}
    ]

    for item in items:
        # Extract text from dict items (use title, then description, then str() fallback)
        if isinstance(item, dict):
            item_text = item.get("title") or item.get("description") or str(item)
        else:
            item_text = item

        adf_content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": f"  • {item_text}"}]
        })

    return adf_content


def _post_with_jira_retry(endpoint: str, **kwargs) -> requests.Response:
    """Make a POST request to Jira with retry on transient errors.

    Raises exceptions on auth errors (non-transient) and 5xx server errors (transient),
    which are handled by with_retry. Returns the response for all other status codes.

    Args:
        endpoint: Jira API endpoint URL
        **kwargs: keyword arguments to pass to requests.post (json, headers, timeout, etc.)

    Returns:
        Response object from requests.post

    Raises:
        RuntimeError: on 401/403 auth errors or 5xx server errors
    """
    response = requests.post(endpoint, **kwargs)

    # Auth errors are non-transient — fail immediately without retrying
    if response.status_code in (401, 403):
        raise RuntimeError(f"Jira authentication failed ({response.status_code})")

    # 5xx errors are transient — with_retry will retry on these
    if response.status_code >= 500:
        raise RuntimeError(f"Jira server error: HTTP {response.status_code}")

    # Return response for all other status codes (including 4xx non-auth errors)
    return response


def build_ticket_payload(action_item: dict, key_points: list[str], project_key: str, qa_recommendations: Optional[dict] = None) -> dict:
    """Build a Jira ticket payload from an action item with optional QA recommendations.

    Args:
        action_item: dict with 'task', 'owner', 'due' keys
        key_points: list of meeting key points for context
        project_key: Jira project key (e.g., "PROJ")
        qa_recommendations: optional dict with 'test_scenarios', 'features_to_add', 'edge_cases_to_cover'

    Returns:
        dict with Jira API v3 ticket structure (fields.summary, fields.description in ADF)

    Raises:
        ValueError: if task is empty or None
    """
    task = action_item.get("task", "").strip() if action_item.get("task") else ""

    # Validate task is not empty
    if not task:
        raise ValueError("task field cannot be empty or None")

    owner = action_item.get("owner") or "Unassigned"

    # Build ADF (Atlassian Document Format) for description with line breaks
    # Each paragraph node renders as a separate line in Jira
    adf_content = [
        {"type": "paragraph", "content": [{"type": "text", "text": "Context:"}]}
    ]

    for kp in key_points:
        adf_content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": f"- {kp}"}]
        })

    adf_content.extend([
        {"type": "paragraph", "content": [{"type": "text", "text": f"Task: {task}"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": f"Owner: {owner}"}]},
    ])

    # Add QA recommendations if available
    if qa_recommendations:
        has_qa_content = any([
            qa_recommendations.get("test_scenarios"),
            qa_recommendations.get("features_to_add"),
            qa_recommendations.get("edge_cases_to_cover"),
        ])

        if has_qa_content:
            adf_content.append({"type": "paragraph", "content": [{"type": "text", "text": ""}]})
            adf_content.append({"type": "paragraph", "content": [{"type": "text", "text": "QA Recommendations:"}]})
            adf_content.extend(_render_bullet_section("Test Scenarios:", qa_recommendations.get("test_scenarios", [])))
            adf_content.extend(_render_bullet_section("Features to Add:", qa_recommendations.get("features_to_add", [])))
            adf_content.extend(_render_bullet_section("Edge Cases to Cover:", qa_recommendations.get("edge_cases_to_cover", [])))

    adf_description = {
        "type": "doc",
        "version": 1,
        "content": adf_content
    }

    # Build and return ticket payload
    return {
        "fields": {
            "summary": task,
            "description": adf_description,
            "project": {"key": project_key},
            "issuetype": {"name": "Task"}
        }
    }


def _build_subtask_description(scenario: str, qa_recommendations: Optional[dict]) -> dict:
    """Build an ADF description for a test-scenario subtask with context.

    Args:
        scenario: Test scenario text (required)
        qa_recommendations: Optional dict with 'edge_cases_to_cover', 'features_to_add'
                           to include in subtask for reference

    Returns:
        Full ADF dict with {"type": "doc", "version": 1, "content": [...]}
    """
    adf_content = []

    # Always include the test scenario section
    if scenario:
        adf_content.extend(_render_bullet_section("Test Scenario:", [scenario]))

    # Add supporting context if qa_recommendations is provided
    if qa_recommendations:
        adf_content.extend(_render_bullet_section("Edge Cases to Consider:", qa_recommendations.get("edge_cases_to_cover", [])))
        adf_content.extend(_render_bullet_section("Related Features:", qa_recommendations.get("features_to_add", [])))

    # Return ADF document
    return {
        "type": "doc",
        "version": 1,
        "content": adf_content if adf_content else [
            {"type": "paragraph", "content": [{"type": "text", "text": scenario}]}
        ]
    }


def _create_subtask(
    parent_key: str,
    title: str,
    description_adf: dict,
    jira_url: str,
    email: str,
    api_token: str,
    project_key: str,
) -> Optional[str]:
    """Create a subtask under a parent ticket.

    Args:
        parent_key: Parent ticket key (e.g., "PROJ-1")
        title: Subtask summary/title
        description_adf: Pre-built ADF dict for subtask description
        jira_url: Jira Cloud instance URL
        email: Jira user email
        api_token: Jira API token
        project_key: Jira project key

    Returns:
        Subtask key if created, None if failed
    """
    headers = {
        "Authorization": _build_auth_header(email, api_token),
        "Content-Type": "application/json"
    }

    payload = {
        "fields": {
            "summary": title,
            "description": description_adf,
            "project": {"key": project_key},
            "issuetype": {"name": "Subtask"},
            "parent": {"key": parent_key},
        }
    }

    try:
        endpoint = f"{jira_url}/rest/api/3/issue"
        response = with_retry(_post_with_jira_retry, endpoint, json=payload, headers=headers, timeout=30)

        if response.status_code == 201:
            subtask_key = response.json().get("key")
            logger.info(f"Created subtask {subtask_key} for {parent_key}")
            return subtask_key
        else:
            logger.warning(f"Failed to create subtask for {parent_key}: HTTP {response.status_code}")
            return None

    except Exception as e:
        logger.warning(f"Exception creating subtask for {parent_key}: {e}")
        return None


def create_jira_tickets(
    insights: dict,
    jira_url: str,
    email: str,
    api_token: str,
    project_key: str
) -> list[str]:
    """Create Jira tickets from insights action items.

    Args:
        insights: dict with 'action_items' and 'key_points' keys (optional: 'qa_recommendations')
        jira_url: Jira Cloud instance URL (e.g., "https://mycompany.atlassian.net")
        email: Jira user email for authentication
        api_token: Jira API token for authentication
        project_key: Jira project key (e.g., "PROJ")

    Returns:
        list of created ticket keys (e.g., ["PROJ-1", "PROJ-2"])

    Raises:
        ValueError: if insights missing required 'action_items' or 'key_points'
    """
    # Validate required fields in insights
    if "action_items" not in insights:
        raise ValueError("Insights missing 'action_items' key")
    if "key_points" not in insights:
        raise ValueError("Insights missing 'key_points' key")

    action_items = insights["action_items"]
    key_points = insights["key_points"]
    qa_recommendations = insights.get("qa_recommendations", {})

    # Build headers with auth (once)
    headers = {
        "Authorization": _build_auth_header(email, api_token),
        "Content-Type": "application/json"
    }

    # Preflight auth check before creating any tickets
    try:
        preflight_response = requests.get(
            f"{jira_url}/rest/api/3/myself",
            headers=headers,
            timeout=5
        )
        if preflight_response.status_code in (401, 403):
            raise RuntimeError(
                f"Jira authentication failed ({preflight_response.status_code}): "
                "check JIRA_EMAIL and JIRA_API_TOKEN"
            )
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to validate Jira credentials: {e}")

    # Create tickets
    created_keys = []
    endpoint = f"{jira_url}/rest/api/3/issue"

    for action_item in action_items:
        # Skip empty tasks
        task = action_item.get("task", "").strip() if action_item.get("task") else ""
        if not task:
            logger.debug(f"Skipping action item with empty task")
            continue

        try:
            # Build and POST ticket with QA recommendations (with retry on transient errors)
            payload = build_ticket_payload(action_item, key_points, project_key, qa_recommendations)
            response = with_retry(_post_with_jira_retry, endpoint, json=payload, headers=headers, timeout=30)

            if response.status_code == 201:
                # Success
                ticket_key = response.json().get("key")
                created_keys.append(ticket_key)
                ticket_url = f"{jira_url}/browse/{ticket_key}"
                print(f"Created: {ticket_key} — {ticket_url}")
                logger.info(f"Created ticket {ticket_key}")

                # Create subtasks for QA recommendations if available
                if qa_recommendations:
                    test_scenarios = qa_recommendations.get("test_scenarios", [])
                    for scenario in test_scenarios:
                        description_adf = _build_subtask_description(scenario, qa_recommendations)
                        subtask_key = _create_subtask(
                            ticket_key,
                            f"Test: {scenario}",
                            description_adf,
                            jira_url,
                            email,
                            api_token,
                            project_key,
                        )
                        if subtask_key:
                            print(f"  Created subtask: {subtask_key}")

            else:
                # Other errors (400, etc.) — warn and skip this ticket
                # (5xx errors were retried and failed, auth errors raise exception)
                try:
                    error_text = response.text
                except Exception:
                    error_text = f"HTTP {response.status_code}"
                print(f"Warning: Failed to create ticket for task '{task}': {response.status_code} {error_text}")
                logger.warning(f"Failed to create ticket: {response.status_code} {error_text}")

        except Exception as e:
            print(f"Warning: Error creating ticket for task '{task}': {e}")
            logger.warning(f"Exception creating ticket: {e}")

    return created_keys
