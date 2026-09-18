"""Validate canonical architecture PNG assets and their documentation references."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ASSETS = (
    ROOT / "assets/system-architecture.png",
    ROOT / "assets/model-training-evaluation.png",
    ROOT / "assets/service-architecture.png",
)

REFERENCES = {
    ROOT / "README.md": ("assets/system-architecture.png",),
    ROOT / "docs/architecture/overview.md": (
        "../../assets/system-architecture.png",
        "../../assets/model-training-evaluation.png",
        "../../assets/service-architecture.png",
    ),
}

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MINIMUM_WIDTH = 1000
MINIMUM_HEIGHT = 500


def _read_chunks(payload: bytes, *, asset_name: str) -> list[tuple[bytes, bytes]]:
    chunks: list[tuple[bytes, bytes]] = []
    offset = len(PNG_SIGNATURE)

    while offset < len(payload):
        if len(payload) - offset < 12:
            raise ValueError(f"truncated PNG chunk header: {asset_name}")

        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            raise ValueError(f"truncated PNG chunk: {asset_name}")

        chunk_data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError(f"invalid PNG chunk checksum: {asset_name}")

        chunks.append((chunk_type, chunk_data))
        offset = crc_end
        if chunk_type == b"IEND":
            if offset != len(payload):
                raise ValueError(f"unexpected data after PNG IEND: {asset_name}")
            break

    return chunks


def validate_asset(path: Path) -> None:
    asset_name = path.relative_to(ROOT).as_posix()
    if not path.is_file():
        raise ValueError(f"missing architecture asset: {asset_name}")

    payload = path.read_bytes()
    if not payload.startswith(PNG_SIGNATURE):
        raise ValueError(f"invalid PNG signature: {asset_name}")

    chunks = _read_chunks(payload, asset_name=asset_name)
    if not chunks or chunks[0][0] != b"IHDR" or len(chunks[0][1]) != 13:
        raise ValueError(f"missing valid PNG IHDR: {asset_name}")
    if chunks[-1][0] != b"IEND":
        raise ValueError(f"missing PNG IEND: {asset_name}")

    width, height = struct.unpack(">II", chunks[0][1][:8])
    if width < MINIMUM_WIDTH or height < MINIMUM_HEIGHT:
        raise ValueError(f"architecture asset canvas is too small: {asset_name} ({width}x{height})")


def validate_references(path: Path, expected: tuple[str, ...]) -> None:
    content = path.read_text(encoding="utf-8")
    for reference in expected:
        if reference not in content:
            raise ValueError(f"missing asset reference {reference!r} in {path.relative_to(ROOT)}")


if __name__ == "__main__":
    for asset in ASSETS:
        validate_asset(asset)
    for document, references in REFERENCES.items():
        validate_references(document, references)
    print(f"validated {len(ASSETS)} architecture PNG assets")
