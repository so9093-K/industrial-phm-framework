import json
from datetime import datetime
from pathlib import Path

import pytest

from industrial_phm.application import (
    JsonSourceRuntimeRepository,
    SourceConnectionAttemptEvidence,
    SourceConnectionAttemptOutcome,
    SourceReceiptEvidence,
    SourceRuntimeFormatError,
    SourceRuntimeRepository,
    validate_distinct_source_state_paths,
)


def _receipt(
    *,
    source_id: str = "source-a",
    observed_at: str | None = "2026-09-23T10:00:00+09:00",
    received_at: str = "2026-09-23T10:00:05+09:00",
) -> SourceReceiptEvidence:
    return SourceReceiptEvidence(
        source_id=source_id,
        observed_at=None if observed_at is None else datetime.fromisoformat(observed_at),
        received_at=datetime.fromisoformat(received_at),
    )


def _connection_attempt(
    *,
    source_id: str = "source-a",
    outcome: SourceConnectionAttemptOutcome = SourceConnectionAttemptOutcome.SUCCEEDED,
    attempted_at: str = "2026-09-23T10:00:00+09:00",
    connected_at: str | None = "2026-09-23T10:00:01+09:00",
    completed_at: str = "2026-09-23T10:00:02+09:00",
    detail: str | None = None,
) -> SourceConnectionAttemptEvidence:
    if outcome == SourceConnectionAttemptOutcome.FAILED and detail is None:
        detail = "connection attempt failed"
    return SourceConnectionAttemptEvidence(
        source_id=source_id,
        outcome=outcome,
        attempted_at=datetime.fromisoformat(attempted_at),
        connected_at=(
            None if connected_at is None else datetime.fromisoformat(connected_at)
        ),
        completed_at=datetime.fromisoformat(completed_at),
        detail=detail,
    )


