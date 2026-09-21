from dataclasses import replace
from pathlib import Path

from industrial_phm.analysis import (
    compare_analysis_evidence,
    load_xjtu_lstm_analysis_view,
    load_xjtu_rul_analysis_view,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULTS = _REPOSITORY_ROOT / "docs" / "research" / "results"
_ANOMALY_RESULT = _RESULTS / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
_RUL_RESULT = _RESULTS / "xjtu-sy-rul-three-model-fold-1-validation-v1.json"


def test_current_xjtu_anomaly_and_rul_artifacts_are_compatible_separate_revision() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)
    prognostics = load_xjtu_rul_analysis_view(_RUL_RESULT)

    compatibility = compare_analysis_evidence(anomaly, prognostics)

    assert compatibility.compatible is True
    assert compatibility.same_code_revision is False
    assert compatibility.source_identity_verified is False
    assert compatibility.relationship == "compatible-separate-revision"
    assert "source byte identity is not recorded" in compatibility.warnings[0]
    assert "separate artifact" in compatibility.warnings[1]
    assert "code revision differs" in compatibility.warnings[2]


def test_same_revision_still_remains_separate_artifact_evidence() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)
    prognostics = load_xjtu_rul_analysis_view(_RUL_RESULT)
    prognostics = replace(
        prognostics,
        identity=replace(
            prognostics.identity,
            code_revision=anomaly.identity.code_revision,
        ),
    )

    compatibility = compare_analysis_evidence(anomaly, prognostics)

    assert compatibility.compatible is True
    assert compatibility.same_code_revision is True
    assert compatibility.relationship == "compatible-separate-artifacts"
    assert compatibility.warnings == (
        (
            "source byte identity is not recorded in these artifacts; compatibility only "
            "establishes matching declared dataset/split/population scope"
        ),
        "evidence comes from a separate artifact and must not be presented as one execution",
    )


def test_fold_mismatch_blocks_evidence_composition() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)
    prognostics = load_xjtu_rul_analysis_view(_RUL_RESULT)
    prognostics = replace(
        prognostics,
        identity=replace(prognostics.identity, fold_id="fold-2"),
    )

    compatibility = compare_analysis_evidence(anomaly, prognostics)

    assert compatibility.compatible is False
    assert compatibility.relationship == "incompatible"
    assert any(reason.startswith("fold_id differs:") for reason in compatibility.reasons)


def test_evaluation_asset_mismatch_blocks_evidence_composition() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)
    prognostics = load_xjtu_rul_analysis_view(_RUL_RESULT)
    prognostics = replace(
        prognostics,
        identity=replace(
            prognostics.identity,
            evaluation_asset_ids=("Bearing1_2", "Bearing2_2"),
        ),
    )

    compatibility = compare_analysis_evidence(anomaly, prognostics)

    assert compatibility.compatible is False
    assert any(
        reason.startswith("evaluation_asset_ids differs:")
        for reason in compatibility.reasons
    )
