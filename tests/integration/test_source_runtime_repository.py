import json
from datetime import datetime
from pathlib import Path

import pytest

from industrial_phm.application import (
    JsonSourceRuntimeRepository,
    SourceReceiptEvidence,
    SourceRuntimeFormatError,
    SourceRuntimeRepository,
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

    assert payload["schema"] == "industrial-phm-source-runtime-v1"
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
