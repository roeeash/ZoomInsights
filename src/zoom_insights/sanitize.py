"""Transcript sanitization — remove prompt-injection patterns and malicious content."""

import logging
import re

logger = logging.getLogger(__name__)

# Patterns that suggest prompt injection attempts (case-insensitive)
INJECTION_PATTERNS = [
    r"system\s*:",
    r"ignore\s+instructions?",
    r"override",
    r"bypass",
    r"admin\s+mode",
    r"jailbreak",
    r"forget\s+everything",
    r"disregard",
    r"pretend",
    r"act\s+as\s+(?:an?\s+)?(?:evil|malicious|hacker)",
]

# HTML/XML tags that could be dangerous
DANGEROUS_TAGS = [
    r"<script[^>]*>.*?</script>",
    r"<iframe[^>]*>.*?</iframe>",
    r"<object[^>]*>.*?</object>",
    r"<embed[^>]*>",
    r"<link[^>]*>",
    r"javascript:",
    r"on\w+\s*=",  # event handlers
]


def sanitize_transcript(text: str) -> str:
    """Remove prompt-injection patterns and dangerous content from transcript.

    Args:
        text: Raw transcript text.

    Returns:
        Sanitized transcript with injection patterns removed.
    """
    if not text:
        return "" if text is None else text

    sanitized = text
    injection_found = False

    # Check for and remove injection patterns
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, sanitized, re.IGNORECASE):
            injection_found = True
            # Remove the line(s) containing the pattern
            sanitized = re.sub(
                f".*{pattern}.*",
                "",
                sanitized,
                flags=re.IGNORECASE | re.MULTILINE,
            )

    # Escape/remove dangerous HTML tags
    for tag_pattern in DANGEROUS_TAGS:
        if re.search(tag_pattern, sanitized, re.IGNORECASE):
            injection_found = True
            sanitized = re.sub(tag_pattern, "", sanitized, flags=re.IGNORECASE | re.DOTALL)

    # Collapse excessive newlines (5+ → 2)
    sanitized = re.sub(r"\n{5,}", "\n\n", sanitized)

    # Log warning if patterns were found
    if injection_found:
        logger.warning(
            "Transcript sanitization: removed prompt-injection patterns. "
            "Check raw transcript for suspicious content."
        )

    return sanitized
