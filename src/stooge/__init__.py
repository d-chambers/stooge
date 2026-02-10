"""stooge package exports."""

from pathlib import Path

from stooge.info import info
from stooge.init import init
from stooge.version import __version__

_template_path = Path(__file__).parent / "data" / "project_template"

__all__ = ["__version__", "_template_path", "info", "init"]
