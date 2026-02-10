"""
Example utilites
"""
from pathlib import Path
from typing import Union


def ensure_folder_exists(path: Union[Path, str]) -> Path:
    """
    Given a path to a directory, ensure the directory exists.

    Returns a path to said directory.
    """
    path = Path(path)
    path.mkdir(exist_ok=True, parents=True)
    return path


def some_function():
    """Another function which might be used by multiple files."""
