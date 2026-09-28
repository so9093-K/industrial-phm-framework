"""Developer-only AI-Hub acquisition helper.

This module deliberately lives outside ``industrial_phm``. It prepares local vendor
archives for development and research without making AI-Hub a runtime dependency of
the framework.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DATA_ROOT_ENV = "INDUSTRIAL_PHM_DATA_DIR"
API_KEY_ENV = "AIHUB_APIKEY"
SHELL_PATH_ENV = "AIHUBSHELL_PATH"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRESET_ROOT = Path(__file__).resolve().parent / "presets"
_FILE_LINE = re.compile(
    r"(?P<filename>\d+\.(?P<equipment>.+)\.zip)\s*\|\s*"
    r"(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>[KMGT]?B)\s*\|\s*"
    r"(?P<filekey>\d+)\s*$"
)
_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AIHubToolError(RuntimeError):
    """Raised when acquisition tooling cannot safely continue."""


@dataclass(frozen=True, slots=True)
class InventoryFile:
    """One file exposed by the AI-Hub file-tree listing."""

    path: str
    filekey: int
    declared_size: str
    declared_size_bytes_approx: int
    split: str
    role: str
    equipment_group: str
    filename: str


@dataclass(frozen=True, slots=True)
class PresetFile:
    """One explicitly selected remote archive."""

    filekey: int
    remote_path: str
    archive_name: str
    split: str
    role: str
    equipment_group: str
    declared_size: str
    declared_size_bytes_approx: int


def load_local_env(path: Path | None = None) -> None:
    """Load simple KEY=VALUE entries without overriding the process environment."""

    env_path = path or _REPO_ROOT / ".env"
    if not env_path.is_file():
        return

    for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise AIHubToolError(f"invalid .env entry at line {line_number}")

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not _ENV_KEY.fullmatch(key):
            raise AIHubToolError(f"invalid .env key at line {line_number}")

        if value[:1] in {'"', "'"}:
            quote = value[0]
            if len(value) < 2 or value[-1] != quote:
                raise AIHubToolError(f"unterminated quoted .env value at line {line_number}")
            value = value[1:-1]

        os.environ.setdefault(key, value)


def default_data_root() -> Path:
    """Return the existing project data-root override or the repository raw-data default."""

    configured = os.environ.get(DATA_ROOT_ENV)
    return Path(configured) if configured else Path("data/raw")


def parse_inventory(text: str, *, dataset_key: int) -> tuple[InventoryFile, ...]:
    """Parse the file lines emitted by ``aihubshell -mode l``."""

    split: str | None = None
    role: str | None = None
    result: list[InventoryFile] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if "1.Training" in line:
            split = "training"
            role = None
            continue
        if "2.Validation" in line:
            split = "validation"
            role = None
            continue
        if "원천데이터" in line and "|" not in line:
            role = "raw"
            continue
        if "라벨링데이터" in line and "|" not in line:
            role = "label"
            continue

        match = _FILE_LINE.search(line)
        if match is None:
            continue
        if split is None or role is None:
            raise AIHubToolError(
                f"dataset {dataset_key} file appeared before split/role context: {line}"
            )

        size_number = float(match.group("size"))
        size_unit = match.group("unit")
        size_bytes = _approximate_bytes(size_number, size_unit)
        filename = match.group("filename")
        result.append(
            InventoryFile(
                path=f"{split}/{role}/{filename}",
                filekey=int(match.group("filekey")),
                declared_size=f"{match.group('size')} {size_unit}",
                declared_size_bytes_approx=size_bytes,
                split=split,
                role=role,
                equipment_group=match.group("equipment"),
                filename=filename,
            )
        )

    if not result:
        raise AIHubToolError(f"dataset {dataset_key} listing contained no downloadable files")
    if len({item.filekey for item in result}) != len(result):
        raise AIHubToolError(f"dataset {dataset_key} listing contains duplicate filekeys")
    return tuple(result)


def build_parser() -> argparse.ArgumentParser:
    """Build the developer-tool command surface."""

    parser = argparse.ArgumentParser(prog="aihub-acquire")
    subcommands = parser.add_subparsers(dest="command", required=True)

    inventory = subcommands.add_parser("inventory", help="refresh remote file inventory")
    inventory.add_argument("dataset_key", type=int)
    _add_root_argument(inventory)

    plan = subcommands.add_parser("plan", help="show a preset download plan without network I/O")
    plan.add_argument("dataset_key", type=int)
    plan.add_argument("--preset", default="bootstrap")
    _add_root_argument(plan)

    download = subcommands.add_parser("download", help="download selected archives explicitly")
    download.add_argument("dataset_key", type=int)
    download.add_argument("--preset", default="bootstrap")
    download.add_argument("--force", action="store_true")
    _add_root_argument(download)

    verify = subcommands.add_parser(
        "verify",
        help="record or verify local SHA-256 provenance for selected archives",
    )
    verify.add_argument("dataset_key", type=int)
    verify.add_argument("--preset", default="bootstrap")
    _add_root_argument(verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the acquisition tool and convert expected failures to a stable exit code."""

    load_local_env()
    args = build_parser().parse_args(argv)

    try:
        if args.command == "inventory":
            return _run_inventory(args.dataset_key, args.root)
        if args.command == "plan":
            return _run_plan(args.dataset_key, args.preset, args.root)
        if args.command == "download":
            return _run_download(args.dataset_key, args.preset, args.root, force=args.force)
        if args.command == "verify":
            return _run_verify(args.dataset_key, args.preset, args.root)
    except AIHubToolError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    raise AssertionError(f"unhandled command: {args.command}")


