"""Packaged Monitor UI bridge; durable state stays in the Operations runtime."""

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import Any as _WidgetBase
else:
    _WidgetBase = importlib.import_module("anywidget").AnyWidget
_traitlets = importlib.import_module("traitlets")


class MonitorWidget(_WidgetBase):  # type: ignore[misc]
    _esm = Path(__file__).with_name("monitor_widget.js")
    _css = Path(__file__).with_name("monitor_widget.css")
    snapshot = _traitlets.Dict().tag(sync=True)
    event = _traitlets.Dict().tag(sync=True)

    def __init__(
        self, snapshot: dict[str, Any], on_event: Callable[[dict[str, Any]], None]
    ) -> None:
        super().__init__(snapshot=snapshot)
        self.observe(lambda change: on_event(change["new"]), names="event")
