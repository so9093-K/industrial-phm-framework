"""Typed manifest for reproducible public-dataset acquisition."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

ProviderKind = Literal["manual", "url"]


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """Authoritative acquisition metadata for one external dataset."""

    dataset_id: str
    title: str
    version: str
    provider: ProviderKind
    source_url: str
    citation_doi: str | None
    license_name: str
    archive_name: str | None = None
    sha256: str | None = None

    @classmethod
    def from_toml(cls, content: str) -> DatasetManifest:
        raw = tomllib.loads(content)
        provider = _required_str(raw, "provider")
        if provider not in {"manual", "url"}:
            raise ValueError(f"unsupported dataset provider: {provider!r}")

        archive_name = _optional_str(raw, "archive_name")
        if provider == "url" and archive_name is None:
            raise ValueError("url dataset provider requires archive_name")

        sha256 = _optional_str(raw, "sha256")
        if sha256 is not None:
            normalized = sha256.lower()
            if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
                raise ValueError("sha256 must be a 64-character hexadecimal digest")
            sha256 = normalized

        return cls(
            dataset_id=_required_str(raw, "id"),
            title=_required_str(raw, "title"),
            version=_required_str(raw, "version"),
            provider=cast(ProviderKind, provider),
            source_url=_required_str(raw, "source_url"),
            citation_doi=_optional_str(raw, "citation_doi"),
            license_name=_required_str(raw, "license"),
            archive_name=archive_name,
            sha256=sha256,
        )


def _required_str(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"manifest field {key!r} must be a non-empty string")
    return value.strip()


def _optional_str(values: Mapping[str, object], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"manifest field {key!r} must be a non-empty string when provided")
    return value.strip()
