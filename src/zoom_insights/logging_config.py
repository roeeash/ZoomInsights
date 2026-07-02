"""Logging configuration for Zoom Insights."""

import logging


def setup_logging(debug: bool = False) -> None:
    """Setup structured logging for the application.

    Args:
        debug: If True, set logging level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
