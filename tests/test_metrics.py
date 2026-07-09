"""Tests for metrics collection and cost estimation."""

import pytest
from zoom_insights.metrics import (
    MetricsCollector,
    aggregate_metrics,
    cost_estimate,
    format_metrics_summary,
)


@pytest.mark.unit
class TestMetricsCollector:
    """Tests for MetricsCollector dataclass."""

    def test_metrics_collector_default_values(self):
        """MetricsCollector should have sensible defaults."""
        m = MetricsCollector()
        assert m.total_input_tokens == 0
        assert m.total_output_tokens == 0
        assert m.total_latency_seconds == 0.0
        assert m.num_api_calls == 0
        assert m.num_chunks == 0
        assert m.estimated_cost_usd == 0.0

    def test_metrics_collector_with_values(self):
        """MetricsCollector should store provided values."""
        m = MetricsCollector(
            total_input_tokens=100,
            total_output_tokens=50,
            total_latency_seconds=1.5,
            num_api_calls=2,
            num_chunks=3,
            estimated_cost_usd=0.001,
        )
        assert m.total_input_tokens == 100
        assert m.total_output_tokens == 50
        assert m.total_latency_seconds == 1.5
        assert m.num_api_calls == 2
        assert m.num_chunks == 3
        assert m.estimated_cost_usd == 0.001


@pytest.mark.unit
class TestCostEstimate:
    """Tests for cost_estimate function."""

    def test_cost_estimate_llama_model(self):
        """Cost should be calculated correctly for llama-3.1-8b-instant."""
        # llama-3.1-8b-instant: 0.05/1M input, 0.08/1M output
        # 1000 input + 1000 output = 0.00005 + 0.00008 = 0.00013
        cost = cost_estimate(1000, 1000, "llama-3.1-8b-instant")
        assert cost == pytest.approx(0.00013, rel=1e-5)

    def test_cost_estimate_whisper_free(self):
        """Whisper should be free."""
        cost = cost_estimate(10000, 10000, "whisper-large-v3-turbo")
        assert cost == 0.0

    def test_cost_estimate_unknown_model_free(self):
        """Unknown models should default to free."""
        cost = cost_estimate(1000, 1000, "unknown-model")
        assert cost == 0.0

    def test_cost_estimate_zero_tokens(self):
        """Zero tokens should have zero cost."""
        cost = cost_estimate(0, 0, "llama-3.1-8b-instant")
        assert cost == 0.0

    def test_cost_estimate_never_negative(self):
        """Cost should never be negative."""
        cost = cost_estimate(-100, -100, "llama-3.1-8b-instant")
        assert cost >= 0.0


@pytest.mark.unit
class TestAggregateMetrics:
    """Tests for aggregate_metrics function."""

    def test_aggregate_empty_list(self):
        """Aggregating empty list should return zeroed collector."""
        result = aggregate_metrics([])
        assert result.total_input_tokens == 0
        assert result.total_output_tokens == 0
        assert result.total_latency_seconds == 0.0
        assert result.num_api_calls == 0

    def test_aggregate_single_metric(self):
        """Aggregating single metric should return equivalent collector."""
        m = MetricsCollector(
            total_input_tokens=100,
            total_output_tokens=50,
            total_latency_seconds=1.0,
            num_api_calls=1,
            num_chunks=5,
        )
        result = aggregate_metrics([m])
        assert result.total_input_tokens == 100
        assert result.total_output_tokens == 50
        assert result.total_latency_seconds == 1.0
        assert result.num_api_calls == 1
        assert result.num_chunks == 5

    def test_aggregate_multiple_metrics(self):
        """Aggregating multiple metrics should sum all values."""
        m1 = MetricsCollector(
            total_input_tokens=100,
            total_output_tokens=50,
            total_latency_seconds=1.0,
            num_api_calls=1,
            num_chunks=2,
        )
        m2 = MetricsCollector(
            total_input_tokens=200,
            total_output_tokens=75,
            total_latency_seconds=1.5,
            num_api_calls=2,
            num_chunks=3,
        )
        result = aggregate_metrics([m1, m2])
        assert result.total_input_tokens == 300
        assert result.total_output_tokens == 125
        assert result.total_latency_seconds == 2.5
        assert result.num_api_calls == 3
        assert result.num_chunks == 5


@pytest.mark.unit
class TestFormatMetricsSummary:
    """Tests for format_metrics_summary function."""

    def test_format_includes_all_fields(self):
        """Summary should include all metric fields."""
        m = MetricsCollector(
            total_input_tokens=1000,
            total_output_tokens=500,
            total_latency_seconds=2.5,
            num_api_calls=3,
            num_chunks=5,
            estimated_cost_usd=0.001,
        )
        summary = format_metrics_summary(m)
        assert "1,000" in summary  # formatted with comma
        assert "500" in summary
        assert "2.50s" in summary
        assert "3" in summary
        assert "5" in summary
        assert "0.001000" in summary or "$0.001" in summary

    def test_format_includes_header(self):
        """Summary should have a header."""
        m = MetricsCollector()
        summary = format_metrics_summary(m)
        assert "Processing Metrics" in summary or "Metrics" in summary
