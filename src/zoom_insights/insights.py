"""Summary and structured insights extraction using map-reduce pattern."""

import json
import logging
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


def map_phase(chunks: list[str], client) -> list[str]:
    """Summarize each chunk via LLM into tight bullets (map phase)."""
    summaries = []

    for i, chunk_text in enumerate(chunks):
        logger.info(f"Summarizing chunk {i + 1}/{len(chunks)}")

        messages = [
            {
                "role": "system",
                "content": """You are a meeting analyst. Analyze this transcript chunk and extract:
- Key discussion points (what was talked about)
- Decisions made (explicit choices or commitments)
- Action items (implied or explicit tasks that need to happen - NOT verbatim phrases, but deduced from context)
- Questions raised (unresolved issues or concerns)

For action items specifically: Look for implied responsibilities like "we need to", "someone should", "by end of week", "follow up on", etc. Deduce WHO should do it and WHAT concretely needs to happen. Do NOT just copy phrases from the transcript.

Be faithful to the original text but interpret and structure information meaningfully. Do not fabricate information.""",
            },
            {
                "role": "user",
                "content": f"Analyze this meeting chunk and extract meaningful insights:\n\n{chunk_text}",
            },
        ]

        try:
            def create_message():
                return client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    max_tokens=1024,
                    messages=messages,
                )

            response = with_retry(create_message)

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


def reduce_phase(summaries: list[str], client) -> dict:
    """Combine summaries into the final insights JSON object (reduce phase)."""
    combined_text = "\n\n".join(summaries)

    logger.info("Reducing summaries to final insights")

    messages = [
        {
            "role": "system",
            "content": """You are a meeting analyst. Produce a JSON object with exactly these keys:
- summary: 3-5 sentence overview of what the meeting was about
- key_points: list of important discussion points (concise, meaningful interpretations - NOT verbatim)
- decisions: list of commitments or decisions made explicitly
- action_items: list of objects with owner (string|null), task (string), due (string|null)
  * CRITICAL: Action items are things that need to HAPPEN as a result of this meeting
  * Deduce implied tasks from context ("we should follow up on X", "Y needs approval", "Z must be tested")
  * Task should be specific and actionable (e.g., "Review Q4 budget proposal" not just "Budget")
  * Do NOT copy verbatim phrases; interpret and structure them as concrete next steps
  * If owner is not mentioned, use null (don't guess)
  * If no clear due date, use null (don't make one up)
- open_questions: list of unresolved issues or concerns from discussion
- notable_quotes: list of important direct quotes that capture key moments

Do not invent information that wasn't discussed. Use null for missing data. Every action item must be traceable back to the meeting content.""",
        },
        {
            "role": "user",
            "content": f"Create structured insights JSON from these meeting summaries. Focus on MEANINGFUL, DEDUCED action items (not verbatim copies):\n\n{combined_text}",
        },
    ]

    try:
        def create_reduce_message():
            return client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=2048,
                messages=messages,
            )

        response = with_retry(create_reduce_message)

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
            import re
            json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if json_match:
                insights = json.loads(json_match.group())
            else:
                raise ValueError("No JSON found in LLM response")

        return insights

    except Exception as e:
        logger.error(f"Error in reduce phase: {e}")
        raise


def summarize(transcript: str, client) -> dict:
    """Execute the full map-reduce pipeline and return schema-valid insights.

    Args:
        transcript: Full meeting transcript text.
        client: Groq API client.

    Returns:
        Dictionary matching INSIGHTS_SCHEMA.
    """
    logger.info("Starting insight extraction pipeline")

    # Chunk the transcript
    chunks_list = chunk(transcript)
    logger.info(f"Transcript split into {len(chunks_list)} chunks")

    # Map phase: summarize each chunk
    summaries = map_phase(chunks_list, client)

    # Reduce phase: combine into final insights
    insights = reduce_phase(summaries, client)

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
            def repair_message():
                return client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    max_tokens=2048,
                    messages=messages,
                )

            response = with_retry(repair_message)

            if isinstance(response, str):
                result_text = response
            else:
                result_text = response.choices[0].message.content

            import re
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
