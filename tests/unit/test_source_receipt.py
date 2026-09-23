from datetime import datetime

import pytest

from industrial_phm.application import SourceReceiptEvidence


def test_source_receipt_requires_timezone_aware_received_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SourceReceiptEvidence(
            source_id="source-a",
            received_at=datetime.fromisoformat("2026-09-23T10:00:00"),
            observed_at=datetime.fromisoformat("2026-09-23T09:59:00+09:00"),
        )


def test_source_receipt_computes_signed_lag_for_aware_timestamps() -> None:
    receipt = SourceReceiptEvidence(
        source_id="source-a",
        observed_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
        received_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
    )

    assert receipt.lag_seconds == 5.0
    assert receipt.lag_unavailable_reason is None


def test_source_receipt_preserves_negative_lag_as_clock_evidence() -> None:
    receipt = SourceReceiptEvidence(
        source_id="source-a",
        observed_at=datetime.fromisoformat("2026-09-23T10:00:10+09:00"),
        received_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
    )

    assert receipt.lag_seconds == -5.0


def test_source_receipt_does_not_compare_naive_observed_time() -> None:
    receipt = SourceReceiptEvidence(
        source_id="source-a",
        observed_at=datetime.fromisoformat("2026-09-23T10:00:00"),
        received_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
    )

    assert receipt.lag_seconds is None
    assert receipt.lag_unavailable_reason == "source observation timezone is unavailable"


def test_source_receipt_explains_missing_observed_time() -> None:
    receipt = SourceReceiptEvidence(
        source_id="source-a",
        observed_at=None,
        received_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
    )

    assert receipt.lag_seconds is None
    assert receipt.lag_unavailable_reason == "source observation time is unavailable"
