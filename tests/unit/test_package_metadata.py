from importlib.metadata import version

import industrial_phm
from industrial_phm.apps import operations_app_path


def test_runtime_version_matches_installed_distribution_metadata() -> None:
    assert industrial_phm.__version__ == version("industrial-phm-framework")


def test_operations_application_is_packaged_under_industrial_phm() -> None:
    path = operations_app_path()

    assert path.name == "operations.py"
    assert path.is_file()
    assert path.parent.name == "apps"
