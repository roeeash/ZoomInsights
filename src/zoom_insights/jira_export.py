"""Jira Cloud export module for exporting insights as tickets."""

import base64
import json
import logging
import requests

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


def build_ticket_payload(action_item: dict, key_points: list[str], project_key: str) -> dict:
    """Build a Jira ticket payload from an action item.

    Args:
        action_item: dict with 'task', 'owner', 'due' keys
        key_points: list of meeting key points for context
        project_key: Jira project key (e.g., "PROJ")

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


def create_jira_tickets(
    insights: dict,
    jira_url: str,
    email: str,
    api_token: str,
    project_key: str
) -> list[str]:
    """Create Jira tickets from insights action items.

    Args:
        insights: dict with 'action_items' and 'key_points' keys
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

    # Build headers with auth
    headers = {
        "Authorization": _build_auth_header(email, api_token),
        "Content-Type": "application/json"
    }

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
            # Build and POST ticket
            payload = build_ticket_payload(action_item, key_points, project_key)
            response = requests.post(endpoint, json=payload, headers=headers, timeout=30)

            if response.status_code == 201:
                # Success
                ticket_key = response.json().get("key")
                created_keys.append(ticket_key)
                ticket_url = f"{jira_url}/browse/{ticket_key}"
                print(f"Created: {ticket_key} — {ticket_url}")
                logger.info(f"Created ticket {ticket_key}")
            elif response.status_code in (401, 403):
                # Authentication/authorization failure — fatal
                raise RuntimeError(
                    f"Jira authentication failed ({response.status_code}): "
                    "check JIRA_EMAIL and JIRA_API_TOKEN"
                )
            else:
                # Other errors (400, 500, etc.) — warn and skip this ticket
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
