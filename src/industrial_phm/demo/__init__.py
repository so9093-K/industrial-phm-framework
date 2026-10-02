"""Packaged product demos that exercise supported local runtime paths."""

from industrial_phm.demo.aihub_boiler import (
    AIHUB_BOILER_DEMO_ASSET_ID,
    AIHUB_BOILER_DEMO_DEFAULT_ARCHIVE,
    AIHUB_BOILER_DEMO_MEMBER,
    AIHUB_BOILER_DEMO_SOURCE_ID,
    AihubBoilerDemoConfig,
    AihubBoilerDemoPreparation,
    prepare_aihub_boiler_demo,
    run_aihub_boiler_demo,
)
from industrial_phm.demo.synthetic import (
    SYNTHETIC_DEMO_ASSET_ID,
    SYNTHETIC_DEMO_SOURCE_ID,
    SyntheticDemoConfig,
    SyntheticDemoPreparation,
    prepare_synthetic_demo,
    run_synthetic_demo,
)

__all__ = [
    "AIHUB_BOILER_DEMO_ASSET_ID",
    "AIHUB_BOILER_DEMO_DEFAULT_ARCHIVE",
    "AIHUB_BOILER_DEMO_MEMBER",
    "AIHUB_BOILER_DEMO_SOURCE_ID",
    "AihubBoilerDemoConfig",
    "AihubBoilerDemoPreparation",
    "SYNTHETIC_DEMO_ASSET_ID",
    "SYNTHETIC_DEMO_SOURCE_ID",
    "SyntheticDemoConfig",
    "SyntheticDemoPreparation",
    "prepare_aihub_boiler_demo",
    "prepare_synthetic_demo",
    "run_aihub_boiler_demo",
    "run_synthetic_demo",
]
