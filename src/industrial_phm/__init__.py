"""Industrial PHM framework."""

from importlib.metadata import version

from industrial_phm.contracts import CanonicalTimeSeries

__all__ = ["CanonicalTimeSeries", "__version__"]
__version__ = version("industrial-phm-framework")
