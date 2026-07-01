"""Tests for insights extraction module."""

import json
import pytest
from zoom_insights.insights import (
    chunk,
    map_phase,
    reduce_phase,
    summarize,
    INSIGHTS_SCHEMA,
)
from jsonschema import validate, ValidationError


@pytest.mark.unit
class TestChunk:
    """Tests for text chunking function."""

    def test_chunk_small_text_single_chunk(self):
        """Test that small text is returned as single chunk."""
        text = "Hello world"
        chunks = chunk(text, size=100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_large_text_multiple_chunks(self):
        """Test that large text is split into multiple chunks."""
        text = " ".join(["word"] * 1000)
        chunks = chunk(text, size=100)
        assert len(chunks) > 1
        # Verify all chunks fit under size limit
        for chunk_text in chunks:
            assert len(chunk_text) <= 130  # Some buffer for word boundaries

    def test_chunk_preserves_words(self):
        """Test that chunking preserves complete words (no splitting mid-word)."""
        text = "This is a test of the chunking algorithm"
        chunks = chunk(text, size=20)
        # Join chunks back and verify they match
        rejoined = " ".join(chunks)
        assert all(word in rejoined for word in text.split())

    def test_chunk_empty_string(self):
        """Test chunking an empty string."""
        chunks = chunk("", size=100)
        assert chunks == []

    def test_chunk_custom_size(self):
        """Test chunking with custom size parameter."""
        text = " ".join(["word"] * 50)
        chunks_small = chunk(text, size=50)
        chunks_large = chunk(text, size=200)
        assert len(chunks_small) > len(chunks_large)


@pytest.mark.unit
class TestMapPhase:
    """Tests for map phase (per-chunk summarization)."""

    @pytest.mark.parametrize("num_chunks", [1, 3, 5], ids=["single", "three", "five"])
    def test_map_phase_multiple_chunks(self, mocker, num_chunks):
        """Test map phase with various numbers of chunks."""
        mock_client = mocker.MagicMock()
        # Create responses for each chunk
        responses = [
            mocker.MagicMock(choices=[mocker.MagicMock(message=mocker.MagicMock(content=f"Summary {i+1}"))
            ]) for i in range(num_chunks)
        ]
        mock_client.chat.completions.create.side_effect = responses

        chunks = [f"Chunk {i+1}" for i in range(num_chunks)]
        summaries = map_phase(chunks, mock_client)

        assert len(summaries) == num_chunks
        assert mock_client.chat.completions.create.call_count == num_chunks

    def test_map_phase_uses_correct_model(self, mocker):
        """Test that map phase uses the correct model."""
        mock_client = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(content="Summary"))]
        mock_client.chat.completions.create.return_value = mock_response

        chunks = ["Test chunk"]
        map_phase(chunks, mock_client)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "llama-3.3-70b-versatile"

    def test_map_phase_single_chunk(self, mocker):
        """Test map phase with a single chunk."""
        mock_client = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(content="Summary of chunk 1"))]
        mock_client.chat.completions.create.return_value = mock_response

        chunks = ["This is a meeting chunk."]
        summaries = map_phase(chunks, mock_client)

        assert len(summaries) == 1
        assert "Summary of chunk 1" in summaries[0]


