from pathlib import Path

import pytest

from industrial_phm.runtime import (
    OPERATIONS_CONFIG_SCHEMA,
    OperationsConfigFormatError,
    OperationsRuntimeConfig,
    load_operations_runtime_config,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config


def test_operations_runtime_config_round_trips_current_schema(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    write_operations_runtime_config(path)

    assert path.read_text(encoding="utf-8") == (f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\n')
    assert load_operations_runtime_config(path) == OperationsRuntimeConfig()


@pytest.mark.parametrize(
    "content",
    [
        "schema = 1\n",
        'schema = "future-schema"\n',
        f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\nextra = true\n',
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