def _run_inventory(dataset_key: int, root: Path) -> int:
    shell = resolve_aihub_shell()
    completed = subprocess.run(
        [str(shell), "-mode", "l", "-datasetkey", str(dataset_key)],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "aihubshell returned a non-zero exit status"
        raise AIHubToolError(f"inventory request failed: {detail}")

    files = parse_inventory(completed.stdout, dataset_key=dataset_key)
    target = _dataset_root(root, dataset_key) / "inventory"
    target.mkdir(parents=True, exist_ok=True)

    raw_path = target / "file-tree.txt"
    json_path = target / "inventory.json"
    raw_path.write_text(completed.stdout, encoding="utf-8")
    _write_json(
        json_path,
        {
            "schema_version": 1,
            "dataset_key": dataset_key,
            "observed_at": _utc_now(),
            "source_command": f"aihubshell -mode l -datasetkey {dataset_key}",
            "files": [asdict(item) for item in files],
        },
    )

    print(f"inventory: {len(files)} file(s)")
    print(f"raw listing: {raw_path}")
    print(f"machine inventory: {json_path}")
    return 0


def _run_plan(dataset_key: int, preset_name: str, root: Path) -> int:
    selected = _select_preset(dataset_key, preset_name)
    print(f"AI-Hub dataset {dataset_key} preset: {preset_name}")
    print(f"destination: {_dataset_root(root, dataset_key) / 'archives'}")
    print("")

    total = 0
    for item in selected:
        total += item.declared_size_bytes_approx
        print(
            f"{item.filekey}  {item.split}/{item.role}  "
            f"{item.equipment_group}  {item.declared_size}"
        )
    print("")
    print(f"declared total: ~{_format_bytes(total)}")
    print("note: totals are approximate because AI-Hub listing sizes are rounded")
    print("no network request was made")
    return 0


def _run_download(
    dataset_key: int,
    preset_name: str,
    root: Path,
    *,
    force: bool,
) -> int:
    selected = _select_preset(dataset_key, preset_name)
    shell = resolve_aihub_shell()
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        raise AIHubToolError(
            f"{API_KEY_ENV} is required for downloads; set it in the environment or .env"
        )

    dataset_root = _dataset_root(root, dataset_key)
    records = _read_local_manifest(dataset_root)
    by_filekey = {int(record["filekey"]): record for record in records}

    for item in selected:
        destination = _archive_path(dataset_root, item)
        existing = by_filekey.get(item.filekey)
        if destination.is_file() and not force:
            if existing is None:
                raise AIHubToolError(
                    f"untracked archive already exists: {destination}; "
                    "run verify first or use --force"
                )
            observed = _inspect_file(destination)
            if observed["sha256"] != existing.get("sha256"):
                raise AIHubToolError(
                    f"local archive changed since manifest was recorded: {destination}"
                )
            print(f"skip verified local archive: {destination}")
            continue

        if force and destination.exists():
            destination.unlink()

        staging = dataset_root / "staging" / str(item.filekey)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        command = [
            str(shell),
            "-mode",
            "d",
            "-datasetkey",
            str(dataset_key),
            "-filekey",
            str(item.filekey),
        ]
        completed = subprocess.run(
            command,
            cwd=staging,
            check=False,
            env=os.environ.copy(),
        )
        if completed.returncode != 0:
            raise AIHubToolError(
                f"download failed for filekey {item.filekey} with exit "
                f"status {completed.returncode}"
            )

        matches = tuple(staging.rglob(item.archive_name))
        if len(matches) != 1:
            raise AIHubToolError(
                f"expected one {item.archive_name!r} after download, found {len(matches)}"
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(matches[0]), destination)
        shutil.rmtree(staging, ignore_errors=True)

        integrity = _inspect_file(destination)
        record = _local_record(
            dataset_key=dataset_key,
            item=item,
            integrity=integrity,
            acquisition="downloaded",
        )
        records = _replace_record(records, record)
        _write_local_manifest(dataset_root, dataset_key, records)
        by_filekey[item.filekey] = record
        print(f"downloaded: {destination}")
        print(f"sha256: {integrity['sha256']}")

    return 0


def _run_verify(dataset_key: int, preset_name: str, root: Path) -> int:
    selected = _select_preset(dataset_key, preset_name)
    dataset_root = _dataset_root(root, dataset_key)
    records = _read_local_manifest(dataset_root)
    by_filekey = {int(record["filekey"]): record for record in records}

    for item in selected:
        path = _archive_path(dataset_root, item)
        if not path.is_file():
            raise AIHubToolError(f"selected archive is missing: {path}")

        integrity = _inspect_file(path)
        existing = by_filekey.get(item.filekey)
        if existing is not None and existing.get("sha256") != integrity["sha256"]:
            raise AIHubToolError(f"checksum mismatch against local manifest: {path}")

        if existing is None:
            record = _local_record(
                dataset_key=dataset_key,
                item=item,
                integrity=integrity,
                acquisition="preexisting-local",
            )
            records = _replace_record(records, record)
            by_filekey[item.filekey] = record
            print(f"recorded local provenance: {path}")
        else:
            print(f"verified local provenance: {path}")

        print(f"sha256: {integrity['sha256']}")

    _write_local_manifest(dataset_root, dataset_key, records)
    print("upstream checksum: not provided by this preset")
    return 0


def resolve_aihub_shell() -> Path:
    """Resolve the official shell without downloading executables implicitly."""

    configured = os.environ.get(SHELL_PATH_ENV)
    if configured:
        path = Path(configured).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise AIHubToolError(f"{SHELL_PATH_ENV} is not an executable file: {path}")

    on_path = shutil.which("aihubshell")
    if on_path:
        return Path(on_path)

    home_candidate = Path.home() / "aihubshell"
    if home_candidate.is_file() and os.access(home_candidate, os.X_OK):
        return home_candidate

    raise AIHubToolError(
        "aihubshell was not found; set AIHUBSHELL_PATH or place it on PATH"
    )


def _select_preset(dataset_key: int, preset_name: str) -> tuple[PresetFile, ...]:
    raw = _read_preset(dataset_key)
    presets = raw.get("presets")
    if not isinstance(presets, dict) or preset_name not in presets:
        raise AIHubToolError(f"unknown preset {preset_name!r} for dataset {dataset_key}")

    selected_keys = presets[preset_name]
    if not isinstance(selected_keys, list) or not all(\n        isinstance(key, int) for key in selected_keys\n    ):
        raise AIHubToolError(f"invalid preset {preset_name!r} for dataset {dataset_key}")

    raw_files = raw.get("files")
    if not isinstance(raw_files, list):
        raise AIHubToolError(f"dataset {dataset_key} preset has no file catalog")

    catalog: dict[int, PresetFile] = {}
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            raise AIHubToolError(f"dataset {dataset_key} preset contains an invalid file entry")
        item = _parse_preset_file(raw_file)
        if item.filekey in catalog:
            raise AIHubToolError(f"dataset {dataset_key} preset repeats filekey {item.filekey}")
        catalog[item.filekey] = item

    missing = [key for key in selected_keys if key not in catalog]
    if missing:
        raise AIHubToolError(
            f"preset {preset_name!r} references unknown filekeys: {missing}"
        )
    return tuple(catalog[key] for key in selected_keys)


def _read_preset(dataset_key: int) -> dict[str, Any]:
    path = _PRESET_ROOT / f"dataset-{dataset_key}.json"
    if not path.is_file():
        raise AIHubToolError(f"no acquisition preset is registered for dataset {dataset_key}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("dataset_key") != dataset_key:
        raise AIHubToolError(f"invalid acquisition preset: {path}")
    return raw


def _parse_preset_file(raw: dict[str, Any]) -> PresetFile:
    try:
        return PresetFile(
            filekey=int(raw["filekey"]),
            remote_path=str(raw["remote_path"]),
            archive_name=str(raw["archive_name"]),
            split=str(raw["split"]),
            role=str(raw["role"]),
            equipment_group=str(raw["equipment_group"]),
            declared_size=str(raw["declared_size"]),
            declared_size_bytes_approx=int(raw["declared_size_bytes_approx"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AIHubToolError("invalid acquisition preset file entry") from error


def _archive_path(dataset_root: Path, item: PresetFile) -> Path:
    return dataset_root / "archives" / item.split / item.role / item.archive_name


def _dataset_root(root: Path, dataset_key: int) -> Path:
    return root / "aihub" / str(dataset_key)


def _local_record(
    *,
    dataset_key: int,
    item: PresetFile,
    integrity: dict[str, int | str],
    acquisition: str,
) -> dict[str, Any]:
    return {
        "dataset_key": dataset_key,
        "filekey": item.filekey,
        "remote_path": item.remote_path,
        "archive_name": item.archive_name,
        "split": item.split,
        "role": item.role,
        "equipment_group": item.equipment_group,
        "bytes": integrity["bytes"],
        "sha256": integrity["sha256"],
        "acquisition": acquisition,
        "recorded_at": _utc_now(),
    }


def _read_local_manifest(dataset_root: Path) -> list[dict[str, Any]]:
    path = dataset_root / "local-manifest.json"
    if not path.is_file():
        return []

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise AIHubToolError(f"unsupported local manifest: {path}")
    archives = raw.get("archives")
    if not isinstance(archives, list) or not all(isinstance(item, dict) for item in archives):
        raise AIHubToolError(f"invalid local manifest archive list: {path}")
    return list(archives)


def _write_local_manifest(
    dataset_root: Path,
    dataset_key: int,
    records: list[dict[str, Any]],
) -> None:
    _write_json(
        dataset_root / "local-manifest.json",
        {
            "schema_version": 1,
            "dataset_key": dataset_key,
            "archives": sorted(records, key=lambda record: int(record["filekey"])),
        },
    )


def _replace_record(
    records: list[dict[str, Any]],
    new_record: dict[str, Any],
) -> list[dict[str, Any]]:
    filekey = int(new_record["filekey"])
    return [record for record in records if int(record["filekey"]) != filekey] + [new_record]


def _inspect_file(path: Path) -> dict[str, int | str]:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _approximate_bytes(size: float, unit: str) -> int:
    multiplier = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
    }
    try:
        return int(size * multiplier[unit])
    except KeyError as error:
        raise AIHubToolError(f"unsupported AI-Hub display size unit: {unit}") from error


def _format_bytes(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=default_data_root(),
        help=f"local data root (default: ${DATA_ROOT_ENV} or data/raw)",
    )


if __name__ == "__main__":
    raise SystemExit(main())
