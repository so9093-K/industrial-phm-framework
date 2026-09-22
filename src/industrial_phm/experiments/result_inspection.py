"""Read-only summaries for explicitly supported experiment result schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from industrial_phm.experiments.ims_cross_test import IMS_CROSS_TEST_RESULT_SCHEMA_ID
from industrial_phm.experiments.mimii_development import MIMII_DEVELOPMENT_RESULT_SCHEMA_ID
from industrial_phm.experiments.result_inspection_support import (
    ExperimentInspection,
    ExperimentResultInspectionError,
    InspectionFact,
    InspectionStage,
    _mapping,
    _text,
)
from industrial_phm.experiments.xjtu_holdout import XJTU_HOLDOUT_RESULT_SCHEMA_ID
from industrial_phm.experiments.xjtu_lstm_result import (
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
)
from industrial_phm.experiments.xjtu_rul_benchmark_result import (
    XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID,
)
from industrial_phm.experiments.xjtu_rul_validation_result import (
    XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID,
)

__all__ = [
    "ExperimentInspection",
    "ExperimentResultInspectionError",
    "InspectionFact",
    "InspectionStage",
    "inspect_experiment_result",
]


def inspect_experiment_result(path: Path) -> ExperimentInspection:
    """Validate and interpret one supported result artifact without modifying it."""
    try:
        document = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise ExperimentResultInspectionError(f"invalid result JSON: {error}") from error

    root = _mapping(document, "result root")
    schema_id = _text(root, "schema_id", "result root")
    if schema_id == XJTU_HOLDOUT_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.xjtu_holdout_inspection import (
            inspect_xjtu_holdout,
        )

        return inspect_xjtu_holdout(root, path)
    elif schema_id == IMS_CROSS_TEST_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.ims_cross_test_inspection import (
            inspect_ims_cross_test,
        )

        return inspect_ims_cross_test(root, path)
    elif schema_id == XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.xjtu_lstm_inspection import (
            inspect_xjtu_lstm_development,
        )

        return inspect_xjtu_lstm_development(root, path)
    elif schema_id == XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.xjtu_rul_validation_inspection import (
            inspect_xjtu_rul_three_model_validation,
        )

        return inspect_xjtu_rul_three_model_validation(root, path)
    elif schema_id == XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.xjtu_rul_benchmark_inspection import (
            inspect_xjtu_rul_lstm_benchmark,
        )

        return inspect_xjtu_rul_lstm_benchmark(root, path)
    elif schema_id == MIMII_DEVELOPMENT_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.mimii_development_inspection import (
            inspect_mimii_development,
        )

        return inspect_mimii_development(root, path)
    raise ExperimentResultInspectionError(
        f"unsupported experiment result schema_id {schema_id!r}; expected one of "
        f"{XJTU_HOLDOUT_RESULT_SCHEMA_ID!r}, {IMS_CROSS_TEST_RESULT_SCHEMA_ID!r}, "
        f"{XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID!r}, "
        f"{MIMII_DEVELOPMENT_RESULT_SCHEMA_ID!r}, "
        f"{XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID!r}, "
        f"{XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID!r}"
    )


def render_experiment_inspection_text(inspection: ExperimentInspection) -> str:
    """Render an experiment inspection for the developer-facing CLI surface."""
    lines = [
        "Experiment Result",
        f"  Schema: {inspection.schema_id}",
        f"  Status: {inspection.status}",
    ]
    for stage in inspection.stages:
        lines.extend(("", stage.name, f"  Status: {stage.status}"))
        lines.extend(f"  {fact.label}: {fact.value}" for fact in stage.facts)
        lines.extend(f"  Warning: {warning}" for warning in stage.warnings)
    return "\n".join(lines)
