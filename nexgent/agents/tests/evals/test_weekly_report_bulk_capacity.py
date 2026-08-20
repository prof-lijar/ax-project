import pytest
from ax_evals import evaluate_weekly_report_bulk_capacity


def test_bulk_capacity_distinguishes_sla_from_healthy_headroom() -> None:
    results = evaluate_weekly_report_bulk_capacity(1.5)

    assert [result.status for result in results] == ["passed", "failed"]


def test_bulk_capacity_passes_at_healthy_target() -> None:
    results = evaluate_weekly_report_bulk_capacity(10_000 / (90 * 60))

    assert all(result.status == "passed" for result in results)


def test_bulk_capacity_rejects_non_positive_throughput() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        evaluate_weekly_report_bulk_capacity(0)
