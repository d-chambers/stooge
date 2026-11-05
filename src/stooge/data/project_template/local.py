"""
# {{ project_name }}

Stooge reads this file statically. Define paths using ``Path`` string literals,
``Path(__file__).parent``, aliases, and ``/`` joins with strings or static paths.
Private helpers can derive public paths without becoming tracked artifacts.
Keep this file free of side effects and project-module imports.
"""

from pathlib import Path

# The base path for this project.
project_path = Path(__file__).parent

# External inputs to the project.
input_path = project_path / "inputs"

# Outputs produced by project tasks.
output_path = project_path / "outputs"
a010_first_output = output_path / "a010_first_output.txt"
