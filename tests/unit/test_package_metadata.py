from importlib.metadata import version

import industrial_phm


def test_runtime_version_matches_installed_distribution_metadata() -> None:
    assert industrial_phm.__version__ == version("industrial-phm-framework")
