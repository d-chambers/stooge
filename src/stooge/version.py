"""Runtime package version helpers for stooge."""

from importlib.metadata import PackageNotFoundError, version

# This resolves the SCM-derived version from installed package metadata.
try:
    __version__ = version("stooge")
except PackageNotFoundError:
    # Fallback for local source execution before installation/build.
    __version__ = "0.0.0"
