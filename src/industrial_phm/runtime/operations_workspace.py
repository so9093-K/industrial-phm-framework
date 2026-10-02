"""Authoritative local path layout for one Operations runtime instance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class OperationsWorkspace:
    """Own deterministic non-secret paths below one local Operations root.

    The workspace defines locations only. Individual repositories remain authoritative
    for their contents, and service lifecycle is owned by a separate runtime layer.
    """

    root: Path

    @property
    def config_path(self) -> Path:
        """Return the future user-facing runtime configuration path."""
        return self.root / "config.toml"

    @property
    def source_registry_path(self) -> Path:
        return self.root / "sources.json"

    @property
    def source_runtime_path(self) -> Path:
        return self.root / "source-runtime.json"

    @property
    def collection_control_path(self) -> Path:
        return self.root / "control.sqlite"

    @property
    def acquisition_spool_path(self) -> Path:
        return self.root / "spool.sqlite"

    @property
    def acquisition_telemetry_path(self) -> Path:
        return self.root / "telemetry.sqlite"

    @property
    def window_state_path(self) -> Path:
        return self.root / "windows.sqlite"

    @property
    def analysis_ledger_path(self) -> Path:
        return self.root / "window-analysis-ledger.sqlite"

    @property
    def field_analysis_path(self) -> Path:
        return self.root / "field-analysis.json"

    @property
    def phase_unbalance_state_path(self) -> Path:
        return self.root / "phase-unbalance.sqlite"

    @property
    def analysis_runtime_path(self) -> Path:
        return self.root / "phase-unbalance-runtime.json"

    @property
    def finding_state_path(self) -> Path:
        return self.root / "findings.json"

    @property
    def maintenance_review_state_path(self) -> Path:
        return self.root / "finding-review.json"

    @property
    def history_catalog_path(self) -> Path:
        return self.root / "catalog.sqlite"

    @property
    def history_data_path(self) -> Path:
        return self.root / "data"

    @property
    def logs_path(self) -> Path:
        return self.root / "logs"

    @property
    def runtime_state_files(self) -> tuple[Path, ...]:
        """Return durable/local state files owned by this workspace layout."""
        return (
            self.source_registry_path,
            self.source_runtime_path,
            self.collection_control_path,
            self.acquisition_spool_path,
            self.acquisition_telemetry_path,
            self.window_state_path,
            self.analysis_ledger_path,
            self.field_analysis_path,
            self.phase_unbalance_state_path,
            self.analysis_runtime_path,
            self.finding_state_path,
            self.maintenance_review_state_path,
            self.history_catalog_path,
        )

    @property
    def managed_directories(self) -> tuple[Path, ...]:
        """Return directories whose creation is owned by workspace initialization."""
        return (self.root, self.history_data_path, self.logs_path)
