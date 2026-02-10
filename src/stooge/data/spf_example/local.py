"""
Project variables used by the example project.
"""
from pathlib import Path

# --- Project functions
# These are used in more than one script. Consider creating a separate utils
# module if this section gets too large.


def ensure_folder_exists(path: Path) -> Path:
    """
    Given a path to a directory, ensure the directory exists.

    Returns a path to said directory.
    """
    path = Path(path)
    path.mkdir(exist_ok=True, parents=True)
    return path


# The base path for this project
project_path = Path(__file__).parent

# --- Inputs to project

input_path = ensure_folder_exists(project_path / "inputs")
earthquake_csv = input_path / "bingham_earthquakes.csv"

# --- Outputs produced by project

output_path = ensure_folder_exists(project_path / "outputs")
cleaned_csv = output_path / "a010_cleaned_earthquakes.csv"
calc_csv = output_path / "a020_calculated_earthquakes.csv"
magnitude_histogram = output_path / "a030_magnitude_hist.png"
magnitude_time_plot = output_path / "a030_magnitude_time_plot"
