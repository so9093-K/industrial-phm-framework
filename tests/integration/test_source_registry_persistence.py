import json
from datetime import datetime
from pathlib import Path

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    FileSourceMode,
    JsonSourceRepository,
    RegisteredSource,
    SourceAlreadyRegisteredError,
    SourceRegistryFormatError,
    SourceRepository,
    UnknownRegisteredSourceError,
)


def _source(
    *,
    source_id: str = "source-a",
    source_path: str = "data/pump.csv",
    mode: FileSourceMode = FileSourceMode.SNAPSHOT,
) -> RegisteredSource:
    return RegisteredSource(
        source_id=source_id,
        name=f"Registered {source_id}",
        config=FileSourceConfig(
            source_path=source_path,
            asset_id="pump-01",
            measurement_point_id="drive-end-bearing",
            channel_columns=("vibration_x", "temperature"),
            mode=mode,
            timestamp_column="timestamp",
            sampling_rate_hz=1_000.0,
            sampling_rate_tolerance_ratio=0.05,
            minimum_sample_count=32,
        ),
        registered_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
    )


def test_json_source_repository_implements_source_repository_contract(tmp_path: Path) -> None:
    repository = JsonSourceRepository(tmp_path / "sources.json")

    assert isinstance(repository, SourceRepository)


def test_json_source_repository_round_trip_survives_new_repository_instance(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "state" / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _source()

    repository.register(source)

    reopened = JsonSourceRepository(registry)
    assert reopened.get(source.source_id) == source
    assert reopened.list_sources() == (source,)


def test_json_source_repository_preserves_history_directory_configuration(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    source = _source(
        source_id="history-source",
        source_path="data/history",
        mode=FileSourceMode.HISTORY_DIRECTORY,
    )

    JsonSourceRepository(registry).register(source)
    loaded = JsonSourceRepository(registry).get("history-source")

    assert loaded.config.mode == FileSourceMode.HISTORY_DIRECTORY
    assert loaded.config.source_path == "data/history"
    assert loaded.config.timestamp_column == "timestamp"


def test_json_source_repository_writes_sources_in_deterministic_id_order(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)

    repository.register(_source(source_id="source-b", source_path="data/b.csv"))
    repository.register(_source(source_id="source-a", source_path="data/a.csv"))

    payload = json.loads(registry.read_text(encoding="utf-8"))
    source_ids = [item["source_id"] for item in payload["sources"]]

    assert payload["schema"] == "industrial-phm-source-registry-v1"
    assert source_ids == ["source-a", "source-b"]


def test_json_source_repository_does_not_persist_runtime_health_claims(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"

    JsonSourceRepository(registry).register(_source())

    payload = json.loads(registry.read_text(encoding="utf-8"))
    stored = payload["sources"][0]

    assert set(stored) == {
        "source_id",
        "name",
        "source_type",
        "registered_at",
        "config",
    }
    assert "connected" not in stored
    assert "healthy" not in stored
    assert "last_received_at" not in stored


def test_json_source_repository_rejects_duplicate_without_replacing_existing_source(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    original = _source()

    repository.register(original)

    with pytest.raises(SourceAlreadyRegisteredError, match="already registered"):
        repository.register(_source(source_path="data/replacement.csv"))

    assert JsonSourceRepository(registry).get(original.source_id) == original


def test_json_source_repository_rejects_unknown_source_id(tmp_path: Path) -> None:
    repository = JsonSourceRepository(tmp_path / "sources.json")

    with pytest.raises(UnknownRegisteredSourceError, match="does not exist"):
        repository.get("missing-source")


def test_json_source_repository_rejects_malformed_json(tmp_path: Path) -> None:
    registry = tmp_path / "sources.json"
    registry.write_text("{not-json", encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="valid JSON"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_rejects_unsupported_schema(tmp_path: Path) -> None:
    registry = tmp_path / "sources.json"
    registry.write_text(
        json.dumps({"schema": "future-schema", "sources": []}),
        encoding="utf-8",
    )

    with pytest.raises(SourceRegistryFormatError, match="unsupported source registry schema"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_rejects_unknown_source_type(tmp_path: Path) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    repository.register(_source())

    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["sources"][0]["source_type"] = "opcua"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="source_type is unsupported"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_rejects_duplicate_ids_in_persisted_registry(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    repository.register(_source())

    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["sources"].append(dict(payload["sources"][0]))
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="duplicate source_id"):
        JsonSourceRepository(registry).list_sources()
