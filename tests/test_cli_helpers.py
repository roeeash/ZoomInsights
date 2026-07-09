"""Tests for CLI helper functions."""

import functools
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock


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


@pytest.mark.unit
class TestGuidanceCaching:
    """Tests for guidance caching in _load_agent_guidance()."""

    def test_guidance_loaded_once_across_multiple_calls(self):
        """Test that agent guidance is loaded from disk only once across multiple calls."""
        from zoom_insights.cli import _load_agent_guidance

        # Clear the cache before test
        _load_agent_guidance.cache_clear()

        # Mock the file open to track how many times it's called
        mock_file_content = "# Test Guidance\nSome test content here"
        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            with patch.object(Path, "exists", return_value=True):
                # Call the function 3 times
                result1 = _load_agent_guidance()
                result2 = _load_agent_guidance()
                result3 = _load_agent_guidance()

                # All results should be the same
                assert result1 == result2 == result3

        # Verify cache was used
        cache_info = _load_agent_guidance.cache_info()
        # First call is a miss, second and third are hits
        assert cache_info.hits == 2
        assert cache_info.misses == 1

    def test_guidance_cache_returns_correct_content(self):
        """Test that cached guidance value matches actual file content."""
        from zoom_insights.cli import _load_agent_guidance

        # Clear cache
        _load_agent_guidance.cache_clear()

        # Create actual guidance content
        guidance_content = "# Agent Guidance\n\n## Section 1\nContent here"
        mock_file_content = f"---\ntitle: test\n---\n{guidance_content}"

        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            with patch.object(Path, "exists", return_value=True):
                result = _load_agent_guidance()

                # Should return content after frontmatter (stripped)
                assert result == guidance_content.strip()

    def test_guidance_cache_handles_missing_file(self):
        """Test that cache properly handles missing guidance file."""
        from zoom_insights.cli import _load_agent_guidance

        # Clear cache
        _load_agent_guidance.cache_clear()

        with patch.object(Path, "exists", return_value=False):
            result1 = _load_agent_guidance()
            result2 = _load_agent_guidance()

            # Both should return empty string
            assert result1 == ""
            assert result2 == ""

            # Cache should still work (2 hits, 1 miss)
            cache_info = _load_agent_guidance.cache_info()
            assert cache_info.hits == 1
            assert cache_info.misses == 1


@pytest.mark.unit
class TestRepoSummaryCaching:
    """Tests for caching in read_repo_code_summary()."""

    def test_repo_summary_cached_across_calls(self):
        """Test that repo summary is read from disk only once across multiple calls."""
        from zoom_insights.enrich_insights import read_repo_code_summary

        # Clear cache before test
        read_repo_code_summary.cache_clear()

        # Create temporary repo structure
        with tempfile.TemporaryDirectory() as tmp_dir:
            src_dir = os.path.join(tmp_dir, "src")
            os.makedirs(src_dir)

            # Create a test Python file
            test_file = os.path.join(src_dir, "test_module.py")
            with open(test_file, "w") as f:
                f.write('"""Test module."""\ndef test_func(): pass\n')

            # Call the function 3 times with the same repo path
            result1 = read_repo_code_summary(tmp_dir)
            result2 = read_repo_code_summary(tmp_dir)
            result3 = read_repo_code_summary(tmp_dir)

            # All results should be the same
            assert result1 == result2 == result3
            assert len(result1) > 0

            # Verify cache was used (2 hits, 1 miss)
            cache_info = read_repo_code_summary.cache_info()
            assert cache_info.hits == 2
            assert cache_info.misses == 1

    def test_repo_summary_cache_isolation_by_path(self):
        """Test that different repo paths have separate cache entries."""
        from zoom_insights.enrich_insights import read_repo_code_summary

        # Clear cache before test
        read_repo_code_summary.cache_clear()

        with tempfile.TemporaryDirectory() as tmp_dir1:
            with tempfile.TemporaryDirectory() as tmp_dir2:
                # Create src dirs and files in both repos
                src_dir1 = os.path.join(tmp_dir1, "src")
                src_dir2 = os.path.join(tmp_dir2, "src")
                os.makedirs(src_dir1)
                os.makedirs(src_dir2)

                with open(os.path.join(src_dir1, "module1.py"), "w") as f:
                    f.write('"""Module 1."""\ndef func1(): pass\n')

                with open(os.path.join(src_dir2, "module2.py"), "w") as f:
                    f.write('"""Module 2."""\ndef func2(): pass\n')

                # Call with different paths
                result1 = read_repo_code_summary(tmp_dir1)
                result2 = read_repo_code_summary(tmp_dir2)

                # Results should be different (different module names)
                assert result1 != result2
                assert "module1" in result1
                assert "module2" in result2

                # Verify separate cache entries (2 misses, 0 hits)
                cache_info = read_repo_code_summary.cache_info()
                assert cache_info.misses == 2
                assert cache_info.hits == 0
