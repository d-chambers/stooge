"""Helpers for stooge project metadata."""

from pathlib import Path
from typing import Union

import stooge
from stooge.utils import ensure_spf_project, path_or_cwd

METADATA_DIRECTORY_NAME = ".stooge"
METADATA_FILE_NAME = "spf_version.txt"
SPF_VERSION_FILE_NAME = METADATA_FILE_NAME


def _write_version(spf_path: Path) -> None:
    """Write the current stooge version metadata file."""
    with (spf_path / METADATA_FILE_NAME).open("w") as fi:
        fi.write(stooge.__version__)


def _read_version(spf_path: Path) -> str:
    """Read the stooge version metadata value."""
    with (spf_path / METADATA_FILE_NAME).open("r") as fi:
        out = fi.read().rstrip()
    return out


def write_metadata(project_path: Union[str, Path]) -> None:
    """Write project metadata for an initialized stooge project."""
    spf_path = Path(project_path) / METADATA_DIRECTORY_NAME
    spf_path.mkdir(exist_ok=True, parents=True)
    _write_version(spf_path)


def read_metadata(project_path: Union[str, Path, None]) -> dict[str, str]:
    """Read metadata from an initialized stooge project."""
    path = path_or_cwd(project_path)
    ensure_spf_project(path)
    spf_path = path / METADATA_DIRECTORY_NAME
    out = {
        "spf_version": _read_version(spf_path),
    }
    return out
