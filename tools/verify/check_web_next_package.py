"""Check that the compiled Web-next preview exists in the tree or the built wheel."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


def check_manifest() -> None:
    root = Path("src/industrial_phm/apps/web_next")
    files = json.loads((root / "asset-manifest.json").read_text())
    assert "index.html" in files
    assert any(name.startswith("assets/") and name.endswith(".js") for name in files)
    assert all((root / name).is_file() for name in files)


def check_wheel() -> None:
    wheel = next(Path("dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert any(name.endswith("/web_next/index.html") for name in names), names
    assert any("/web_next/assets/" in name and name.endswith(".js") for name in names), names
    assert any(name.endswith("/web_next/asset-manifest.json") for name in names), names


if __name__ == "__main__":
    {"manifest": check_manifest, "wheel": check_wheel}[sys.argv[1]]()
