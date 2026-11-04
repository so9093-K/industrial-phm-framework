"""Import one explicit AI-Hub member/time selection into common Asset History."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from industrial_phm.adapters.aihub_power_history import PowerHistoryBinding
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.aihub_history_import import (
    batch_id,
    import_history,
    selection_identity,
)

__all__ = ["batch_id", "import_history", "selection_identity"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--member", required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--end", type=datetime.fromisoformat, required=True)
    parser.add_argument("--ducklake-catalog", type=Path, required=True)
    parser.add_argument("--ducklake-data", type=Path, required=True)
    parser.add_argument(
        "--flush-every-batches",
        type=int,
        default=10,
        help="flush newly appended catalog-inlined rows to Parquet after this many batches",
    )
    args = parser.parse_args()
    try:
        binding = PowerHistoryBinding(**json.loads(args.binding.read_text()))
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(
                catalog_path=args.ducklake_catalog,
                data_path=args.ducklake_data,
            )
        )
        result = import_history(
            args.archive,
            args.member,
            binding,
            args.start,
            args.end,
            history,
            flush_every_batches=args.flush_every_batches,
        )
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
