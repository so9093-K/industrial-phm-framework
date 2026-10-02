"""Packaged interactive applications distributed with industrial-phm."""

from pathlib import Path


def operations_app_path() -> Path:
    """Return the installed Operations marimo application path."""
    return Path(__file__).with_name("operations_v2.py")


__all__ = ["operations_app_path"]
