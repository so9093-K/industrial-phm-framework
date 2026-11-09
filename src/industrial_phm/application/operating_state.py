"""Operating levels of equipment, read from the current it draws.

Current shows whether a machine is stopped and at which load it runs. The running levels are
the peaks of the record's own current distribution, not names for a type of equipment: a
compressor's unloaded and loaded running or a pump's two speeds each show as one peak. Reading
other signals within one level keeps a change of load from looking like a change of condition.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from industrial_phm.application.electrical_window_features import CURRENT_FLOOR_A

# Below this the equipment is taken as stopped, as in the electrical window features.
STOPPED_BELOW_A = CURRENT_FLOOR_A
MAX_LEVEL_BINS = 128
# A level must hold this share of the running time; a rarer one joins its neighbour.
MIN_LEVEL_SHARE = 0.05
# Two peaks stay apart only when the count between them falls below this part of the lower one.
_VALLEY_RATIO = 0.5
_MIN_RUNNING_VALUES = 30
_SMOOTHING = np.array([1.0, 4.0, 6.0, 4.0, 1.0]) / 16.0


@dataclass(frozen=True, slots=True)
class OperatingLevels:
    """Bands of a current: below ``edges[0]`` stopped, then one band per running level.

    Running level ``k`` covers ``edges[k]`` up to ``edges[k + 1]`` (the last one has no upper
    edge) and ``typical[k]`` is the median current within it.
    """

    edges: tuple[float, ...]
    typical: tuple[float, ...]


def running_bins(minimum: float, maximum: float, count: int) -> tuple[float, float, int]:
    """Equal bins over the running part of a current range.

    Args:
        minimum: The smallest current in the range.
        maximum: The largest current in the range.
        count: How many usable values the range holds.

    Returns:
        The low end and width of the bins and their number; no bins when nothing ran.
    """
    low = max(minimum, STOPPED_BELOW_A)
    if maximum <= low:
        return low, 0.0, 0
    bins = int(min(MAX_LEVEL_BINS, max(16, np.sqrt(count))))
    return low, (maximum - low) / bins, bins


def histogram_edges(low: float, width: float, bins: int) -> tuple[float, ...]:
    """Edges that split stopped from running, then the running range into ``bins`` bins."""
    return (STOPPED_BELOW_A, *(low + width * index for index in range(1, bins)))


def find_levels(low: float, width: float, counts: Sequence[int]) -> OperatingLevels:
    """Running levels from a histogram of the running current.

    Each peak of the smoothed histogram is a level. A peak whose valley to the next one is not
    deep enough, or whose level holds too little of the running time, joins its neighbour.

    Args:
        low: The low end of the first bin.
        width: The width of every bin.
        counts: Running values per bin, lowest first.

    Returns:
        The stop floor and the boundaries between levels, with each level's median current.
    """
    values = np.asarray(counts, dtype=float)
    total = float(values.sum())
    if total < _MIN_RUNNING_VALUES or width <= 0:
        return OperatingLevels((STOPPED_BELOW_A,), (_median(values, low, width),) if total else ())
    smooth = np.convolve(np.pad(values, 2), _SMOOTHING, mode="valid")
    last = len(smooth) - 1
    peaks = [
        index
        for index, height in enumerate(smooth)
        if height > 0
        and (index == 0 or height >= smooth[index - 1])
        and (index == last or height > smooth[index + 1])
    ]

    def valleys() -> list[int]:
        return [left + int(np.argmin(smooth[left : right + 1])) for left, right in pairwise(peaks)]

    while len(peaks) > 1:
        bottoms = valleys()
        depth = [
            float(smooth[bottom] / min(smooth[left], smooth[right]))
            for (left, right), bottom in zip(pairwise(peaks), bottoms, strict=True)
        ]
        shallow = int(np.argmax(depth))
        if depth[shallow] > _VALLEY_RATIO:
            left, right = peaks[shallow], peaks[shallow + 1]
            peaks.remove(left if smooth[left] < smooth[right] else right)
            continue
        cuts = [0, *(bottom + 1 for bottom in bottoms), len(values)]
        shares = [float(values[a:b].sum()) / total for a, b in pairwise(cuts)]
        rare = int(np.argmin(shares))
        if shares[rare] >= MIN_LEVEL_SHARE:
            break
        # Without its peak the deeper of its two valleys remains, so the rare level joins the
        # side it is least separated from.
        peaks.pop(rare)
    cuts = [0, *(bottom + 1 for bottom in valleys()), len(values)]
    return OperatingLevels(
        (STOPPED_BELOW_A, *(float(low + width * cut) for cut in cuts[1:-1])),
        tuple(_median(values[a:b], low + width * a, width) for a, b in pairwise(cuts)),
    )


def _median(values: np.ndarray, low: float, width: float) -> float:
    """The median of binned values, taken as the centre of the bin that holds it."""
    if width <= 0:
        return float(low)
    middle = int(np.searchsorted(np.cumsum(values), values.sum() / 2))
    return float(low + width * (middle + 0.5))


def main_current(signals: Sequence[tuple[str, str | None, str]]) -> str | None:
    """The signal whose current best shows how the equipment ran.

    A current is a signal shown in A. A declared three-phase current comes first, then any
    other current in the given order.

    Args:
        signals: ``(key, unit shown, interpretation_json)`` of one source and measurement point.

    Returns:
        The chosen key, or None when no signal is a current in A.
    """
    currents = [(key, meaning) for key, unit, meaning in signals if unit == "A"]
    if not currents:
        return None
    return min(currents, key=lambda item: _scope(item[1]) != "three-phase")[0]


def _scope(interpretation_json: str) -> str | None:
    data = json.loads(interpretation_json)
    for part in ("binding", "semantics"):
        item = data.get(part) if isinstance(data, dict) else None
        definition = item.get("definition", item) if isinstance(item, dict) else None
        if isinstance(definition, dict) and isinstance(definition.get("scope"), str):
            return str(definition["scope"])
    return None
