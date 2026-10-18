"""Create a fresh, reproducible product scenario using the real application services.

The signals are explicitly synthetic. No external data, trained model, AI response,
or hand-written analysis result is used. Existing workspaces are never adopted.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.application import (
    ChannelSemanticBinding,
    FileSourceConfig,
    JsonSourceRepository,
    MeasurementDefinition,
    RegisteredSource,
)
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_actions import execute_web_source_action

START = datetime(2026, 10, 1, tzinfo=UTC)
CHANNELS = {"current_a": ("electric current", "A"), "temperature_c": ("temperature", "°C")}


def csv_bytes(changing: bool) -> bytes:
    lines = ["timestamp,current_a,temperature_c"]
    for index in range(240):
        drift = max(0, index - 119) * 0.04 if changing else 0
        current = 8 + 0.06 * math.sin(index / 7) + drift
        temperature = 35 + 0.12 * math.cos(index / 9) + drift * 1.8
        lines.append(
            f"{(START + timedelta(minutes=index)).isoformat()},{current:.6f},{temperature:.6f}"
        )
    return ("\n".join(lines) + "\n").encode()


def prepare(root: Path) -> dict[str, object]:
    root = root.resolve()
    if root.exists():
        raise ValueError("Showcase requires a new workspace; existing files are never changed")
    workspace = OperationsWorkspace(root)
    initialize_operations_workspace(workspace)
    (root / "inputs").mkdir()
    sources = []
    review = None
    for changing, asset in ((False, "demo-pump-stable"), (True, "demo-pump-change")):
        source_id = asset + "-csv"
        raw = csv_bytes(changing)
        path = root / "inputs" / (asset + ".csv")
        path.write_bytes(raw)
        bindings = tuple(
            ChannelSemanticBinding(
                source_id=source_id,
                channel_id=channel,
                version="showcase-synthetic-v1",
                definition=MeasurementDefinition(
                    property_name,
                    unit=unit,
                    unit_evidence="synthetic generator definition",
                ),
                interpretation_evidence="constructed example; not a physical measurement",
            )
            for channel, (property_name, unit) in CHANNELS.items()
        )
        JsonSourceRepository(workspace.source_registry_path).register(
            RegisteredSource(
                source_id=source_id,
                name="합성 펌프 · " + ("변화 기록" if changing else "일정한 기록"),
                registered_at=START,
                config=FileSourceConfig(
                    source_path=str(path),
                    asset_id=asset,
                    channel_columns=tuple(CHANNELS),
                    asset_display_name="변화가 있는 합성 펌프" if changing else "일정한 합성 펌프",
                    timestamp_column="timestamp",
                    semantic_bindings=bindings,
                ),
            )
        )

        def action(route: str, payload: dict[str, object]) -> dict[str, object]:
            return execute_web_source_action(root, "/api/v1/" + route, payload)

        action("sources/lifecycle", {"source_id": source_id, "target_state": "active"})
        received = action("sources/file/receive", {"source_id": source_id})
        if received["cycle_state"] != "succeeded":
            raise RuntimeError(f"Synthetic CSV validation failed: {received}")
        stored = action("sources/file/backfill", {"source_id": source_id})
        analysis = action("analysis/file", {"source_id": source_id})
        if changing:
            review = action(
                "reviews/request",
                {
                    "analysis_run_id": analysis["analysis_run_id"],
                    "evidence_id": analysis["evidence_id"],
                },
            )
            action(
                "reviews/action",
                {
                    "finding_id": review["finding_id"],
                    "action": "note",
                    "note": "시연용 검토 메모: 두 기간에서 전류와 온도가 함께 변했습니다. "
                    "실제 설비라면 운전 부하와 계측 조건부터 확인합니다. 고장 진단은 아닙니다.",
                },
            )
        sources.append(
            {
                "asset_id": asset,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "rows": 240,
                "stored": stored,
                "analysis": analysis,
            }
        )
    workspace.web_context_path.parent.mkdir(parents=True, exist_ok=True)
    workspace.web_context_path.write_text(
        json.dumps({"schema_version": 1, "kind": "synthetic-demo"})
    )
    manifest = {
        "schema_version": 1,
        "scenario": "synthetic-pump-change-v1",
        "kind": "synthetic",
        "start": START.isoformat(),
        "interval_seconds": 60,
        "sources": sources,
        "review": review,
        "meaning": "product walkthrough, not field performance or failure prediction",
    }
    (root / "showcase.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest
