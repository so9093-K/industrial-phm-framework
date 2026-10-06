from datetime import UTC, datetime

from industrial_phm.application.operations_investigations import (
    InvestigationQueueGroup,
    InvestigationQueueItem,
    InvestigationReviewState,
)
from industrial_phm.presentation.operations_investigations import (
    investigation_capability_label,
    investigation_group_option_label,
    investigation_queue_option_label,
    investigation_review_label,
    investigation_workspace_css,
    render_investigation_evidence_identity_html,
    render_investigation_summary_html,
)
from industrial_phm.presentation.operations_shell import operations_theme_css

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _item() -> InvestigationQueueItem:
    return InvestigationQueueItem(
        investigation_id="run-1:three-phase-unbalance-v1",
        analysis_run_id="run-1",
        asset_id="boiler-01",
        source_id="source-a",
        measurement_point_id="panel-main",
        capability_id="three-phase-unbalance-v1",
        evidence_id="evidence-1",
        observed_start_at=NOW,
        observed_end_at=NOW,
        completed_at=NOW,
        data_quality="good",
        review_state=InvestigationReviewState.OPEN,
        finding_id="finding-1",
    )


def test_queue_option_uses_user_label_but_keeps_identity() -> None:
    label = investigation_queue_option_label(_item())

    assert "boiler-01" in label
    assert "Three-phase unbalance" in label
    assert "Open" in label
    assert "run-1" not in label


def test_group_option_summarizes_many_runs_without_hiding_exact_items() -> None:
    item = _item()
    group = InvestigationQueueGroup(
        group_id="boiler-01:three-phase-unbalance-v1:open",
        asset_id=item.asset_id,
        capability_id=item.capability_id,
        review_state=item.review_state,
        items=(item,),
    )

    label = investigation_group_option_label(group)

    assert "boiler-01" in label
    assert "Three-phase unbalance" in label
    assert "1 run(s)" in label
    assert "2026-09-30 12:00:00 UTC" in label


def test_summary_and_evidence_identity_keep_progressive_disclosure() -> None:
    item = _item()
    summary = render_investigation_summary_html(item)
    identity = render_investigation_evidence_identity_html(item)

    assert "Three-phase unbalance" in summary
    assert "run-1" not in summary
    assert "run-1" in identity
    assert "evidence-1" in identity
    assert "finding-1" in identity


def test_capability_and_review_labels_are_explicit_not_severity() -> None:
    assert (
        investigation_capability_label("field-vibration-statistical-features-v1")
        == "Vibration features"
    )
    assert investigation_review_label(InvestigationReviewState.NOT_REQUESTED) == "Not requested"
    assert "severity" not in investigation_workspace_css().lower()
    # marimo stacks default to min-width:auto; the shared theme lets every stack around
    # Operations content shrink, so wide evidence cannot push detail past the viewport.
    assert "div:has(.phm-shell)" in operations_theme_css()
