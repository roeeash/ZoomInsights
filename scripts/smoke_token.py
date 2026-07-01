#!/usr/bin/env python
"""Manual smoke test for Zoom token retrieval."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zoom_insights.config import load_config
from zoom_insights.zoom_client import get_access_token


if __name__ == "__main__":
    config = load_config()
    token = get_access_token(config)
    print(f"Token prefix: {token[:8]}")
