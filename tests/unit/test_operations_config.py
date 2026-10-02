from pathlib import Path

import pytest

from industrial_phm.runtime import (
    OPERATIONS_CONFIG_SCHEMA,
    OPERATIONS_CONFIG_SCHEMA_V1,
    OperationsAnalysisConfig,
    OperationsCollectionConfig,
    OperationsConfigFormatError,
    OperationsRuntimeConfig,
    OperationsUiConfig,
    load_operations_runtime_config,
    upgrade_operations_runtime_config,
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
        "\n"
        "[ui]\n"
        "port = 2718\n"
    )
    assert load_operations_runtime_config(path) == OperationsRuntimeConfig()


def test_operations_runtime_config_loads_v1_with_safe_ui_default(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        (
            f'schema = "{OPERATIONS_CONFIG_SCHEMA_V1}"\n'
            "\n"
            "[collection]\n"
            "reconcile_interval_seconds = 1.0\n"
            "window_duration_seconds = 30.0\n"
            "allowed_lateness_seconds = 2.0\n"
            "\n"
            "[analysis]\n"
            "poll_interval_seconds = 2.5\n"
            'alignment = "strict"\n'
        ),
        encoding="utf-8",
    )

    config = load_operations_runtime_config(path)

    assert config.schema == OPERATIONS_CONFIG_SCHEMA
    assert config.collection == OperationsCollectionConfig(1.0, 30.0, 2.0)
    assert config.analysis == OperationsAnalysisConfig(2.5)
    assert config.ui == OperationsUiConfig()


def test_operations_runtime_config_upgrade_rewrites_v1_atomically(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f'schema = "{OPERATIONS_CONFIG_SCHEMA_V1}"\n', encoding="utf-8")

    config = upgrade_operations_runtime_config(path)

    assert config == OperationsRuntimeConfig()
    text = path.read_text(encoding="utf-8")
    assert text.startswith(f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\n')
    assert "[ui]" in text
    assert "port = 2718" in text


def test_operations_runtime_config_round_trips_bounded_previous_and_ui_policy(
    tmp_path: Path,
) -> None:
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
        ui=OperationsUiConfig(port=3818),
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
        (f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\n[ui]\nport = 0\n'),
        (f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\n[ui]\nport = "2718"\n'),
        (f'schema = "{OPERATIONS_CONFIG_SCHEMA_V1}"\n[ui]\nport = 2718\n'),
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
