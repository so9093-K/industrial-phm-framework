"""Optional asset display names declared by source registrations.

There is no separate asset registry: a source that feeds an asset may declare how the
asset is called. ``asset_id`` stays the stable identity everywhere; the display name is
only a presentation label and falls back to ``asset_id``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from industrial_phm.application.source_registration import RegisteredSource


@dataclass(frozen=True, slots=True)
class AssetDisplayNames:
    names: Mapping[str, str] = field(default_factory=dict)
    conflicts: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def name(self, asset_id: str) -> str | None:
        return self.names.get(asset_id)

    def label(self, asset_id: str) -> str:
        """Display name when one is agreed, otherwise the asset ID itself."""
        return self.names.get(asset_id, asset_id)

    def option_label(self, asset_id: str) -> str:
        """Unambiguous selector label: two assets may share a display name."""
        name = self.names.get(asset_id)
        return asset_id if name is None else f"{name} · {asset_id}"


def resolve_asset_display_names(sources: Sequence[RegisteredSource]) -> AssetDisplayNames:
    """Use a name only when every source that declares one for the asset agrees."""
    declared: dict[str, set[str]] = {}
    for source in sources:
        name = source.config.asset_display_name
        if name is not None:
            declared.setdefault(source.asset_id, set()).add(name)
    return AssetDisplayNames(
        names={
            asset_id: next(iter(names))
            for asset_id, names in sorted(declared.items())
            if len(names) == 1
        },
        conflicts={
            asset_id: tuple(sorted(names))
            for asset_id, names in sorted(declared.items())
            if len(names) > 1
        },
    )
