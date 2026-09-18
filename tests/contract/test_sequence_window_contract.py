from dataclasses import FrozenInstanceError

import pytest

from industrial_phm.sequences import (
    SequenceAlignment,
    SequenceFeatureObservation,
    SequenceWindowError,
    SequenceWindowSpec,
    construct_sequence_windows,
)


def _observation(
    sequence_id: str,
    asset_id: str,
    partition_id: str,
    position: int,
    *,
    observation_id: str | None = None,
    values: tuple[float, ...] | list[float] | None = None,
) -> SequenceFeatureObservation:
    return SequenceFeatureObservation(
        sequence_id=sequence_id,
        asset_id=asset_id,
        partition_id=partition_id,
        source_observation_id=observation_id or f"{sequence_id}:observation-{position}",
        sequence_position=position,
        feature_values=(float(position), float(position + 1)) if values is None else values,
    )


def test_sequence_windows_preserve_lineage_and_right_edge_alignment() -> None:
    mutable_values = [0.0, 1.0]
    observations = (
        _observation("run-a", "asset-a", "train", 0, values=mutable_values),
        *(_observation("run-a", "asset-a", "train", position) for position in range(1, 4)),
        *(_observation("run-b", "asset-b", "validation", position) for position in range(10, 13)),
    )

    construction = construct_sequence_windows(
        observations,
        feature_set_id="features-v1",
        feature_names=("feature.a", "feature.b"),
        spec=SequenceWindowSpec(length=3, stride=1),
    )
    mutable_values[0] = 999.0

    assert construction.source_observation_count == 7
    assert construction.sequence_count == 2
    assert construction.window_count == 3
    assert construction.dropped_prefix_observation_count == 4
    assert construction.unaligned_source_observation_count == 4
    assert tuple(window.window_id for window in construction.windows) == (
        "run-a:window-0-2",
        "run-a:window-1-3",
        "run-b:window-10-12",
    )
    first = construction.windows[0]
    assert first.values[0] == (0.0, 1.0)
    assert first.source_observation_ids == (
        "run-a:observation-0",
        "run-a:observation-1",
        "run-a:observation-2",
    )
    assert first.source_positions == (0, 1, 2)
    assert first.start_source_observation_id == "run-a:observation-0"
    assert first.end_source_observation_id == "run-a:observation-2"
    assert first.aligned_source_observation_id == first.end_source_observation_id
    assert first.asset_id == "asset-a"
    assert first.partition_id == "train"
    assert first.feature_width == 2

    with pytest.raises(FrozenInstanceError):
        first.asset_id = "other"  # type: ignore[misc]


def test_sequence_stride_changes_alignment_without_crossing_sequence_boundaries() -> None:
    observations = tuple(
        _observation(sequence_id, asset_id, partition_id, position)
        for sequence_id, asset_id, partition_id in (
            ("run-a", "asset-a", "train"),
            ("run-b", "asset-b", "validation"),
        )
        for position in range(5)
    )

    construction = construct_sequence_windows(
        observations,
        feature_set_id="features-v1",
        feature_names=("feature.a", "feature.b"),
        spec=SequenceWindowSpec(length=3, stride=2),
    )

    assert tuple(
        (window.sequence_id, window.source_positions, window.aligned_source_observation_id)
        for window in construction.windows
    ) == (
        ("run-a", (0, 1, 2), "run-a:observation-2"),
        ("run-a", (2, 3, 4), "run-a:observation-4"),
        ("run-b", (0, 1, 2), "run-b:observation-2"),
        ("run-b", (2, 3, 4), "run-b:observation-4"),
    )
    assert construction.dropped_prefix_observation_count == 4
    assert construction.unaligned_source_observation_count == 6


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"length": 0}, "length must be a positive integer"),
        ({"length": True}, "length must be a positive integer"),
        ({"stride": 0}, "stride must be a positive integer"),
        ({"alignment": "right-edge"}, "supported SequenceAlignment"),
    ],
)
def test_sequence_window_spec_rejects_invalid_values(
    changes: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "length": 3,
        "stride": 1,
        "alignment": SequenceAlignment.RIGHT_EDGE,
    }
    values.update(changes)

    with pytest.raises(SequenceWindowError, match=message):
        SequenceWindowSpec(**values)  # type: ignore[arg-type]


def test_sequence_construction_rejects_interleaved_sequence_blocks() -> None:
    observations = (
        _observation("run-a", "asset-a", "train", 0),
        _observation("run-b", "asset-b", "train", 0),
        _observation("run-a", "asset-a", "train", 1),
    )

    with pytest.raises(SequenceWindowError, match="one contiguous input block"):
        construct_sequence_windows(
            observations,
            feature_set_id="features-v1",
            feature_names=("feature.a", "feature.b"),
            spec=SequenceWindowSpec(length=2, stride=1),
        )


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        (_observation("run-a", "asset-b", "train", 1), "asset boundaries"),
        (_observation("run-a", "asset-a", "validation", 1), "partition boundaries"),
        (_observation("run-a", "asset-a", "train", 2), "contiguous and ordered"),
    ],
)
def test_sequence_construction_rejects_boundary_or_position_drift(
    changed: SequenceFeatureObservation,
    message: str,
) -> None:
    observations = (
        _observation("run-a", "asset-a", "train", 0),
        changed,
    )

    with pytest.raises(SequenceWindowError, match=message):
        construct_sequence_windows(
            observations,
            feature_set_id="features-v1",
            feature_names=("feature.a", "feature.b"),
            spec=SequenceWindowSpec(length=2, stride=1),
        )


def test_sequence_construction_rejects_duplicate_source_identity() -> None:
    observations = (
        _observation("run-a", "asset-a", "train", 0, observation_id="duplicate"),
        _observation("run-a", "asset-a", "train", 1, observation_id="duplicate"),
    )

    with pytest.raises(SequenceWindowError, match="identities must be unique"):
        construct_sequence_windows(
            observations,
            feature_set_id="features-v1",
            feature_names=("feature.a", "feature.b"),
            spec=SequenceWindowSpec(length=2, stride=1),
        )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ((1.0,), "feature width must be 2"),
        ((1.0, float("nan")), "finite values"),
        ((1.0, True), "numerical values"),
    ],
)
def test_sequence_construction_rejects_invalid_feature_rows(
    values: tuple[object, ...],
    message: str,
) -> None:
    with pytest.raises(SequenceWindowError, match=message):
        observations = (
            _observation(
                "run-a",
                "asset-a",
                "train",
                0,
                values=values,  # type: ignore[arg-type]
            ),
            _observation("run-a", "asset-a", "train", 1),
        )
        construct_sequence_windows(
            observations,
            feature_set_id="features-v1",
            feature_names=("feature.a", "feature.b"),
            spec=SequenceWindowSpec(length=2, stride=1),
        )


def test_sequence_construction_requires_a_complete_window_for_every_sequence() -> None:
    observations = (
        _observation("run-a", "asset-a", "train", 0),
        _observation("run-a", "asset-a", "train", 1),
        *(_observation("run-b", "asset-b", "validation", position) for position in range(3)),
    )

    with pytest.raises(SequenceWindowError, match=r"run-a.*at least 3 observations"):
        construct_sequence_windows(
            observations,
            feature_set_id="features-v1",
            feature_names=("feature.a", "feature.b"),
            spec=SequenceWindowSpec(length=3, stride=1),
        )
