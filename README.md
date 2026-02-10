# stooge

A simple project framework.

`stooge` enables reproducible development for local research projects, so you don't have to.

## Project structure

stooge requires a specific project structure.

An example project directory looks like this:

my_project
-> inputs/
---> some_file.csv
-> outputs/
-> local.py
-> environment.yml
-> a010_clean_data.py
-> a020_calculate.py
-> a030_visualize.py

Each script has an ID (the part of the name before the first `_`).

The file called `local.py` defines the inputs and outputs of the scripts. In this file, outputs are also given the same prefix.

For example:

```python
from pathlib import Path

input_path = Path("inputs")
output_path = Path("outputs")

raw_data_path = input_path / "raw data.csv"

a010_clean_data_path = output_path / "a010_cleaned_outputs.csv"
a020_calculated_data_path = output_path / "a020_calculated_results.csv"
a030_result_plot = output_path / "a030_result_plot.png"
```

This provides stooge with all the required information to figure out the relationships between scripts and their outputs.

## Init
Creates a stooge project skeleton.

This provides a small Rich interface to get information about the project name and backend, or they can be provided via command-line flags.

Supported backends are:
- [uv](https://docs.astral.sh/uv/)
- [miniforge](https://github.com/conda-forge/miniforge)
- [marimo](https://marimo.io/)
- python (use system python or provided interpreter path)

```bash
stooge init test_project --backend uv
```

## Run

`stooge run` runs the entire project up to and including a target ID. It automatically calculates stale or missing results that `a030` depends on.

For example:

```bash
stooge run a030
```

This first gets the directed acyclic graph (DAG) that defines `a030`'s dependencies. It then uses file output mtime values to determine if any results need to be re-run. This includes:

- Requiring that, for a given output, all dependency outputs have an mtime less than or equal to the current output.
- Requiring all outputs to have an mtime greater than or equal to the script that creates them.

Flags include:
- `--force`: rerun the specified task.
- `--force-all`: rerun all affected tasks.
- `--debug`: If true, drop into a pdb debugger on failure.

## Remove

Remove results from specified tasks.

```bash
stooge remove a020  # removes the results for a020
```

## Parse

Although typically called automatically by other commands, it can be used manually to parse script structure/dependencies and update timestamps.

```bash
stooge parse  # parse current directory, or pass a path
```

The flag `--dryrun` can be used to simply validate the project structure.


# Guiding principles
- `stooge` is always optional. A project can be fully executed by running the scripts in order. It is there when you want it, and it gets out of your way when you don't.
