"""Find the model packages an asset can use and connect one, from the CLI or the Web.

A package is matched to the asset's actual input streams: delivered acquisition snapshots and
registered OPC UA sources whose finalized windows feed the runner. Connecting creates the same
binding record as `operations phm bind`. The runner stays the authority on input compatibility;
a mismatch found later is a skipped step with its reason, never a fabricated result.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from industrial_phm.application import JsonSourceRepository, OpcUaSourceConfig
from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.analysis_input import (
    ChannelObservation,
    window_channel_observations,
)
from industrial_phm.application.electrical_window_features import (
    ELECTRICAL_WINDOW_CHANNELS,
    ELECTRICAL_WINDOW_FEATURE_SET_ID,
    resolve_electrical_roles,
)
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore
from industrial_phm.models.package import RETIRED_TASKS, load_model_package
from industrial_phm.runtime.operations_web_setup import SourceControlConflict
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_ACQUISITION = "acquisition-snapshot"
_WINDOW = "observation-window"
_MAX_PACKAGES = 100


def derived_binding_id(
    package_id: str, source_id: str, asset_id: str, point_id: str | None = None
) -> str:
    identity = f"{package_id}\n{source_id}\n{asset_id}"
    if point_id is not None:
        identity += "\npoint:" + point_id
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f"phm-{asset_id}-{digest[:10]}"


def create_phm_binding(
    workspace: OperationsWorkspace,
    *,
    package_id: str,
    source_id: str,
    asset_id: str,
    measurement_point_id: str | None = None,
    recorded_replay: bool = False,
    binding_id: str | None = None,
) -> tuple[PhmBinding, bool, str]:
    """Verify the package, then record the binding; returns (binding, created, task)."""
    if not package_id or "/" in package_id or package_id.startswith("."):
        raise ValueError("invalid package ID")
    package = load_model_package(workspace.models_path / package_id)
    binding = PhmBinding(
        binding_id=binding_id
        or derived_binding_id(package_id, source_id, asset_id, measurement_point_id),
        package_id=package_id,
        source_id=source_id,
        asset_id=asset_id,
        step_kind=package.manifest.input.step_kind,
        created_at=datetime.now(UTC),
        recorded_replay=recorded_replay,
        measurement_point_id=measurement_point_id,
    )
    created = SqlitePhmAnalysisStore(workspace.phm_analysis_path).create_binding(binding)
    return binding, created, package.manifest.output.task.value


def _packages(models_root: Path) -> list[dict[str, Any]]:
    """Descriptive manifest fields only; verification happens when a package is connected."""
    if not models_root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(models_root.iterdir())[: _MAX_PACKAGES * 2]:
        try:
            body = json.loads((path / "package.json").read_text(encoding="utf-8"))
        except OSError, ValueError:
            continue
        if not isinstance(body, dict) or not isinstance(body.get("input"), dict):
            continue
        output: dict[str, Any] = body["output"] if isinstance(body.get("output"), dict) else {}
        if output.get("task") in RETIRED_TASKS:
            continue
        validation: dict[str, Any] = (
            body["validation"] if isinstance(body.get("validation"), dict) else {}
        )
        items.append(
            {
                "package_id": body.get("package_id", path.name),
                "recipe_id": body.get("recipe_id"),
                "task": output.get("task"),
                "unit": output.get("unit"),
                "input": {
                    key: body["input"].get(key)
                    for key in (
                        "step_kind",
                        "channels",
                        "sampling_rate_hz",
                        "samples_per_step",
                        "feature_set_id",
                    )
                },
                "acceptance": validation.get("acceptance"),
            }
        )
    return items[:_MAX_PACKAGES]


def _streams(workspace: OperationsWorkspace, asset_id: str) -> list[dict[str, Any]]:
    streams: list[dict[str, Any]] = []
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    for snapshot in snapshots.list_streams():
        if snapshot.asset_id != asset_id:
            continue
        streams.append(
            {
                "kind": _ACQUISITION,
                "source_id": snapshot.source_id,
                "measurement_point_id": None,
                "channels": list(snapshot.channels),
                "sampling_rate_hz": snapshot.sampling_rate_hz,
                "sample_count": snapshot.sample_count,
                "recorded_replay": snapshot.replay,
                "input_state": "stored-input",
            }
        )
    if workspace.source_registry_path.is_file():
        windows = SqliteObservationWindowRepository(workspace.window_state_path)
        for source in JsonSourceRepository(workspace.source_registry_path).list_sources():
            if source.asset_id != asset_id or not isinstance(source.config, OpcUaSourceConfig):
                continue
            latest = (
                windows.latest_for_stream(source.source_id, asset_id, source.measurement_point_id)
                if windows.path.exists()
                else None
            )
            observations = (
                window_channel_observations(latest)
                if latest is not None
                else tuple(
                    ChannelObservation(
                        source.source_id,
                        source.measurement_point_id,
                        binding.channel_id,
                        source.registered_at,
                        None,
                        False,
                        False,
                        binding.definition.observed_property,
                        binding.definition.scope,
                        binding.definition.unit,
                        binding.version,
                    )
                    for binding in source.config.semantic_bindings
                )
            )
            _, electrical_reason = resolve_electrical_roles(observations)
            streams.append(
                {
                    "kind": _WINDOW,
                    "source_id": source.source_id,
                    "measurement_point_id": source.measurement_point_id,
                    "channels": [identity.channel_id for identity in source.channel_identities],
                    "sampling_rate_hz": None,
                    "sample_count": None,
                    "recorded_replay": False,
                    "name": source.name,
                    "input_state": "stored-input" if latest is not None else "waiting-input",
                    "electrical_input_reason": electrical_reason,
                }
            )
    return streams


def _fit(package: dict[str, Any], stream: dict[str, Any]) -> str | None:
    """Return why the package cannot read the stream, or None when its declared input fits."""
    spec = package["input"]
    if spec.get("step_kind") != stream["kind"]:
        wanted = "진동 파형" if spec.get("step_kind") == _ACQUISITION else "관측 윈도우"
        return wanted + " 입력이 필요합니다"
    channels = spec.get("channels") or []
    if stream["kind"] == _ACQUISITION:
        if list(channels) != list(stream["channels"]):
            return "채널 구성이 다릅니다"
        rate = spec.get("sampling_rate_hz")
        if rate is not None and float(rate) != float(stream["sampling_rate_hz"]):
            return "샘플링 주파수가 다릅니다"
        samples = spec.get("samples_per_step")
        if samples is not None and int(samples) != int(stream["sample_count"]):
            return "측정 1회당 표본 수가 다릅니다"
    elif spec.get("feature_set_id") == ELECTRICAL_WINDOW_FEATURE_SET_ID:
        if tuple(channels) != ELECTRICAL_WINDOW_CHANNELS:
            return "모델의 전기 신호 입력 규격이 다릅니다"
        if stream.get("electrical_input_reason") is not None:
            return "전류·전압 R/S/T 역할과 A/V/Hz 단위 선언을 확인하세요"
    elif not set(channels) <= set(stream["channels"]):
        return "필요한 채널이 이 소스에 없습니다"
    return None


def project_phm_models(workspace: OperationsWorkspace, asset_id: str) -> dict[str, Any]:
    """Packages, the asset's input streams and which pairs can be connected."""
    packages = _packages(workspace.models_path)
    streams = _streams(workspace, asset_id)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    bound = (
        {
            (item.package_id, item.source_id, item.measurement_point_id)
            for item in store.list_bindings()
            if item.asset_id == asset_id
        }
        if store.path.exists()
        else set()
    )
    for package in packages:
        candidates = []
        for stream in streams:
            reason = _fit(package, stream)
            candidates.append(
                {
                    "source_id": stream["source_id"],
                    "measurement_point_id": stream["measurement_point_id"],
                    "compatible": reason is None,
                    "reason": reason,
                    "connected": (
                        package["package_id"],
                        stream["source_id"],
                        stream["measurement_point_id"],
                    )
                    in bound,
                }
            )
        package["candidates"] = candidates
    return {
        "schema_version": 1,
        "asset_id": asset_id,
        "streams": streams,
        "packages": packages,
        "meaning": "model-packages-and-asset-input-streams",
    }


