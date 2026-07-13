"""Insights enrichment with repository-aware QA recommendations."""

import functools
import json
import logging
import os
import re
from pathlib import Path
from groq import Groq

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
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
    action_items = insights.get("action_items", [])
    num_items = len(action_items)

    prompt = f"""You are a QA engineer reviewing meeting insights for a software project.

Meeting Summary:
{insights.get("summary", "")}

Key Points:
{json.dumps(insights.get("key_points", []), indent=2)}

Decisions Made:
{json.dumps(insights.get("decisions", []), indent=2)}

Action Items:
{json.dumps(action_items, indent=2)}

Repository Code Structure:
{repo_summary if repo_summary else "(No code files found or unable to read repository)"}

Based on this meeting context and the codebase structure, provide QA testing recommendations for EACH action item.

CRITICAL: Return EXACTLY {num_items} JSON objects in an array, one per action item, in the same order.
Each object must have:
- test_scenarios: Array of test scenarios specific to THIS action item
- features_to_add: Array of features/enhancements relevant to THIS action item
- edge_cases_to_cover: Array of edge cases specific to THIS action item
- technologies: Array of technologies/languages relevant to THIS action item
- implementation_steps: Array of implementation steps for THIS action item

Return ONLY a valid JSON array with {num_items} objects, no other text.
Example: [{{"test_scenarios": [...], "features_to_add": [...], ...}}, {{"test_scenarios": [...], ...}}]"""

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
            qa_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response text (look for array first, then object)
            json_match = re.search(r"\[.*\]|\{.*\}", response_text, re.DOTALL)
            if json_match:
                qa_data = json.loads(json_match.group())
            else:
                raise ValueError("No valid JSON found in Groq API response")

        # Validate and normalize structure
        if isinstance(qa_data, list):
            # New format: array of per-action-item QA data
            action_item_qa = qa_data
            # Ensure we have the right number of items
            num_items = len(insights.get("action_items", []))
            if len(action_item_qa) < num_items:
                # Pad with empty structures if LLM returned fewer items
                logger.warning(f"LLM returned {len(action_item_qa)} items but expected {num_items}, padding with empty entries")
                for _ in range(num_items - len(action_item_qa)):
                    action_item_qa.append({
                        "test_scenarios": [],
                        "features_to_add": [],
                        "edge_cases_to_cover": [],
                        "technologies": [],
                        "implementation_steps": []
                    })
            elif len(action_item_qa) > num_items:
                # Truncate if LLM returned more items
                action_item_qa = action_item_qa[:num_items]
        elif isinstance(qa_data, dict):
            # Old format: single dict (for backward compatibility)
            # Convert to array with one copy per action item
            num_items = len(insights.get("action_items", []))
            action_item_qa = [qa_data.copy() for _ in range(num_items)]
        else:
            raise ValueError(f"Invalid response format: expected list or dict, got {type(qa_data)}")

        # Add to insights
        enriched = insights.copy()
        enriched["action_item_qa"] = action_item_qa

        logger.info(f"Insights enriched with per-action-item QA data ({len(action_item_qa)} items)")
        return enriched

    except Exception as e:
        logger.error(f"Error calling Groq API: {e}")
        raise