def test_source_runtime_path_must_differ_from_control_plane_registry(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "state.json"

    with pytest.raises(ValueError, match="must differ"):
        validate_distinct_source_state_paths(
            registry_path,
            tmp_path / "." / "state.json",
        )


def test_json_source_runtime_repository_implements_contract(tmp_path: Path) -> None:
    repository = JsonSourceRuntimeRepository(tmp_path / "runtime.json")

    assert isinstance(repository, SourceRuntimeRepository)


def test_json_source_runtime_repository_round_trip_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "state" / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    receipt = _receipt()

    repository.record_receipt(receipt)

    reopened = JsonSourceRuntimeRepository(path)
    assert reopened.get_latest_receipt(receipt.source_id) == receipt
    assert reopened.list_latest_receipts() == (receipt,)


def test_json_source_runtime_repository_preserves_naive_or_missing_observed_time(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    naive = _receipt(
        source_id="source-naive",
        observed_at="2026-09-23T10:00:00",
    )
    missing = _receipt(
        source_id="source-missing",
        observed_at=None,
        received_at="2026-09-23T10:01:05+09:00",
    )

    repository.record_receipt(naive)
    repository.record_receipt(missing)

    reopened = JsonSourceRuntimeRepository(path)
    assert reopened.get_latest_receipt("source-naive") == naive
    assert reopened.get_latest_receipt("source-missing") == missing


def test_json_source_runtime_repository_writes_deterministic_source_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)

    repository.record_receipt(_receipt(source_id="source-b"))
    repository.record_receipt(_receipt(source_id="source-a"))

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema"] == "industrial-phm-source-runtime-v2"
    assert payload["latest_connection_attempts"] == []
    assert [item["source_id"] for item in payload["latest_receipts"]] == [
        "source-a",
        "source-b",
    ]


def test_json_source_runtime_repository_updates_latest_receipt(tmp_path: Path) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    first = _receipt()
    second = _receipt(
        observed_at="2026-09-23T10:01:00+09:00",
        received_at="2026-09-23T10:01:05+09:00",
    )

    repository.record_receipt(first)
    repository.record_receipt(second)

    assert repository.list_latest_receipts() == (second,)


def test_json_source_runtime_repository_rejects_received_at_regression(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    repository.record_receipt(_receipt(received_at="2026-09-23T10:01:05+09:00"))

    with pytest.raises(ValueError, match="must not move backwards"):
        repository.record_receipt(_receipt(received_at="2026-09-23T10:01:04+09:00"))


def test_json_source_runtime_repository_rejects_conflict_at_same_received_at(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    repository.record_receipt(_receipt())

    with pytest.raises(ValueError, match="same received_at"):
        repository.record_receipt(_receipt(observed_at="2026-09-23T09:59:00+09:00"))


def test_json_source_runtime_repository_allows_idempotent_same_receipt(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    receipt = _receipt()

    repository.record_receipt(receipt)
    repository.record_receipt(receipt)

    assert repository.list_latest_receipts() == (receipt,)


def test_json_source_runtime_repository_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "runtime.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(SourceRuntimeFormatError, match="valid JSON"):
        JsonSourceRuntimeRepository(path).list_latest_receipts()


def test_json_source_runtime_repository_rejects_unsupported_schema(tmp_path: Path) -> None:
    path = tmp_path / "runtime.json"
    path.write_text(
        json.dumps({"schema": "future-schema", "latest_receipts": []}),
        encoding="utf-8",
    )

    with pytest.raises(SourceRuntimeFormatError, match="unsupported source runtime schema"):
        JsonSourceRuntimeRepository(path).list_latest_receipts()


def test_json_source_runtime_repository_rejects_duplicate_source_ids(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    repository.record_receipt(_receipt())

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["latest_receipts"].append(dict(payload["latest_receipts"][0]))
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRuntimeFormatError, match="duplicate receipt source_id"):
        JsonSourceRuntimeRepository(path).list_latest_receipts()


def test_json_source_runtime_repository_rejects_schema_key_drift(tmp_path: Path) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    repository.record_receipt(_receipt())

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRuntimeFormatError, match="keys do not match schema"):
        JsonSourceRuntimeRepository(path).list_latest_receipts()



def test_connection_attempt_evidence_requires_success_timing_and_failure_detail() -> None:
    with pytest.raises(ValueError, match="requires connected_at"):
        _connection_attempt(connected_at=None)

    with pytest.raises(ValueError, match="requires detail"):
        SourceConnectionAttemptEvidence(
            source_id="source-a",
            outcome=SourceConnectionAttemptOutcome.FAILED,
            attempted_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
            completed_at=datetime.fromisoformat("2026-09-23T10:00:02+09:00"),
        )

    with pytest.raises(ValueError, match="before attempted_at"):
        _connection_attempt(connected_at="2026-09-23T09:59:59+09:00")


def test_json_source_runtime_repository_round_trips_success_and_failed_connection_attempts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    success = _connection_attempt(source_id="source-a")
    failed = _connection_attempt(
        source_id="source-b",
        outcome=SourceConnectionAttemptOutcome.FAILED,
        connected_at=None,
        attempted_at="2026-09-23T10:01:00+09:00",
        completed_at="2026-09-23T10:01:03+09:00",
        detail="connection refused",
    )

    repository.record_connection_attempt(failed)
    repository.record_connection_attempt(success)

    reopened = JsonSourceRuntimeRepository(path)
    assert reopened.get_latest_connection_attempt("source-a") == success
    assert reopened.get_latest_connection_attempt("source-b") == failed
    assert reopened.list_latest_connection_attempts() == (success, failed)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "industrial-phm-source-runtime-v2"
    assert [item["source_id"] for item in payload["latest_connection_attempts"]] == [
        "source-a",
        "source-b",
    ]


def test_runtime_v2_writes_preserve_receipts_and_connection_attempts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    receipt = _receipt(source_id="source-a")
    attempt = _connection_attempt(source_id="source-b")

    repository.record_receipt(receipt)
    repository.record_connection_attempt(attempt)
    repository.record_receipt(
        _receipt(
            source_id="source-c",
            observed_at="2026-09-23T10:02:00+09:00",
            received_at="2026-09-23T10:02:05+09:00",
        )
    )

    reopened = JsonSourceRuntimeRepository(path)
    assert reopened.get_latest_receipt("source-a") == receipt
    assert reopened.get_latest_connection_attempt("source-b") == attempt
    assert tuple(item.source_id for item in reopened.list_latest_receipts()) == (
        "source-a",
        "source-c",
    )


def test_runtime_v1_receipts_remain_readable_and_upgrade_on_next_write(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    path.write_text(
        json.dumps(
            {
                "schema": "industrial-phm-source-runtime-v1",
                "latest_receipts": [
                    {
                        "source_id": "legacy-source",
                        "observed_at": "2026-09-23T10:00:00+09:00",
                        "received_at": "2026-09-23T10:00:05+09:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    repository = JsonSourceRuntimeRepository(path)

    assert repository.get_latest_receipt("legacy-source") == _receipt(
        source_id="legacy-source"
    )
    assert repository.list_latest_connection_attempts() == ()

    repository.record_connection_attempt(_connection_attempt(source_id="legacy-source"))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "industrial-phm-source-runtime-v2"
    assert payload["latest_receipts"][0]["source_id"] == "legacy-source"
    assert payload["latest_connection_attempts"][0]["source_id"] == "legacy-source"


def test_json_source_runtime_repository_rejects_connection_attempt_time_regression(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    repository.record_connection_attempt(
        _connection_attempt(completed_at="2026-09-23T10:01:02+09:00")
    )

    with pytest.raises(ValueError, match="completed_at must not move backwards"):
        repository.record_connection_attempt(
            _connection_attempt(
                attempted_at="2026-09-23T09:59:00+09:00",
                connected_at="2026-09-23T09:59:01+09:00",
                completed_at="2026-09-23T09:59:02+09:00",
            )
        )


def test_json_source_runtime_repository_rejects_connection_attempt_conflict_at_same_time(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    attempt = _connection_attempt()
    repository.record_connection_attempt(attempt)

    with pytest.raises(ValueError, match="same completed_at"):
        repository.record_connection_attempt(
            _connection_attempt(
                outcome=SourceConnectionAttemptOutcome.FAILED,
                connected_at=None,
                detail="connection reset",
            )
        )


def test_json_source_runtime_repository_allows_idempotent_same_connection_attempt(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    attempt = _connection_attempt()

    repository.record_connection_attempt(attempt)
    repository.record_connection_attempt(attempt)

    assert repository.list_latest_connection_attempts() == (attempt,)


def test_json_source_runtime_repository_rejects_invalid_persisted_connection_attempt(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    repository = JsonSourceRuntimeRepository(path)
    repository.record_connection_attempt(_connection_attempt())

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["latest_connection_attempts"][0]["connected_at"] = None
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRuntimeFormatError, match="requires connected_at"):
        repository.list_latest_connection_attempts()
