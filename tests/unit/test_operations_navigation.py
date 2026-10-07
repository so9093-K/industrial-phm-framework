from datetime import UTC, datetime

import pytest

from industrial_phm.application.operations_investigations import (
    InvestigationQueueItem,
    InvestigationQueueView,
    InvestigationReviewState,
)
from industrial_phm.application.operations_monitor import (
    OperationsAttentionDestination,
    OperationsMonitorAttention,
    OperationsMonitorStatus,
)
from industrial_phm.presentation.operations_locale import OperationsPageId
from industrial_phm.presentation.operations_navigation import (
    resolve_finding_investigation_route,
    resolve_investigation_route,
    resolve_operations_attention_route,
)

NOW = datetime(2026, 10, 4, 11, 30, tzinfo=UTC)


def _attention(
    destination: OperationsAttentionDestination,
    *,
    asset_id: str | None = None,
    finding_id: str | None = None,
) -> OperationsMonitorAttention:
    return OperationsMonitorAttention(
        attention_id=f"attention:{destination.value}",
        status=OperationsMonitorStatus.NEEDS_ATTENTION,
        title="Inspect evidence",
        detail="Evidence requires inspection.",
        destination=destination,
        occurred_at=NOW,
        asset_id=asset_id,
        finding_id=finding_id,
    )


def _queue(*, finding_id: str = "finding-1") -> InvestigationQueueView:
    return InvestigationQueueView(
        (
            InvestigationQueueItem(
                investigation_id="analysis-1:capability-1",
                analysis_run_id="analysis-1",
                asset_id="asset-1",
                source_id="source-1",
                measurement_point_id="point-1",
                capability_id="capability-1",
                evidence_id="evidence-1",
                observed_start_at=NOW,
                observed_end_at=NOW,
                completed_at=NOW,
                data_quality="no recorded issue",
                review_state=InvestigationReviewState.OPEN,
                finding_id=finding_id,
                review_updated_at=NOW,
            ),
        )
    )


def test_asset_attention_routes_to_signals_without_title_matching() -> None:
    route = resolve_operations_attention_route(
        _attention(
            OperationsAttentionDestination.ASSET_SIGNALS,
            asset_id="asset-1",
        ),
        investigation_queue=_queue(),
    )

    assert route.page == OperationsPageId.ASSETS
    assert route.asset_id == "asset-1"
    assert route.asset_section == "signals"


def test_review_attention_routes_to_exact_investigation() -> None:
    route = resolve_operations_attention_route(
        _attention(
            OperationsAttentionDestination.INVESTIGATIONS,
            asset_id="asset-1",
            finding_id="finding-1",
        ),
        investigation_queue=_queue(),
    )

    assert route.page == OperationsPageId.INVESTIGATIONS
    assert route.investigation_group_id == "asset-1:capability-1:open"
    assert route.investigation_id == "analysis-1:capability-1"


def test_system_attention_routes_without_entity_context() -> None:
    route = resolve_operations_attention_route(
        _attention(OperationsAttentionDestination.SYSTEM),
        investigation_queue=_queue(),
    )

    assert route.page == OperationsPageId.SYSTEM
    assert route.asset_id is None
    assert route.investigation_id is None


def test_review_attention_fails_closed_when_finding_is_not_in_queue() -> None:
    with pytest.raises(LookupError, match="exactly one investigation"):
        resolve_operations_attention_route(
            _attention(
                OperationsAttentionDestination.INVESTIGATIONS,
                asset_id="asset-1",
                finding_id="finding-missing",
            ),
            investigation_queue=_queue(),
        )


def test_review_finding_routes_back_to_its_exact_investigation() -> None:
    route = resolve_finding_investigation_route("finding-1", investigation_queue=_queue())

    assert route.page == OperationsPageId.INVESTIGATIONS
    assert route.investigation_group_id == "asset-1:capability-1:open"
    assert route.investigation_id == "analysis-1:capability-1"
    with pytest.raises(LookupError, match="exactly one investigation"):
        resolve_finding_investigation_route("finding-missing", investigation_queue=_queue())


def test_analysis_evidence_routes_to_exact_investigation_without_finding() -> None:
    route = resolve_investigation_route(
        "analysis-1:capability-1",
        investigation_queue=_queue(finding_id="finding-1"),
    )

    assert route.page == OperationsPageId.INVESTIGATIONS
    assert route.investigation_group_id == "asset-1:capability-1:open"
    assert route.investigation_id == "analysis-1:capability-1"

    with pytest.raises(LookupError, match="exactly one queue item"):
        resolve_investigation_route(
            "analysis-missing:capability-1",
            investigation_queue=_queue(),
        )
