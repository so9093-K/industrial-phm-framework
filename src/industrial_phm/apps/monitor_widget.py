"""Packaged Monitor UI bridge; durable state stays in the Operations runtime."""

import importlib
import logging
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
    response = _traitlets.Dict().tag(sync=True)

    def __init__(
        self, snapshot: dict[str, Any], on_event: Callable[[dict[str, Any]], bool | None]
    ) -> None:
        super().__init__(snapshot=snapshot)

        def dispatch(change: dict[str, Any]) -> None:
            event = change["new"]
            try:
                accepted = on_event(event)
            except Exception:
                logging.getLogger(__name__).exception("Monitor view action failed")
                self.response = {
                    "sequence": event.get("sequence"),
                    "status": "error",
                    "message": "The view update failed. Refresh and try again.",
                }
            else:
                self.response = {
                    "sequence": event.get("sequence"),
                    "status": "rejected" if accepted is False else "ok",
                    "message": "This selection is unavailable. Refresh the view."
                    if accepted is False
                    else "",
                }

        self.observe(dispatch, names="event")
