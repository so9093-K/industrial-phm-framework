"""Shared SVG serialization for Operations matplotlib charts."""

from __future__ import annotations

import importlib
import io
import warnings
from typing import Any


def figure_svg(figure: Any, **savefig_kwargs: Any) -> str:
    """Serialize a figure as SVG with text kept as text elements.

    Glyph paths would bake in the server's font. AI-Hub channel names are Korean and
    matplotlib's default DejaVu Sans has no Hangul, so titles rendered as empty boxes.
    Text elements let the viewing browser render them with its own fonts; the layout
    still uses matplotlib's metrics, so the missing-glyph warnings are not actionable.
    """
    matplotlib = importlib.import_module("matplotlib")
    output = io.StringIO()
    with matplotlib.rc_context({"svg.fonttype": "none"}), warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Glyph \d+ .*missing from font",
            category=UserWarning,
        )
        figure.savefig(output, format="svg", **savefig_kwargs)
    return output.getvalue()
