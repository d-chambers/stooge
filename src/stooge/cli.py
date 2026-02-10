"""
Port's CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from stooge.info import info as info_project
from stooge.init import init as init_project
from stooge.version import __version__

app = typer.Typer(help="CLI for stooge project scaffolding.")


@app.command("init")
def init(path: Optional[Path] = typer.Argument(None)):
    """Create or initialize a stooge project directory."""
    project_path = init_project(path)
    typer.echo(str(project_path))


@app.command("info")
def info(path: Optional[Path] = typer.Argument(None)):
    """Show metadata for a stooge project."""
    data = info_project(path)
    typer.echo(json.dumps(data))


@app.command("version")
def version():
    """Print the installed stooge version."""
    typer.echo(__version__)


def main():
    """Entrypoint used by executable wrappers."""
    app()


if __name__ == "__main__":
    main()
