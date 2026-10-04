"""Framework-neutral routing for Operations attention drill-downs."""

from __future__ import annotations

from dataclasses import dataclass

from industrial_phm.application.operations_investigations import InvestigationQueueView
from industrial_phm.application.operations_monitor import (
    OperationsAttentionDestination,
    OperationsMonitorAttention,
)


@dataclass(frozen=True, slots=True)
class OperationsAttentionRoute:
    """Concrete UI destination resolved from one typed monitor attention."""

    page: str
    asset_id: str | None = None
    asset_section: str | None = None
    investigation_group_id: str | None = None
    investigation_id: str | None = None

    def __post_init__(self) -> None:
        if self.page not in {"Assets", "Investigations", "System"}:
            raise ValueError("unsupported Operations attention route page")
        if self.page == "Assets":
            if self.asset_id is None or self.asset_section != "Signals":
                raise ValueError("Assets attention route requires asset Signals context")
        elif self.page == "Investigations":
            if self.investigation_group_id is None or self.investigation_id is None:
                raise ValueError("Investigations route requires exact queue selection")
        elif any(
            value is not None
            for value in (
                self.asset_id,
                self.asset_section,
                self.investigation_group_id,
                self.investigation_id,
            )
        ):
            raise ValueError("System attention route must not carry workspace selection")


def resolve_operations_attention_route(
    attention: OperationsMonitorAttention,
    *,
    investigation_queue: InvestigationQueueView,
) -> OperationsAttentionRoute:
    """Resolve typed attention intent without inspecting user-facing title text."""

    if not isinstance(attention, OperationsMonitorAttention):
        raise ValueError("attention must be an OperationsMonitorAttention")
    if not isinstance(investigation_queue, InvestigationQueueView):
        raise ValueError("investigation_queue must be an InvestigationQueueView")

    if attention.destination == OperationsAttentionDestination.ASSET_SIGNALS:
        if attention.asset_id is None:
            raise AssertionError("validated asset-signals attention is missing asset_id")
        return OperationsAttentionRoute(
            page="Assets",
            asset_id=attention.asset_id,
            asset_section="Signals",
        )
    if attention.destination == OperationsAttentionDestination.SYSTEM:
        return OperationsAttentionRoute(page="System")

    finding_id = attention.finding_id
    if finding_id is None:
        raise AssertionError("validated investigations attention is missing finding_id")
    matches = tuple(item for item in investigation_queue.items if item.finding_id == finding_id)
    if len(matches) != 1:
        raise LookupError(
            f"attention finding must resolve to exactly one investigation: {finding_id}"
        )
    item = matches[0]
    group = next(
        (
            candidate
            for candidate in investigation_queue.groups()
            if any(member.investigation_id == item.investigation_id for member in candidate.items)
        ),
        None,
    )
    if group is None:
        raise LookupError(f"investigation group is unavailable: {item.investigation_id}")
    return OperationsAttentionRoute(
        page="Investigations",
        investigation_group_id=group.group_id,
        investigation_id=item.investigation_id,
    )
