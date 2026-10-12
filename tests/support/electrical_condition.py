"""One explicit synthetic electrical load-change scenario for HTTP and browser tests."""

from datetime import UTC, datetime, timedelta
from math import sin
from pathlib import Path

from industrial_phm.application import (
    FileSourceConfig,
    JsonSourceRepository,
    RegisteredSource,
    backfill_registered_file_source,
)
from industrial_phm.application.measurement_semantics import (
    ChannelSemanticBinding,
    MeasurementDefinition,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace


def condition_workspace(root: Path) -> OperationsWorkspace:
    workspace = OperationsWorkspace(root)
    initialize_operations_workspace(workspace)
    source_path = root / "synthetic-phase.csv"
    at = datetime(2020, 11, 13, tzinfo=UTC)
    lines = ["timestamp,vR,vS,vT,iR,iS,iT"]
    for index in range(240):
        current = 10 if index < 180 else 80
        values = [
            230 + sin(index),
            231 + sin(index * 0.4),
            229 + sin(index * 0.7),
            current + sin(index),
            current + 1 + sin(index * 0.4),
            current + 2 + sin(index * 0.7),
        ]
        lines.append((at + timedelta(minutes=index)).isoformat() + "," + ",".join(map(str, values)))
    source_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    bindings = tuple(
        ChannelSemanticBinding(
            "synthetic-electrical",
            f"{prefix}{phase}",
            "synthetic-v1",
            MeasurementDefinition(
                prop, scope=f"phase {phase}", unit=unit, unit_evidence="synthetic unit"
            ),
            "synthetic declared phase role",
        )
        for prefix, prop, unit in (("v", "phase voltage", "V"), ("i", "phase current", "A"))
        for phase in "RST"
    )
    sources = JsonSourceRepository(workspace.source_registry_path)
    sources.register(
        RegisteredSource(
            source_id="synthetic-electrical",
            name="Synthetic load change",
            registered_at=at,
            config=FileSourceConfig(
                str(source_path.resolve()),
                "condition-motor",
                channel_columns=("vR", "vS", "vT", "iR", "iS", "iT"),
                timestamp_column="timestamp",
                measurement_point_id="meter",
                semantic_bindings=bindings,
            ),
        )
    )
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    backfill_registered_file_source(sources, history, "synthetic-electrical")
    return workspace
