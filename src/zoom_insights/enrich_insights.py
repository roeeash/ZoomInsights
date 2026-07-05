"""Insights enrichment with repository-aware QA recommendations."""

import json
import logging
import os
import re
from pathlib import Path
from groq import Groq

logger = logging.getLogger(__name__)


def read_repo_code_summary(repo_path: str) -> str:
    """Read Python files from repo and extract imports, function signatures.

    Args:
        repo_path: Path to repository root

    Returns:
        String containing extracted code summaries
    """
    code_summary = []
    src_path = os.path.join(repo_path, "src")

    if not os.path.isdir(src_path):
        logger.warning(f"src directory not found at {src_path}")
        return ""

    # Find all Python files
    python_files = []
    for root, dirs, files in os.walk(src_path):
        for file in files:
            if file.endswith(".py"):
                python_files.append(os.path.join(root, file))

    if not python_files:
        logger.warning(f"No Python files found in {src_path}")
        return ""

    # Extract summaries from first N files (limit to avoid token explosion)
    max_files = 15
    for file_path in python_files[:max_files]:
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Extract docstring if present
            docstring_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
            docstring = docstring_match.group(1).strip() if docstring_match else ""

            # Extract function and class signatures
            functions = re.findall(r"^def\s+(\w+)\(.*?\).*?:", content, re.MULTILINE)
            classes = re.findall(r"^class\s+(\w+).*?:", content, re.MULTILINE)

            # Get imports
            imports = re.findall(r"^(?:from|import)\s+.*", content, re.MULTILINE)

            relative_path = os.path.relpath(file_path, repo_path)
            code_summary.append(f"\n=== {relative_path} ===")
            if docstring:
                code_summary.append(f"Module: {docstring[:200]}")
            if imports:
                code_summary.append(f"Imports: {', '.join(imports[:5])}")
            if classes:
                code_summary.append(f"Classes: {', '.join(classes)}")
            if functions:
                code_summary.append(f"Functions: {', '.join(functions[:8])}")

        except Exception as e:
            logger.debug(f"Error reading {file_path}: {e}")
            continue

    return "\n".join(code_summary)


def enrich_insights_with_repo_context(insights: dict, repo_path: str, api_key: str, model: str = "mixtral-8x7b-32768") -> dict:
    """Enrich meeting insights with repository-aware QA recommendations.

    Args:
        insights: Dictionary with keys from INSIGHTS_SCHEMA (summary, key_points, etc.)
        repo_path: Path to repository to scan for code context
        api_key: Groq API key
        model: Groq model to use for enrichment

    Returns:
        insights dict with qa_recommendations field added

    Raises:
        ValueError: if insights missing required keys or API call fails
    """
    # Validate insights has required keys
    required_keys = ["summary", "key_points", "decisions", "action_items"]
    missing = [k for k in required_keys if k not in insights]
    if missing:
        raise ValueError(f"Insights missing required keys: {missing}")

    # Validate repo path
    if not os.path.isdir(repo_path):
        raise ValueError(f"Repository path not found: {repo_path}")

    # Read repository code summary
    repo_summary = read_repo_code_summary(repo_path)
    if not repo_summary:
        logger.warning("Could not extract code from repository")

    # Build Groq prompt
    prompt = f"""You are a QA engineer reviewing meeting insights for a software project.

Meeting Summary:
{insights.get("summary", "")}

Key Points:
{json.dumps(insights.get("key_points", []), indent=2)}

Decisions Made:
{json.dumps(insights.get("decisions", []), indent=2)}

Action Items:
{json.dumps(insights.get("action_items", []), indent=2)}

Repository Code Structure:
{repo_summary if repo_summary else "(No code files found or unable to read repository)"}

Based on this meeting context and the codebase structure, provide QA testing recommendations as a JSON object with:
- test_scenarios: Array of test scenarios to validate meeting decisions and action items
- features_to_add: Array of potential features or enhancements discussed
- edge_cases_to_cover: Array of edge cases and error conditions to test

Return ONLY valid JSON, no other text."""

    # Call Groq API
    try:
        client = Groq(api_key=api_key)

        message = client.chat.completions.create(
            model=model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        # Extract response text
        response_text = message.choices[0].message.content

        # Parse JSON from response
        try:
            qa_recommendations = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response text
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                qa_recommendations = json.loads(json_match.group())
            else:
                raise ValueError("No valid JSON found in Groq API response")

        # Validate structure
        if not isinstance(qa_recommendations, dict):
            raise ValueError("Groq response is not a JSON object")

        # Add to insights
        enriched = insights.copy()
        enriched["qa_recommendations"] = qa_recommendations

        logger.info("Insights enriched with QA recommendations")
        return enriched

    except Exception as e:
        logger.error(f"Error calling Groq API: {e}")
        raise
