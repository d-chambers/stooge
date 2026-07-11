"""Static path declarations for the example Stooge project."""

from pathlib import Path

project_path = Path(__file__).parent

input_path = project_path / "inputs"
earthquake_csv = input_path / "earthquakes.csv"

output_path = project_path / "outputs"
cleaned_csv = output_path / "a010_cleaned_earthquakes.csv"
calc_csv = output_path / "a020_calculated_earthquakes.csv"
magnitude_histogram = output_path / "a030_magnitude_hist.png"
magnitude_time_plot = output_path / "a030_magnitude_time_plot"
