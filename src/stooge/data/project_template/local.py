"""
# {{ project_name }}

#### {Insert description of project} ####
"""
from pathlib import Path

# --- Project functions
# These are used in more than one script. Consider creating a separate utils
# module if this section gets too large. However, never import any project
# modules in local.py.


def ensure_folder_exists(path: Path) -> Path:
    """
    Given a path to a directory, ensure the directory exists.

    Returns a path to said directory.
    """
    path = Path(path)
    path.mkdir(exist_ok=True, parents=True)
    return path


# --- Project Parameters

# The base path for this project
project_path = Path(__file__).parent

# --- Inputs to project

input_path = ensure_folder_exists(project_path / "inputs")

# --- Outputs produced by project

# outputs should have the same prefix as the script which creates them (eg a010)

output_path = ensure_folder_exists(project_path / "outputs")
