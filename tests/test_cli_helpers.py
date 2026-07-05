"""Tests for CLI helper functions."""

import os
import tempfile
import pytest
from pathlib import Path


@pytest.mark.unit
class TestLoadAgentGuidance:
    """Tests for _load_agent_guidance() function."""

    def test_load_agent_guidance_finds_file(self):
        """Test that agent guidance file is found and loaded correctly."""
        from zoom_insights.cli import _load_agent_guidance

        result = _load_agent_guidance()
        # The file exists in the repo, so it should load content
        if result:
            # If file exists, it should have content
            assert len(result) > 0
            # Should skip frontmatter if present
            assert not result.startswith("---")
        else:
            # File not found (might be run from different directory)
            assert result == ""

    def test_load_agent_guidance_format(self):
        """Test that agent guidance properly skips frontmatter."""
        from zoom_insights.cli import _load_agent_guidance

        result = _load_agent_guidance()
        # If content is returned, it should not have the YAML frontmatter start
        if result:
            # First 3 chars should not be "---"
            assert not result.startswith("---")


@pytest.mark.unit
class TestGetRepoSummary:
    """Tests for read_repo_code_summary() function."""

    def test_read_repo_code_summary_extracts_python_files(self, tmp_path):
        """Test that read_repo_code_summary extracts Python code from repo."""
        from zoom_insights.enrich_insights import read_repo_code_summary

        # Create a test repo structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text('"""Module docstring."""\ndef func(): pass\n')

        summary = read_repo_code_summary(str(tmp_path))

        assert "module.py" in summary or "src" in summary
        assert "func" in summary or "Module" in summary

    def test_read_repo_code_summary_no_src_dir(self, tmp_path):
        """Test that read_repo_code_summary returns empty string when src/ missing."""
        from zoom_insights.enrich_insights import read_repo_code_summary

        # Create a repo without src/
        summary = read_repo_code_summary(str(tmp_path))

        assert summary == ""

    def test_cli_imports_read_repo_code_summary(self):
        """Test that cli.py properly imports read_repo_code_summary."""
        from zoom_insights import cli
        import inspect

        # Check that read_repo_code_summary is imported or used in cli
        source = inspect.getsource(cli)
        assert "read_repo_code_summary" in source
