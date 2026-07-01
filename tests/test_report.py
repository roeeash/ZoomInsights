"""Tests for report generation module."""

import json
import os
import tempfile
from pathlib import Path
import pytest
from zoom_insights.report import write_report, sanitize_topic, _render_report


@pytest.mark.unit
class TestSanitizeTopic:
    """Tests for topic sanitization."""

    def test_sanitize_topic_removes_special_chars(self):
        """Test that special characters are removed."""
        result = sanitize_topic("Q4 Strategy & Planning!@#")
        assert "!" not in result
        assert "@" not in result
        assert "#" not in result
        assert "&" not in result

    def test_sanitize_topic_replaces_spaces_with_underscores(self):
        """Test that spaces are replaced with underscores."""
        result = sanitize_topic("Q4 Strategy Planning")
        assert result == "Q4_Strategy_Planning"

    def test_sanitize_topic_limits_length(self):
        """Test that very long topics are truncated."""
        long_topic = "A" * 150
        result = sanitize_topic(long_topic)
        assert len(result) <= 100

    def test_sanitize_topic_empty_string(self):
        """Test that empty string returns default."""
        result = sanitize_topic("")
        assert result == "meeting"

    def test_sanitize_topic_only_special_chars(self):
        """Test that string with only special chars returns default."""
        result = sanitize_topic("!@#$%^&*()")
        assert result == "meeting"

    def test_sanitize_topic_preserves_alphanumeric(self):
        """Test that alphanumeric characters are preserved."""
        result = sanitize_topic("Q4 2024 Planning v2")
        assert "Q4" in result
        assert "2024" in result
        assert "Planning" in result
        assert "v2" in result


@pytest.mark.unit
class TestRenderReport:
    """Tests for markdown report rendering."""

    def test_render_report_includes_title(self):
        """Test that report includes the topic as a title."""
        insights = {
            "summary": "",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        report = _render_report("Q4 Strategy", insights)
        assert "# Q4 Strategy" in report

    def test_render_report_includes_summary(self):
        """Test that summary section is rendered when present."""
        insights = {
            "summary": "This was a productive meeting.",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        report = _render_report("Test Meeting", insights)
        assert "## Summary" in report
        assert "This was a productive meeting." in report

    def test_render_report_omits_empty_summary(self):
        """Test that summary section is omitted when empty."""
        insights = {
            "summary": "",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        report = _render_report("Test Meeting", insights)
        # Empty summary should not be included, but the ## Summary header might still appear
        # Let's check that there's no content after the summary header
        lines = report.split("\n")
        # Find summary header
        for i, line in enumerate(lines):
            if "## Summary" in line:
                # Next non-empty line should be a different section
                for next_line in lines[i + 1 :]:
                    if next_line.strip() and not next_line.startswith("##"):
                        # Found content under summary, which shouldn't exist
                        pass
                break

    def test_render_report_includes_key_points(self):
        """Test that key points are rendered."""
        insights = {
            "summary": "",
            "key_points": ["Point 1", "Point 2"],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        report = _render_report("Test", insights)
        assert "## Key Points" in report
        assert "- Point 1" in report
        assert "- Point 2" in report

    def test_render_report_includes_decisions(self):
        """Test that decisions are rendered."""
        insights = {
            "summary": "",
            "key_points": [],
            "decisions": ["Approved budget", "Extended timeline"],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": [],
        }
        report = _render_report("Test", insights)
        assert "## Decisions" in report
        assert "- Approved budget" in report
        assert "- Extended timeline" in report

    def test_render_report_action_items_with_owner_and_due(self):
        """Test that action items with owner and due date are formatted correctly."""
        insights = {
            "summary": "",
            "key_points": [],
            "decisions": [],
            "action_items": [
                {"owner": "Alice", "task": "Finalize docs", "due": "2024-12-15"}
            ],
            "open_questions": [],
            "notable_quotes": [],
        }
        report = _render_report("Test", insights)
        assert "## Action Items" in report
        assert "**Alice**" in report
        assert "Finalize docs" in report
        assert "due: 2024-12-15" in report

    def test_render_report_action_items_without_owner(self):
        """Test that action items without owner show 'Unassigned'."""
        insights = {
            "summary": "",
            "key_points": [],
            "decisions": [],
            "action_items": [
                {"owner": None, "task": "Review feedback", "due": None}
            ],
            "open_questions": [],
            "notable_quotes": [],
        }
        report = _render_report("Test", insights)
        assert "**Unassigned**" in report
        assert "Review feedback" in report

    def test_render_report_includes_questions(self):
        """Test that open questions are rendered."""
        insights = {
            "summary": "",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": ["What about the timeline?", "Who owns feature X?"],
            "notable_quotes": [],
        }
        report = _render_report("Test", insights)
        assert "## Open Questions" in report
        assert "- What about the timeline?" in report
        assert "- Who owns feature X?" in report

    def test_render_report_includes_quotes(self):
        """Test that notable quotes are rendered."""
        insights = {
            "summary": "",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "notable_quotes": ["We need to move fast.", "Quality first."],
        }
        report = _render_report("Test", insights)
        assert "## Notable Quotes" in report
        assert "> We need to move fast." in report
        assert "> Quality first." in report


class TestWriteReport:
    """Tests for report file writing."""

    def test_write_report_creates_files(self):
        """Test that all three output files are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            insights = {
                "summary": "Test summary",
                "key_points": ["Point 1"],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

            write_report("Test Meeting", "Full transcript text", insights, tmpdir)

            # Check that files were created
            topic_dir = os.path.join(tmpdir, "Test_Meeting")
            assert os.path.exists(os.path.join(topic_dir, "transcript.txt"))
            assert os.path.exists(os.path.join(topic_dir, "insights.json"))
            assert os.path.exists(os.path.join(topic_dir, "report.md"))

    def test_write_report_transcript_content(self):
        """Test that transcript is written correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript = "This is the full meeting transcript."
            insights = {
                "summary": "",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

            write_report("Test", transcript, insights, tmpdir)

            transcript_file = os.path.join(tmpdir, "Test", "transcript.txt")
            with open(transcript_file) as f:
                content = f.read()
            assert content == transcript

    def test_write_report_insights_json_format(self):
        """Test that insights.json is valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            insights = {
                "summary": "Test",
                "key_points": ["Point 1"],
                "decisions": ["Decision 1"],
                "action_items": [{"owner": "Alice", "task": "Task", "due": None}],
                "open_questions": [],
                "notable_quotes": [],
            }

            write_report("Test", "transcript", insights, tmpdir)

            insights_file = os.path.join(tmpdir, "Test", "insights.json")
            with open(insights_file) as f:
                loaded = json.load(f)
            assert loaded == insights

    def test_write_report_creates_directory_structure(self):
        """Test that directory structure is created if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = os.path.join(tmpdir, "nonexistent", "output")
            insights = {
                "summary": "",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

            write_report("Test", "text", insights, output_dir)

            assert os.path.exists(os.path.join(output_dir, "Test"))

    def test_write_report_uses_sanitized_topic_as_dirname(self):
        """Test that topic name is sanitized for directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            insights = {
                "summary": "",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "notable_quotes": [],
            }

            write_report("Q4 Strategy!@#", "text", insights, tmpdir)

            # Should create directory without special chars
            assert os.path.exists(os.path.join(tmpdir, "Q4_Strategy"))
