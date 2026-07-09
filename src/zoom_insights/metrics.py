"""Metrics aggregation and cost estimation for API calls."""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricsCollector:
    """Collects metrics from a processing run."""

    timestamp: Optional[str] = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_seconds: float = 0.0
    num_api_calls: int = 0
    num_chunks: int = 0
    estimated_cost_usd: float = 0.0


# Groq pricing (as of 2025-02)
GROQ_PRICING = {
    "mixtral-8x7b-32768": {"input": 0.24 / 1e6, "output": 0.24 / 1e6},
    "llama-3.1-70b-versatile": {"input": 0.59 / 1e6, "output": 0.79 / 1e6},
    "llama-3.1-8b-instant": {"input": 0.05 / 1e6, "output": 0.08 / 1e6},
    "llama-3.2-11b-vision-preview": {"input": 0.06 / 1e6, "output": 0.06 / 1e6},
    "whisper-large-v3-turbo": {"input": 0.0, "output": 0.0},  # Whisper is free
}


def cost_estimate(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate USD cost for API tokens.

    Args:
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.
        model: Model identifier (e.g. 'mixtral-8x7b-32768').

    Returns:
        Estimated cost in USD.
    """
    pricing = GROQ_PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost = (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])
    return max(0.0, cost)  # Never negative


def aggregate_metrics(metrics_list: list[MetricsCollector]) -> MetricsCollector:
    """Aggregate a list of metrics collectors into one.

    Args:
        metrics_list: List of MetricsCollector instances.

    Returns:
        Single MetricsCollector with aggregated values.
    """
    aggregated = MetricsCollector()

    for m in metrics_list:
        aggregated.total_input_tokens += m.total_input_tokens
        aggregated.total_output_tokens += m.total_output_tokens
        aggregated.total_latency_seconds += m.total_latency_seconds
        aggregated.num_api_calls += m.num_api_calls
        aggregated.num_chunks += m.num_chunks
        aggregated.estimated_cost_usd += m.estimated_cost_usd

    return aggregated


def format_metrics_summary(collector: MetricsCollector) -> str:
    """Format metrics into a human-readable summary.

    Args:
        collector: MetricsCollector instance.

    Returns:
        Formatted summary string.
    """
    lines = [
        "## Processing Metrics",
        f"Total tokens (input): {collector.total_input_tokens:,}",
        f"Total tokens (output): {collector.total_output_tokens:,}",
        f"Total latency: {collector.total_latency_seconds:.2f}s",
        f"API calls: {collector.num_api_calls}",
        f"Chunks processed: {collector.num_chunks}",
        f"Estimated cost: ${collector.estimated_cost_usd:.6f}",
    ]
    return "\n".join(lines)
