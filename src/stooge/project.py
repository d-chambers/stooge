"""
Read/write support for project structure.
"""
import tomllib
from dataclasses import dataclass
from pathlib import Path


def _get_mtimes(files_or_folders) -> tuple[list[float], list[float]]:
    """
    Get timestamps for files or folders.
    If a folder, find the most recent mtime, including files and folders inside.
    """

    def _get_min_max(entry):
        path = Path(entry)
        if path.is_file():
            return (entry.stat().st_mtime, entry.stat().st_mtime)
        # Go through the contents of the directory; return the min/max modified times.
        time = path.stat().st_mtime
        min_time, max_time = time, time
        # iterate through contents, update min/max times.
        for sub in path.rglob("*"):
            subtime = sub.stat().st_mtime
            if subtime < min_time:
                min_time = subtime
            if subtime > max_time:
                max_time = subtime
        return min_time, max_time

    min_times, max_times = [], []
    for entry in files_or_folders:
        min_time, max_time = _get_min_max(entry)
        min_times.append(min_time)
        max_times.append(max_time)
    return min_times, max_times


class Project(dataclass):
    """A class to encapsulate information about a project."""

    # A dict that contains the direct dependencies from one ID to another.
    dependencies: dict[str, tuple[str, ...]]
    # A mapping from an ID to the path (relative to project directory)
    script_id_path_map: dict[str, Path]
    # Output paths
    out_id_path_map: dict[str, Path]
    # Outputs that are directories rather than files
    directory_ids: set[str]
    # Time stamps of scripts/outputs (key is path not id)
    time_stamps: dict[str, float]
    # Run command
    backend: str = "uv"
    _toml_name = "stooge.toml"

    def write_toml(self, path):
        """Write the toml file containing information about the project."""

    @classmethod
    def from_path(cls, path):
        """Create a project object from the path to a stooge project."""
        # First, read existing toml, there is one, and get the back_end
        outputs = {}
        if (tomal_path := path / cls._toml_name).exists():
            tom = tomllib.load(tomal_path)
            outputs["backend"] = tom["backend"]
        # Next actually parse structure.


def _read_dependencies():
    """Read the script dependencies, parse into a dictionary."""
