from importlib.metadata import version
from importlib.resources import files

import industrial_phm


def test_runtime_version_matches_installed_distribution_metadata() -> None:
    assert industrial_phm.__version__ == version("industrial-phm-framework")


def test_operations_web_application_is_packaged_under_industrial_phm() -> None:
    assets = files("industrial_phm.apps").joinpath("web")
    for name in ("index.html", "app.js", "styles.css"):
        assert assets.joinpath(name).read_bytes(), name
