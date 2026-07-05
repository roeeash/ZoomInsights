"""Summary and structured insights extraction using map-reduce pattern."""

import json
import logging
import re
from jsonschema import validate, ValidationError
from zoom_insights.retry import with_retry

logger = logging.getLogger(__name__)

INSIGHTS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "owner": {"type": ["string", "null"]},
                    "task": {"type": "string"},
                    "due": {"type": ["string", "null"]},
                },
                "required": ["owner", "task", "due"],
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "notable_quotes": {"type": "array", "items": {"type": "string"}},
        "qa_recommendations": {
            "type": "object",
            "properties": {
                "test_scenarios": {"type": "array", "items": {"type": "string"}},
                "features_to_add": {"type": "array", "items": {"type": "string"}},
                "edge_cases_to_cover": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "required": [
        "summary",
        "key_points",
        "decisions",
        "action_items",
        "open_questions",
        "notable_quotes",
    ],
}


def chunk(text: str, size: int = 11000) -> list[str]:
    """Split text into word-aware chunks of approximately the given size."""
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0

    for word in words:
        word_len = len(word) + 1  # +1 for space
        if current_size + word_len > size and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_size = word_len
        else:
            current_chunk.append(word)
            current_size += word_len

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def map_phase(chunks: list[str], client, model: str) -> list[str]:
    """Summarize each chunk via LLM into tight bullets (map phase)."""
    summaries = []

    for i, chunk_text in enumerate(chunks):
        logger.info(f"Summarizing chunk {i + 1}/{len(chunks)}")

        messages = [
            {
                "role": "system",
                "content": """You are a meeting analyst. Analyze this transcript chunk and extract specific, concrete details:
- Key discussion points: Capture WHAT specifically was discussed, including technical details, tool names, features, concerns, and component names mentioned
- Decisions made: Explicit choices or commitments (e.g., "we decided to use X", "approved Y")
- Action items: Tasks that must happen as a result - interpret implied tasks from "we need to", "should", "must", "follow up", "fix", etc. Deduce WHO and WHAT specifically.
- Questions raised: Unresolved issues, concerns, or unknowns that were discussed

CRITICAL: Be specific and concrete. Capture actual names, tools, features, concerns mentioned - don't generalize to vague descriptions.
Action items must be specific (e.g., "Fix performance issue in transcription module" not just "Fix issues").
Do NOT fabricate information. Do NOT repeat verbatim; interpret meaningfully.""",
            },
            {
                "role": "user",
                "content": f"Extract key insights from this chunk, focusing on SPECIFIC DETAILS and TECHNICAL CONTENT:\n\n{chunk_text}",
            },
        ]

        try:
            response = with_retry(
                client.chat.completions.create,
                model=model,
                max_tokens=1024,
                messages=messages,
            )

            # Handle Groq response (has .choices[0].message.content)
            if isinstance(response, str):
                summary_text = response
            else:
                summary_text = response.choices[0].message.content

            summaries.append(summary_text)
            logger.debug(f"Chunk {i + 1} summary: {len(summary_text)} characters")

        except Exception as e:
            logger.warning(f"Error summarizing chunk {i + 1}: {e}")
            raise

    return summaries


def reduce_phase(summaries: list[str], client, model: str, repo_summary: str = "", agent_guidance: str = "") -> dict:
    """Combine summaries into final insights JSON with optional QA recommendations."""
    combined_text = "\n\n".join(summaries)

    logger.info("Reducing summaries to final insights (with QA recommendations)")

    qa_section = ""
    agent_context = ""
    if repo_summary:
        qa_section = f"""
- qa_recommendations: QA recommendations based on meeting + repository context
  * test_scenarios: array of specific test scenarios to write based on meeting discussion and repo code
  * features_to_add: array of features or improvements mentioned or implied
  * edge_cases_to_cover: array of edge cases, error conditions, or boundary conditions to test
  * All recommendations must be specific and traceable to meeting content + code context"""

    if agent_guidance:
        agent_context = f"""

AGENT GUIDANCE FOR QA PRIORITIZATION:
{agent_guidance}

Apply this agent's philosophy: prioritize by blast radius and failure cost, not coverage metrics. Focus on tests that protect the critical path and catch regressions affecting the business."""

    messages = [
        {
            "role": "system",
            "content": f"""You are a meeting analyst and QA engineer. Produce a JSON object with these keys:
- summary: 2-3 sentence overview capturing WHAT was discussed, including specific tools, concerns, or technical details mentioned
- key_points: list of specific discussion points - include tool names, features, technical concerns, and concrete details discussed
- decisions: list of explicit commitments or decisions made (e.g., "decided to implement X", "approved Y feature")
- action_items: list of objects with owner (string|null), task (string), due (string|null)
  * CRITICAL: Action items are concrete tasks that must happen as a result of this meeting
  * Include specific WHAT: "Fix bug in transcription" not "Fix issues"
  * Deduce implied tasks from "we should", "we need to", "must", "follow up", "test", "implement", etc.
  * If owner is not mentioned, use null (don't guess names)
  * If no clear due date, use null (don't invent dates)
  * Each action item must be traceable to meeting content
- open_questions: list of specific unresolved issues or technical concerns raised (not generic questions)
- notable_quotes: list of important direct quotes (only if meeting actually contains quotable moments, else empty){qa_section}

CRITICAL: Capture SPECIFICITY - tool names, technical details, component names, feature names.
Do NOT invent information. Do NOT be vague or generic.{agent_context}""",
        },
        {
            "role": "user",
            "content": f"Create structured insights JSON. Emphasize SPECIFIC DETAILS, TECHNICAL CONTENT, and CONCRETE ACTION ITEMS:{repo_summary if repo_summary else ''}\n\n{combined_text}",
        },
    ]

    try:
        response = with_retry(
            client.chat.completions.create,
            model=model,
            max_tokens=2048,
            messages=messages,
        )

        # Handle Groq response (has .choices[0].message.content)
        if isinstance(response, str):
            result_text = response
        else:
            result_text = response.choices[0].message.content

        # Extract JSON from response
        try:
            insights = json.loads(result_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response text
            json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if json_match:
                insights = json.loads(json_match.group())
            else:
                raise ValueError("No JSON found in LLM response")

        return insights

    except Exception as e:
        logger.error(f"Error in reduce phase: {e}")
        raise


def summarize(transcript: str, client, model: str, repo_summary: str = "", agent_guidance: str = "") -> dict:
    """Execute the full map-reduce pipeline and return schema-valid insights with QA recommendations.

    Args:
        transcript: Full meeting transcript text.
        client: Groq API client.
        model: LLM model name to use.
        repo_summary: Optional repository code summary for QA recommendations.
        agent_guidance: Optional agent guidance for QA prioritization (blast radius, failure cost, etc).

    Returns:
        Dictionary matching INSIGHTS_SCHEMA (with optional qa_recommendations).
    """
    logger.info("Starting insight extraction pipeline")

    # Chunk the transcript
    chunks_list = chunk(transcript)
    logger.info(f"Transcript split into {len(chunks_list)} chunks")

    # Map phase: summarize each chunk
    summaries = map_phase(chunks_list, client, model)

    # Reduce phase: combine into final insights with QA recommendations
    insights = reduce_phase(summaries, client, model, repo_summary, agent_guidance)

    # Validate against schema
    try:
        validate(instance=insights, schema=INSIGHTS_SCHEMA)
        logger.info("Insights validated against schema")
        return insights
    except ValidationError as e:
        logger.warning(f"Validation error: {e.message}. Attempting repair...")

        # Repair attempt: request valid JSON
        messages = [
            {
                "role": "system",
                "content": "Return only valid JSON matching this schema: " + json.dumps(INSIGHTS_SCHEMA),
            },
            {
                "role": "user",
                "content": f"Fix this JSON to match the schema:\n\n{json.dumps(insights)}",
            },
        ]

        try:
            response = with_retry(
                client.chat.completions.create,
                model=model,
                max_tokens=2048,
                messages=messages,
            )

            if isinstance(response, str):
                result_text = response
            else:
                result_text = response.choices[0].message.content

            json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if json_match:
                repaired = json.loads(json_match.group())
                validate(instance=repaired, schema=INSIGHTS_SCHEMA)
                logger.info("Insights repaired and validated")
                return repaired
        except Exception as repair_e:
            logger.warning(f"Repair failed: {repair_e}. Using fallback object")

        # Fallback: return a valid but empty insights object
        fallback = {
            "summary": "Unable to extract structured insights from transcript.",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }

        validate(instance=fallback, schema=INSIGHTS_SCHEMA)
        return fallback
