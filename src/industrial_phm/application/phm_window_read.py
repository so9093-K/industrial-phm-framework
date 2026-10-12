"""Raw, quality-aware signal samples of exactly the window a PHM step consumed."""

from __future__ import annotations

from typing import Any

from industrial_phm.application.analysis_input import window_channel_observations
from industrial_phm.application.electrical_window_features import resolve_electrical_roles
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_read import PhmReadError
from industrial_phm.models.package import StepKind


def project_phm_window(
    store: SqlitePhmAnalysisStore,
    windows: SqliteObservationWindowRepository,
    *,
    binding_id: str,
    position: int,
) -> dict[str, Any]:
    bindings = [b for b in store.list_bindings() if b.binding_id == binding_id]
    if not bindings:
        raise PhmReadError("unknown binding")
    binding = bindings[0]
    if binding.step_kind is not StepKind.OBSERVATION_WINDOW:
        raise PhmReadError("binding does not consume observation windows")
    result = store.get_result(binding_id, position)
    if result is None:
        raise PhmReadError("step not analyzed")
    try:
        window = windows.get(str(result.input_reference["window_id"]))
    except KeyError as error:
        raise PhmReadError("stored input window unavailable") from error
    if (window.source_id, window.asset_id, window.measurement_point_id) != (
        binding.source_id,
        binding.asset_id,
        binding.measurement_point_id,
    ):
        raise PhmReadError("window does not belong to binding")
    observations = window_channel_observations(window)
    if len(observations) > 2_000:
        return {"available": False, "reason": "window exceeds preview limit"}
    roles, reason = resolve_electrical_roles(observations)
    if roles is None:
        return {"available": False, "reason": reason}
    channels = []
    for channel_id in roles.channels:
        rows = sorted(
            (o for o in observations if o.channel_id == channel_id), key=lambda o: o.event_at
        )
        first = rows[0]
        points = []
        for row in rows:
            quality = (
                "conflict"
                if row.conflicting
                else ("good" if row.source_quality_good and row.value is not None else "unusable")
            )
            points.append(
                {
                    "at": row.event_at.isoformat(),
                    "value": row.value if quality == "good" else None,
                    "quality": quality,
                }
            )
        channels.append(
            {
                "channel_id": channel_id,
                "unit": first.unit,
                "observed_property": first.observed_property,
                "scope": first.scope,
                "points": points,
            }
        )
    return {
        "schema_version": 1,
        "available": True,
        "binding_id": binding_id,
        "position": position,
        "window_id": window.window_id,
        "start": window.window_start.isoformat(),
        "end": window.window_end.isoformat(),
        "measurement_point_id": window.measurement_point_id,
        "channels": channels,
    }
