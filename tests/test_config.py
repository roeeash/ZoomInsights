"""Tests for configuration loading and validation."""

import pytest
import os
from zoom_insights.config import Config, load_config


@pytest.mark.unit
class TestConfigValidate:
    """Tests for Config.validate() method."""

    def test_config_validate_success(self):
        """Test that validation passes when all required variables are set."""
        config = Config(
            zoom_account_id="account123",
            zoom_client_id="client123",
            zoom_client_secret="secret123",
            groq_api_key="groq123",
        )
        # Should not raise
        config.validate()

    def test_config_validate_missing_single_var(self):
        """Test that validation raises ValueError naming the missing variable."""
        config = Config(
            zoom_account_id="account123",
            zoom_client_id="client123",
            zoom_client_secret="",
            groq_api_key="groq123",
        )
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "zoom_client_secret" in str(exc_info.value)

    def test_config_validate_missing_multiple_vars(self):
        """Test that validation raises ValueError naming all missing variables."""
        config = Config(
            zoom_account_id="",
            zoom_client_id="",
            zoom_client_secret="secret123",
            groq_api_key="",
        )
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        error_msg = str(exc_info.value)
        assert "zoom_account_id" in error_msg
        assert "zoom_client_id" in error_msg
        assert "groq_api_key" in error_msg

    def test_config_defaults(self):
        """Test that optional variables use default values."""
        config = Config(
            zoom_account_id="account123",
            zoom_client_id="client123",
            zoom_client_secret="secret123",
            groq_api_key="groq123",
        )
        assert config.llm_model == "llama-3.3-70b-versatile"
        assert config.whisper_model == "whisper-large-v3-turbo"
