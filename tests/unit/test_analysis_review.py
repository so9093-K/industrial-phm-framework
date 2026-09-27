from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from industrial_phm.analysis import (
    AnalysisReviewFormatError,
    AnalysisReviewRecord,
    JsonAnalysisReviewRepository,
    analysis_artifact_sha256,
)


def _record(*, reviewed_at: datetime, note: str = "checked") -> AnalysisReviewRecord:
    return AnalysisReviewRecord(
        artifact_path="artifacts/analysis/result.json",
        artifact_sha256="a" * 64,
        asset_id="bearing-01",
        review_policy_id="early-scored-windows-nearest-rank-quantile-v1",
        review_threshold_value=1.25,
        review_interval_count=2,
        reviewed_at=reviewed_at,
        note=note,
    )


def test_analysis_review_repository_round_trips_and_updates_latest_record(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reviews.json"
    repository = JsonAnalysisReviewRepository(path)
    first_time = datetime(2026, 9, 27, 4, 30, tzinfo=timezone.utc)

    repository.record(_record(reviewed_at=first_time))
    repository.record(
        _record(
            reviewed_at=first_time + timedelta(minutes=5),
            note="inspected strongest interval",
        )
    )

    records = repository.list_records()
    assert len(records) == 1
    assert records[0].note == "inspected strongest interval"
    assert repository.get(
        artifact_sha256="a" * 64,
        asset_id="bearing-01",
        review_policy_id="early-scored-windows-nearest-rank-quantile-v1",
    ) == records[0]


def test_analysis_review_repository_rejects_review_time_regression(tmp_path: Path) -> None:
    repository = JsonAnalysisReviewRepository(tmp_path / "reviews.json")
    current = datetime(2026, 9, 27, 4, 30, tzinfo=timezone.utc)
    repository.record(_record(reviewed_at=current))

    with pytest.raises(ValueError, match="must not move backwards"):
        repository.record(_record(reviewed_at=current - timedelta(seconds=1)))


def test_analysis_review_repository_rejects_unsupported_schema(tmp_path: Path) -> None:
    path = tmp_path / "reviews.json"
    path.write_text(
        '{"schema":"industrial-phm-analysis-review-v999","records":[]}\n',
        encoding="utf-8",
    )

    with pytest.raises(AnalysisReviewFormatError, match="unsupported analysis review schema"):
        JsonAnalysisReviewRepository(path).list_records()


def test_analysis_artifact_sha256_tracks_exact_file_bytes(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    path.write_text('{"value": 1}\n', encoding="utf-8")
    first = analysis_artifact_sha256(path)

    path.write_text('{"value": 2}\n', encoding="utf-8")
    second = analysis_artifact_sha256(path)

    assert len(first) == 64
    assert len(second) == 64
    assert first != second
