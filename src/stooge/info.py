"""Helpers for getting metadata from a stooge project."""

from pathlib import Path
from typing import Optional, Union

from stooge.meta import read_metadata


def info(project_path: Optional[Union[Path, str]] = None) -> dict:
    """
    Return metadata for a project.

    Parameters
    ----------
    project_path
        Path to project directory. Defaults to current working directory.

    Returns
    -------
    dict
        Metadata dictionary for the project.
    """
    data = read_metadata(project_path)
    return data
