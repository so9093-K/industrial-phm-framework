from pathlib import Path

import pytest

from industrial_phm.runtime import (
    OPERATIONS_CONFIG_SCHEMA,
    OperationsAnalysisConfig,
    OperationsCollectionConfig,
    OperationsConfigFormatError,
    OperationsRuntimeConfig,
    load_operations_runtime_config,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config


def test_operations_runtime_config_round_trips_current_schema(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    write_operations_runtime_config(path)

    assert path.read_text(encoding="utf-8") == (
        f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\n'
        "\n"
        "[collection]\n"
        "reconcile_interval_seconds = 0.5\n"
        "window_duration_seconds = 60.0\n"
        "allowed_lateness_seconds = 5.0\n"
        "\n"
        "[analysis]\n"
        "poll_interval_seconds = 5.0\n"
        'alignment = "strict"\n'
    )
    assert load_operations_runtime_config(path) == OperationsRuntimeConfig()


def test_operations_runtime_config_keeps_legacy_v1_marker_compatible(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\n', encoding="utf-8")

    assert load_operations_runtime_config(path) == OperationsRuntimeConfig()


def test_operations_runtime_config_round_trips_bounded_previous_policy(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    config = OperationsRuntimeConfig(
        collection=OperationsCollectionConfig(
            reconcile_interval_seconds=1.0,
            window_duration_seconds=30.0,
            allowed_lateness_seconds=2.0,
        ),
        analysis=OperationsAnalysisConfig(
            poll_interval_seconds=2.5,
            alignment="bounded-previous",
            max_carry_age_seconds=5.0,
            alignment_basis='device writes every phase; "carry" is bounded',
        ),
    )

    write_operations_runtime_config(path, config)

    assert load_operations_runtime_config(path) == config


@pytest.mark.parametrize(
    "content",
    [
        "schema = 1\n",
        'schema = "future-schema"\n',
        f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\nextra = true\n',
        (f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\n[collection]\nunknown = 1\n'),
        (f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\n[analysis]\nalignment = "bounded-previous"\n'),
        "not valid toml = [",
    ],
)
def test_operations_runtime_config_rejects_invalid_or_unsupported_content(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises((OperationsConfigFormatError, ValueError)):
        load_operations_runtime_config(path)
