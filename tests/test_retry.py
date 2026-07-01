"""Tests for retry logic."""

import time
import pytest
from zoom_insights.retry import with_retry


@pytest.mark.unit
class TestWithRetry:
    """Tests for the with_retry function."""

    def test_with_retry_succeeds_on_first_call(self, mocker):
        """Test that successful call returns immediately without retry."""
        mock_fn = mocker.MagicMock(return_value="success")

        result = with_retry(mock_fn)

        assert result == "success"
        mock_fn.assert_called_once()

    def test_with_retry_passes_args(self, mocker):
        """Test that args are passed through to the function."""
        mock_fn = mocker.MagicMock(return_value="result")

        result = with_retry(mock_fn, "arg1", "arg2")

        mock_fn.assert_called_once_with("arg1", "arg2")
        assert result == "result"

    def test_with_retry_passes_kwargs(self, mocker):
        """Test that kwargs are passed through to the function."""
        mock_fn = mocker.MagicMock(return_value="result")

        result = with_retry(mock_fn, key1="value1", key2="value2")

        mock_fn.assert_called_once_with(key1="value1", key2="value2")
        assert result == "result"

    def test_with_retry_passes_args_and_kwargs(self, mocker):
        """Test that both args and kwargs are passed through."""
        mock_fn = mocker.MagicMock(return_value="result")

        result = with_retry(mock_fn, "arg1", key1="value1")

        mock_fn.assert_called_once_with("arg1", key1="value1")
        assert result == "result"

    def test_with_retry_retries_on_429(self, mocker):
        """Test that retries occur on 429 rate limit error."""
        mock_fn = mocker.MagicMock()
        mock_fn.side_effect = [
            Exception("429 Too Many Requests"),
            "success",
        ]

        mocker.patch("time.sleep")
        result = with_retry(mock_fn, tries=3)

        assert result == "success"
        assert mock_fn.call_count == 2

    def test_with_retry_retries_on_rate_error(self, mocker):
        """Test that retries occur on 'rate' errors."""
        mock_fn = mocker.MagicMock()
        mock_fn.side_effect = [
            Exception("Rate limit exceeded"),
            "success",
        ]

        mocker.patch("time.sleep")
        result = with_retry(mock_fn, tries=3)

        assert result == "success"
        assert mock_fn.call_count == 2

    def test_with_retry_retries_on_timeout(self, mocker):
        """Test that retries occur on timeout errors."""
        mock_fn = mocker.MagicMock()
        mock_fn.side_effect = [
            Exception("Connection timeout"),
            "success",
        ]

        mocker.patch("time.sleep")
        result = with_retry(mock_fn, tries=3)

        assert result == "success"
        assert mock_fn.call_count == 2

    def test_with_retry_does_not_retry_on_non_retryable_error(self, mocker):
        """Test that non-retryable errors are raised immediately."""
        mock_fn = mocker.MagicMock()
        mock_fn.side_effect = ValueError("Bad input")

        with pytest.raises(ValueError):
            with_retry(mock_fn, tries=3)

        # Should only be called once
        assert mock_fn.call_count == 1

    def test_with_retry_exhausts_retries(self, mocker):
        """Test that all retries are exhausted before giving up."""
        mock_fn = mocker.MagicMock()
        mock_fn.side_effect = Exception("429 Rate limit")

        mocker.patch("time.sleep")
        with pytest.raises(Exception):
            with_retry(mock_fn, tries=4)

        # Should be called tries times
        assert mock_fn.call_count == 4

    def test_with_retry_exponential_backoff(self, mocker):
        """Test that delay increases exponentially."""
        mock_fn = mocker.MagicMock()
        mock_fn.side_effect = Exception("429")

        mock_sleep = mocker.patch("time.sleep")
        try:
            with_retry(mock_fn, tries=4, base_delay=2)
        except Exception:
            pass

        # Delays should be 2, 4, 8
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [2, 4, 8]

    def test_with_retry_backoff_capped_at_60(self, mocker):
        """Test that backoff delay is capped at 60 seconds."""
        mock_fn = mocker.MagicMock()
        mock_fn.side_effect = Exception("429")

        mock_sleep = mocker.patch("time.sleep")
        try:
            with_retry(mock_fn, tries=6, base_delay=20)
        except Exception:
            pass

        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        # Delays: 20, 40, 60, 60, 60
        assert sleep_calls[-1] == 60
        assert all(d <= 60 for d in sleep_calls)

    def test_with_retry_custom_tries(self, mocker):
        """Test that custom tries parameter is respected."""
        mock_fn = mocker.MagicMock()
        mock_fn.side_effect = Exception("429")

        mocker.patch("time.sleep")
        with pytest.raises(Exception):
            with_retry(mock_fn, tries=2)

        assert mock_fn.call_count == 2

    def test_with_retry_custom_base_delay(self, mocker):
        """Test that custom base_delay parameter is used."""
        mock_fn = mocker.MagicMock()
        mock_fn.side_effect = Exception("429")

        mock_sleep = mocker.patch("time.sleep")
        try:
            with_retry(mock_fn, tries=2, base_delay=10)
        except Exception:
            pass

        mock_sleep.assert_called_once_with(10)
