"""Verify complete frontend distributions and serve an installed wheel without Node."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

_ASSETS = "industrial_phm/apps/web_next/"
_ROOT = Path(__file__).resolve().parents[2]


def manifest_names(raw: bytes) -> list[str]:
    names = json.loads(raw)
    assert isinstance(names, list) and all(isinstance(name, str) for name in names)
    assert len(names) == len(set(names)), "duplicate manifest entry"
    assert "index.html" in names
    assert any(name.startswith("assets/") and name.endswith(".js") for name in names)
    assert all(
        name == "index.html" or re.fullmatch(r"assets/[A-Za-z0-9_-]+\.(?:js|css)", name)
        for name in names
    ), "unexpected static path"
    return names


def check_manifest() -> None:
    root = _ROOT / "src" / _ASSETS
    names = manifest_names((root / "asset-manifest.json").read_bytes())
    assert all((root / name).is_file() and (root / name).stat().st_size for name in names)


def check_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = manifest_names(archive.read(_ASSETS + "asset-manifest.json"))
        expected = {_ASSETS + name for name in ["asset-manifest.json", *names]}
        packaged = {name for name in archive.namelist() if name.startswith(_ASSETS)}
        assert expected == packaged, (expected - packaged, packaged - expected)
        assert all(archive.read(name) for name in expected)
        assert not any(
            "node_modules/" in name or name.startswith("frontend/") for name in archive.namelist()
        )


def check_installed() -> None:
    """Run in a fresh venv with PATH containing only that venv's bin directory."""
    from importlib.resources import files

    import industrial_phm
    from industrial_phm.runtime.operations_web_http import create_operations_web_read_server

    assert shutil.which("node") is None and shutil.which("npm") is None
    assert Path(industrial_phm.__file__).is_relative_to(Path(sys.prefix))
    package = files("industrial_phm.apps").joinpath("web_next")
    names = manifest_names(package.joinpath("asset-manifest.json").read_bytes())
    with tempfile.TemporaryDirectory() as temporary:
        server = create_operations_web_read_server(Path(temporary))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for name in names:
                path = "/web-next/" + ("" if name == "index.html" else name)
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
                try:
                    connection.request("GET", path)
                    response = connection.getresponse()
                    assert response.status == 200, (path, response.status)
                    assert response.getheader("Cache-Control") == "no-store"
                    assert response.read() == package.joinpath(*name.split("/")).read_bytes()
                finally:
                    connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)
    print("Installed wheel served every compiled asset without Node or checkout imports")


def check_build() -> None:
    """Exercise sdist -> wheel, installed runtime, missing npm and editable setup."""
    uv = shutil.which("uv")
    assert uv is not None, "uv is required for distribution checks"
    with tempfile.TemporaryDirectory(prefix="phm-distribution-") as temporary:
        root = Path(temporary)
        output = root / "dist"
        # uv's default builds the sdist, then builds the wheel FROM that archive.
        subprocess.run([uv, "build", "--out-dir", str(output)], cwd=_ROOT, check=True)
        wheel = next(output.glob("*.whl"))
        check_wheel(wheel)
        with tarfile.open(next(output.glob("*.tar.gz"))) as archive:
            paths = archive.getnames()
            for required in (
                "hatch_build.py",
                "uv.lock",
                "frontend/package.json",
                "frontend/package-lock.json",
            ):
                assert any(path.endswith("/" + required) for path in paths), required
            assert not any("node_modules/" in path for path in paths)
        environment = root / "runtime"
        subprocess.run([uv, "venv", "--python", sys.executable, str(environment)], check=True)
        python = environment / "bin/python"
        subprocess.run([uv, "pip", "install", "--python", str(python), str(wheel)], check=True)
        no_node = {**os.environ, "PATH": str(environment / "bin")}
        subprocess.run(
            [str(python), "-I", str(Path(__file__).resolve()), "installed"],
            cwd=root,
            env=no_node,
            check=True,
        )
        failed = subprocess.run(
            [
                uv,
                "build",
                "--wheel",
                "--python",
                sys.executable,
                "--out-dir",
                str(root / "missing-node"),
            ],
            cwd=_ROOT,
            env=no_node,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert (
            failed.returncode != 0 and "Building from source requires Node.js" in failed.stdout
        ), failed.stdout
        assert not list((root / "missing-node").glob("*.whl"))
        # Python development remains possible on a host without a frontend toolchain.
        subprocess.run(
            [uv, "pip", "install", "--python", str(python), "--no-deps", "--editable", str(_ROOT)],
            cwd=root,
            env=no_node,
            check=True,
        )
    print("sdist -> wheel, installed runtime, missing-Node refusal and editable setup passed")


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "wheel":
        check_wheel(Path(sys.argv[2]) if len(sys.argv) > 2 else next(Path("dist").glob("*.whl")))
    else:
        {"manifest": check_manifest, "build": check_build, "installed": check_installed}[action]()
