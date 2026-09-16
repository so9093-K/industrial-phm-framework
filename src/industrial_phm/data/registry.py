"""Registry backed by packaged dataset manifests."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from industrial_phm.data.manifest import DatasetManifest


class UnknownDatasetError(LookupError):
    """Raised when a dataset ID is not registered."""


@lru_cache(maxsize=1)
def list_datasets() -> tuple[DatasetManifest, ...]:
    """Return registered datasets sorted by stable dataset ID."""

    root = resources.files("industrial_phm.data.manifests")
    manifests = [
        DatasetManifest.from_toml(entry.read_text(encoding="utf-8"))
        for entry in root.iterdir()
        if entry.name.endswith(".toml")
    ]
    manifests.sort(key=lambda manifest: manifest.dataset_id)

    ids = [manifest.dataset_id for manifest in manifests]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset manifest IDs must be unique")

    return tuple(manifests)


def get_dataset(dataset_id: str) -> DatasetManifest:
    """Resolve one dataset manifest by its stable ID."""

    for manifest in list_datasets():
        if manifest.dataset_id == dataset_id:
            return manifest
    raise UnknownDatasetError(f"unknown dataset: {dataset_id}")
