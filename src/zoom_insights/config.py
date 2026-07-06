"""Configuration loading and validation for Zoom Insights."""

from dataclasses import dataclass
from typing import Optional
import os
from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    zoom_account_id: str
    zoom_client_id: str
    zoom_client_secret: str
    groq_api_key: str
    llm_model: str = "llama-3.3-70b-versatile"
    whisper_model: str = "whisper-large-v3-turbo"
    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = ""
    claude_api_key: str = ""
    zoom_webhook_secret_token: str = ""
    ollama_url: str = "http://localhost:11434"
    use_local_backend: bool = False
    huggingface_token: str = ""
    slack_webhook_url: str = ""
    teams_webhook_url: str = ""
    tracker_db: str = ""

    def validate(self) -> None:
        """Validate that all required fields are set; raise ValueError if any are missing."""
        required = ["zoom_account_id", "zoom_client_id", "zoom_client_secret", "groq_api_key"]
        missing = [field for field in required if not getattr(self, field)]
        if missing:
            raise ValueError(f"Missing required configuration variables: {', '.join(missing)}")

    def validate_zoom(self) -> None:
        """Validate that Zoom credentials are set."""
        zoom_fields = ["zoom_account_id", "zoom_client_id", "zoom_client_secret"]
        missing = [field for field in zoom_fields if not getattr(self, field)]
        if missing:
            raise ValueError(f"Missing Zoom configuration variables: {', '.join(missing)}")


def load_config() -> Config:
    """Load configuration from .env file and environment variables."""
    load_dotenv()

    jira_url = os.getenv("JIRA_URL", "").rstrip("/")

    config = Config(
        zoom_account_id=os.getenv("ZOOM_ACCOUNT_ID", ""),
        zoom_client_id=os.getenv("ZOOM_CLIENT_ID", ""),
        zoom_client_secret=os.getenv("ZOOM_CLIENT_SECRET", ""),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        whisper_model=os.getenv("WHISPER_MODEL", "whisper-large-v3-turbo"),
        jira_url=jira_url,
        jira_email=os.getenv("JIRA_EMAIL", ""),
        jira_api_token=os.getenv("JIRA_API_TOKEN", ""),
        jira_project_key=os.getenv("JIRA_PROJECT_KEY", ""),
        claude_api_key=os.getenv("CLAUDE_API_KEY", ""),
        zoom_webhook_secret_token=os.getenv("ZOOM_WEBHOOK_SECRET_TOKEN", ""),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        use_local_backend=os.getenv("USE_LOCAL_BACKEND", "false").lower() == "true",
        huggingface_token=os.getenv("HUGGINGFACE_TOKEN", ""),
        slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL", ""),
        teams_webhook_url=os.getenv("TEAMS_WEBHOOK_URL", ""),
        tracker_db=os.getenv("TRACKER_DB", os.path.expanduser("~/.zoom-insights.db")),
    )

    config.validate()
    return config
