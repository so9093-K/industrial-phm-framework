"""Build the Operations frontend for distributable wheels and source archives.

Editable Python installs deliberately skip this hook: ``make up`` owns their
frontend preparation. Installing a built wheel never invokes npm or this hook.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name == "wheel" and version == "editable":
            return
        npm = shutil.which("npm")
        if npm is None:
            raise RuntimeError(
                "Building from source requires Node.js >=22.12 and npm. "
                "Install them and rebuild, or install a prebuilt wheel (no Node runtime needed)."
            )
        root = Path(self.root)
        # Rebuild from the locked sources every time; a leftover bundle is not evidence
        # that the current Python distribution contains the current frontend.
        for arguments in (
            ["ci", "--prefix", "frontend", "--no-audit", "--no-fund"],
            ["run", "--prefix", "frontend", "build"],
        ):
            subprocess.run([npm, *arguments], cwd=root, check=True)
        output = root / "src/industrial_phm/apps/web_next"
        manifest = json.loads((output / "asset-manifest.json").read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, list)
            or not all(isinstance(name, str) for name in manifest)
            or len(manifest) != len(set(manifest))
            or "index.html" not in manifest
            or not any(name.endswith(".js") for name in manifest)
            or any(
                (
                    name != "index.html"
                    and not re.fullmatch(r"assets/[A-Za-z0-9_-]+\.(js|css)", name)
                )
                or not (output / name).is_file()
                for name in manifest
            )
        ):
            raise RuntimeError("Frontend build did not produce a complete static asset manifest")
        build_data["artifacts"].extend(
            f"/src/industrial_phm/apps/web_next/{name}"
            for name in ["asset-manifest.json", *manifest]
        )
