"""Tests for insights enrichment with repository-aware QA recommendations."""

import json
import pytest
from zoom_insights.enrich_insights import (
    enrich_insights_with_repo_context,
    read_repo_code_summary,
)


def _make_groq_response(mocker, qa_recommendations: dict):
    """Build a mock Groq chat completion response."""
    mock_response = mocker.MagicMock()
    mock_response.choices[0].message.content = json.dumps(qa_recommendations)
    return mock_response


@pytest.mark.unit
class TestEnrichInsights:
    """Tests for enrichment functionality."""

    def test_enrich_happy_path(self, mocker, sample_insights, tmp_path):
        """Test successful enrichment with repository context."""
        repo_path = tmp_path / "test_repo"
        (repo_path / "src").mkdir(parents=True)
        (repo_path / "src" / "test.py").write_text(
            '"""Module."""\ndef sample_function(): pass\nclass SampleClass: pass\n'
        )

        qa_recommendations = {
            "test_scenarios": ["Test scenario 1", "Test scenario 2"],
            "features_to_add": ["Feature 1"],
            "edge_cases_to_cover": ["Edge case 1"],
        }

        mock_client = mocker.MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(
            mocker, qa_recommendations
        )
        mocker.patch("zoom_insights.enrich_insights.Groq", return_value=mock_client)

        result = enrich_insights_with_repo_context(
            sample_insights, str(repo_path), "test-api-key", model="mixtral-8x7b-32768"
        )

        assert "qa_recommendations" in result
        assert (
            result["qa_recommendations"]["test_scenarios"]
            == ["Test scenario 1", "Test scenario 2"]
        )
        assert all(k in result for k in ["summary", "key_points", "decisions", "action_items"])

    def test_enrich_missing_keys(self, tmp_path):
        """Test that enrichment raises ValueError when insights missing required keys."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        with pytest.raises(ValueError) as exc_info:
            enrich_insights_with_repo_context(
                {"summary": "Test"},  # missing key_points, decisions, action_items
                str(repo_path),
                "test-api-key",
                model="mixtral-8x7b-32768",
            )

        assert "missing required keys" in str(exc_info.value).lower()

    def test_enrich_invalid_repo_path(self, sample_insights):
        """Test that enrichment raises ValueError for non-existent repo path."""
        with pytest.raises(ValueError) as exc_info:
            enrich_insights_with_repo_context(
                sample_insights,
                "/nonexistent/repo/path",
                "test-api-key",
                model="mixtral-8x7b-32768",
            )

        assert "not found" in str(exc_info.value).lower()

    def test_enrich_bad_json_response(self, mocker, sample_insights, tmp_path):
        """Test that enrichment raises ValueError when LLM returns invalid JSON."""
        repo_path = tmp_path / "test_repo"
        (repo_path / "src").mkdir(parents=True)

        mock_client = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.choices[0].message.content = "NOT VALID JSON"
        mock_client.chat.completions.create.return_value = mock_response
        mocker.patch("zoom_insights.enrich_insights.Groq", return_value=mock_client)

        with pytest.raises(ValueError):
            enrich_insights_with_repo_context(
                sample_insights, str(repo_path), "test-api-key", model="mixtral-8x7b-32768"
            )

    def test_enrich_uses_config_model(self, mocker, sample_insights, tmp_path):
        """Test that enrichment uses the model parameter, not hardcoded 'mixtral-8x7b-32768'."""
        repo_path = tmp_path / "test_repo"
        (repo_path / "src").mkdir(parents=True)

        qa_recommendations = {
            "test_scenarios": [],
            "features_to_add": [],
            "edge_cases_to_cover": [],
        }

        mock_client = mocker.MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(
            mocker, qa_recommendations
        )
        mocker.patch("zoom_insights.enrich_insights.Groq", return_value=mock_client)

        # Call with a custom model
        enrich_insights_with_repo_context(
            sample_insights, str(repo_path), "test-api-key", model="custom-llm-model"
        )

        # Verify the custom model was used in the API call
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "custom-llm-model"

    def test_enrich_repo_context_included(self, mocker, sample_insights, tmp_path):
        """Test that repository code context is included in the enrichment prompt."""
        repo_path = tmp_path / "test_repo"
        (repo_path / "src").mkdir(parents=True)
        (repo_path / "src" / "distinctive_module.py").write_text(
            '"""Distinctive module."""\ndef distinctive_function(): pass\n'
        )

        qa_recommendations = {
            "test_scenarios": ["Test"],
            "features_to_add": [],
            "edge_cases_to_cover": [],
        }

        mock_client = mocker.MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(
            mocker, qa_recommendations
        )
        mocker.patch("zoom_insights.enrich_insights.Groq", return_value=mock_client)

        enrich_insights_with_repo_context(
            sample_insights, str(repo_path), "test-api-key", model="mixtral-8x7b-32768"
        )

        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        prompt = call_kwargs["messages"][0]["content"]
        assert "Repository" in prompt or "distinctive" in prompt or "src" in prompt

    def test_read_repo_code_summary_extracts_functions(self, tmp_path):
        """Test that read_repo_code_summary extracts function and class names."""
        repo_path = tmp_path / "test_repo"
        (repo_path / "src").mkdir(parents=True)
        (repo_path / "src" / "sample.py").write_text(
            '"""Test module."""\ndef func_one(): pass\ndef func_two(): pass\nclass TestClass: pass\n'
        )

        summary = read_repo_code_summary(str(repo_path))

        assert "sample.py" in summary or "src/" in summary
        assert "func_one" in summary or "func_two" in summary or "Functions:" in summary

    def test_read_repo_code_summary_missing_src(self, tmp_path):
        """Test that read_repo_code_summary returns empty string when src/ doesn't exist."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        summary = read_repo_code_summary(str(repo_path))

        assert summary == ""
