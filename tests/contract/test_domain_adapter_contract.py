from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.adapters import DomainAdapter
from industrial_phm.contracts import CanonicalTimeSeries


class ExampleAdapter:
    @property
    def domain(self) -> str:
        return "example"

    def iter_series(self, source: Path) -> Iterable[CanonicalTimeSeries]:
        del source
        yield CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=[datetime(2026, 1, 1, tzinfo=UTC)],
            channels=["sensor-a"],
            values=[[1.0]],
        )


def test_structural_adapter_contract() -> None:
    adapter = ExampleAdapter()

    assert isinstance(adapter, DomainAdapter)
    assert adapter.domain == "example"
    assert len(list(adapter.iter_series(Path("unused")))) == 1
