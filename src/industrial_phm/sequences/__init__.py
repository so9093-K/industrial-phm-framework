"""Dataset-neutral feature-sequence construction contracts."""

from industrial_phm.sequences.window import (
    SequenceAlignment,
    SequenceConstruction,
    SequenceFeatureObservation,
    SequenceWindow,
    SequenceWindowError,
    SequenceWindowSpec,
    construct_sequence_windows,
)

__all__ = [
    "SequenceAlignment",
    "SequenceConstruction",
    "SequenceFeatureObservation",
    "SequenceWindow",
    "SequenceWindowError",
    "SequenceWindowSpec",
    "construct_sequence_windows",
]
