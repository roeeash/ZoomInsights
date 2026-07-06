"""Notification integration for Slack and Teams."""

import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def detect_platform(webhook_url: str) -> str:
    """Detect notification platform from webhook URL.

    Args:
        webhook_url: Slack or Teams webhook URL

    Returns:
        "slack", "teams", or "unknown"
    """
    if not webhook_url:
        return "unknown"

    url_lower = webhook_url.lower()
    if "hooks.slack.com" in url_lower:
        return "slack"
    elif "webhook.office.com" in url_lower or "outlook.webhook.office.com" in url_lower:
        return "teams"
    else:
        return "unknown"


def post_slack(insights: Dict[str, Any], webhook_url: str) -> bool:
    """Post a summary card to Slack.

    Args:
        insights: insights.json dict with summary, key_points, action_items
        webhook_url: Slack incoming webhook URL

    Returns:
        True on success, False on error (logs error without raising)
    """
    try:
        # Extract top 3 action items
        action_items = insights.get("action_items", [])
        top_items = action_items[:3]

        # Build action items text
        action_text = ""
        if top_items:
            action_text = "\n".join(
                f"• {item.get('task', 'Unnamed task')}"
                for item in top_items
            )

        # Build Block Kit card
        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Meeting Summary",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Summary*\n{insights.get('summary', 'No summary available')}"
                    }
                }
            ]
        }

        # Add action items section if present
        if action_text:
            payload["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Action Items*\n{action_text}"
                }
            })

        # POST to Slack webhook
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=5
        )

        if response.status_code == 200:
            logger.info("Successfully posted to Slack")
            return True
        else:
            logger.warning(
                f"Slack webhook returned {response.status_code}: {response.text}"
            )
            return False

    except requests.exceptions.Timeout:
        logger.warning("Slack webhook request timed out (5s)")
        return False
    except Exception as e:
        logger.warning(f"Error posting to Slack: {e}")
        return False


def post_teams(insights: Dict[str, Any], webhook_url: str) -> bool:
    """Post a summary card to Microsoft Teams.

    Args:
        insights: insights.json dict with summary, key_points, action_items
        webhook_url: Teams incoming webhook URL

    Returns:
        True on success, False on error (logs error without raising)
    """
    try:
        # Extract top 3 action items
        action_items = insights.get("action_items", [])
        top_items = action_items[:3]

        # Build action items text
        facts = []
        for i, item in enumerate(top_items, 1):
            facts.append({
                "name": f"Item {i}",
                "value": item.get("task", "Unnamed task")
            })

        # Build Adaptive Card
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": "Meeting Summary",
            "themeColor": "0078D4",
            "sections": [
                {
                    "activityTitle": "Meeting Summary",
                    "text": insights.get("summary", "No summary available")
                }
            ]
        }

        # Add action items section if present
        if facts:
            payload["sections"].append({
                "activityTitle": "Action Items",
                "facts": facts
            })

        # POST to Teams webhook
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=5
        )

        if response.status_code == 200:
            logger.info("Successfully posted to Teams")
            return True
        else:
            logger.warning(
                f"Teams webhook returned {response.status_code}: {response.text}"
            )
            return False

    except requests.exceptions.Timeout:
        logger.warning("Teams webhook request timed out (5s)")
        return False
    except Exception as e:
        logger.warning(f"Error posting to Teams: {e}")
        return False


def post_notification(insights: Dict[str, Any], webhook_url: str) -> bool:
    """Post notification to Slack or Teams based on webhook URL.

    Auto-detects the platform and dispatches to the appropriate function.

    Args:
        insights: insights.json dict with summary, key_points, action_items
        webhook_url: Slack or Teams incoming webhook URL

    Returns:
        True on success, False on error (logs error without raising)
    """
    if not webhook_url:
        logger.warning("No webhook URL provided")
        return False

    platform = detect_platform(webhook_url)

    if platform == "slack":
        return post_slack(insights, webhook_url)
    elif platform == "teams":
        return post_teams(insights, webhook_url)
    else:
        logger.warning(f"Unknown notification platform for URL: {webhook_url}")
        return False