@pytest.mark.unit
class TestReducePhase:
    """Tests for reduce phase (combining summaries to insights)."""

    def test_reduce_phase_returns_valid_schema(self, mocker):
        """Test that reduce phase returns a schema-valid insights object."""
        mock_client = mocker.MagicMock()

        valid_insights = {
            "summary": "Meeting discussed Q4 strategy.",
            "key_points": ["Strategy defined", "Timeline set"],
            "decisions": ["Approved Q4 budget"],
            "action_items": [
                {"owner": "Alice", "task": "Finalize docs", "due": "2024-12-15"},
                {"owner": None, "task": "Review feedback", "due": None},
            ],
            "open_questions": ["What about the timeline?"],
            "notable_quotes": ["We need to move fast."],
        }

        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(content=json.dumps(valid_insights)))]
        mock_client.chat.completions.create.return_value = mock_response

        summaries = ["Summary 1", "Summary 2"]
        insights = reduce_phase(summaries, mock_client)

        # Verify schema compliance
        validate(instance=insights, schema=INSIGHTS_SCHEMA)
        assert insights["summary"] == "Meeting discussed Q4 strategy."

    def test_reduce_phase_handles_string_response(self, mocker):
        """Test reduce phase when LLM returns a string instead of object."""
        mock_client = mocker.MagicMock()
        valid_insights = {
            "summary": "Test summary",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        mock_client.chat.completions.create.return_value = json.dumps(valid_insights)

        summaries = ["Test"]
        insights = reduce_phase(summaries, mock_client)

        assert insights["summary"] == "Test summary"


@pytest.mark.unit
class TestSummarize:
    """Tests for the full summarization pipeline."""

    def test_summarize_valid_transcript(self):
        """Test summarizing a valid transcript produces schema-valid output."""
        from unittest.mock import MagicMock
        mock_client = MagicMock()

        # Mock map phase responses (1 chunk in this case)
        map_response = MagicMock()
        map_response.choices = [MagicMock(message=MagicMock(content="Chunk 1 summary"))]

        # Mock reduce phase response
        valid_insights = {
            "summary": "Meeting summary",
            "key_points": ["Point 1"],
            "decisions": ["Decision 1"],
            "action_items": [{"owner": "Alice", "task": "Task", "due": None}],
            "open_questions": ["Question 1"],
            "notable_quotes": ["Quote 1"],
        }
        reduce_response = MagicMock()
        reduce_response.choices = [MagicMock(message=MagicMock(content=json.dumps(valid_insights)))]

        mock_client.chat.completions.create.side_effect = [
            map_response,
            reduce_response,
        ]

        transcript = " ".join(["word"] * 500)  # Single chunk
        insights = summarize(transcript, mock_client)

        validate(instance=insights, schema=INSIGHTS_SCHEMA)
        assert insights["summary"] == "Meeting summary"

    def test_summarize_with_schema_validation_failure_uses_fallback(self):
        """Test that invalid LLM output falls back to safe object."""
        from unittest.mock import MagicMock
        mock_client = MagicMock()

        # Mock map phase
        map_response = MagicMock()
        map_response.choices = [MagicMock(message=MagicMock(content="Summary"))]

        # Mock reduce phase with invalid JSON
        reduce_response = MagicMock()
        reduce_response.choices = [MagicMock(message=MagicMock(content='{"invalid": "object"}'))]

        # Mock repair attempt (also fails)
        repair_response = MagicMock()
        repair_response.choices = [MagicMock(message=MagicMock(content="Not JSON at all"))]

        mock_client.chat.completions.create.side_effect = [
            map_response,
            reduce_response,
            repair_response,
        ]

        transcript = " ".join(["word"] * 500)
        insights = summarize(transcript, mock_client)

        # Should return fallback (valid but empty)
        validate(instance=insights, schema=INSIGHTS_SCHEMA)
        assert insights["summary"] == "Unable to extract structured insights from transcript."
        assert insights["key_points"] == []

    def test_summarize_action_items_never_fabricate(self):
        """Test that action items use null for missing owners/dates."""
        from unittest.mock import MagicMock
        mock_client = MagicMock()

        map_response = MagicMock()
        map_response.choices = [MagicMock(message=MagicMock(content="Summary"))]

        valid_insights = {
            "summary": "Test",
            "key_points": [],
            "decisions": [],
            "action_items": [
                {"owner": None, "task": "Undefined owner task", "due": None},
                {"owner": "Bob", "task": "Task with owner", "due": "2025-01-01"},
            ],
            "open_questions": [],
            "notable_quotes": [],
        }
        reduce_response = MagicMock()
        reduce_response.choices = [MagicMock(message=MagicMock(content=json.dumps(valid_insights)))]

        mock_client.chat.completions.create.side_effect = [
            map_response,
            reduce_response,
        ]

        transcript = " ".join(["word"] * 500)
        insights = summarize(transcript, mock_client)

        # Verify owners are null, not fabricated
        assert insights["action_items"][0]["owner"] is None
        assert insights["action_items"][1]["owner"] == "Bob"

    def test_summarize_empty_arrays_allowed(self):
        """Test that empty arrays in insights are valid."""
        from unittest.mock import MagicMock
        mock_client = MagicMock()

        map_response = MagicMock()
        map_response.choices = [MagicMock(message=MagicMock(content="Summary"))]

        insights_empty_arrays = {
            "summary": "No action items",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        reduce_response = MagicMock()
        reduce_response.choices = [MagicMock(message=MagicMock(content=json.dumps(insights_empty_arrays)))]

        mock_client.chat.completions.create.side_effect = [
            map_response,
            reduce_response,
        ]

        transcript = " ".join(["word"] * 500)
        insights = summarize(transcript, mock_client)

        validate(instance=insights, schema=INSIGHTS_SCHEMA)
        assert all(isinstance(arr, list) and len(arr) == 0 for arr in [
            insights["key_points"],
            insights["decisions"],
            insights["action_items"],
            insights["open_questions"],
            insights["notable_quotes"],
        ])