def connect_web_phm_model(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Connect one package to one of the asset's existing input streams."""
    allowed = {"package_id", "source_id", "asset_id", "measurement_point_id"}
    if not {"package_id", "source_id", "asset_id"} <= set(payload) <= allowed:
        raise ValueError("unexpected model connection fields")
    values = {key: payload.get(key) for key in allowed}
    if any(value is not None and not isinstance(value, str) for value in values.values()):
        raise ValueError("model connection fields must be text")
    workspace = OperationsWorkspace(root)
    asset_id = str(values["asset_id"])
    point = values["measurement_point_id"] or None
    stream = next(
        (
            item
            for item in _streams(workspace, asset_id)
            if item["source_id"] == values["source_id"] and item["measurement_point_id"] == point
        ),
        None,
    )
    package = next(
        (
            item
            for item in _packages(workspace.models_path)
            if item["package_id"] == values["package_id"]
        ),
        None,
    )
    if stream is None or package is None:
        raise SourceControlConflict("unknown package or input stream for this asset")
    if (reason := _fit(package, stream)) is not None:
        raise SourceControlConflict(reason)
    binding, created, task = create_phm_binding(
        workspace,
        package_id=str(values["package_id"]),
        source_id=str(values["source_id"]),
        asset_id=asset_id,
        measurement_point_id=point if isinstance(point, str) else None,
        recorded_replay=bool(stream["recorded_replay"]),
    )
    return {
        "schema_version": 1,
        "binding_id": binding.binding_id,
        "asset_id": binding.asset_id,
        "package_id": binding.package_id,
        "task": task,
        "created": created,
        "meaning": "model-binding-recorded-results-follow-from-the-runner",
    }
