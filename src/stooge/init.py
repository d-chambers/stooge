"""Code for creating new stooge projects."""

from pathlib import Path
from typing import Optional, Union

import jinja2

import stooge
from stooge.meta import write_metadata


def _init_directory(
    template_directory: Path, output_directory: Path, data: dict
) -> None:
    """Render each template file into the output directory."""
    for path in Path(template_directory).rglob("*"):
        if path.is_dir():
            continue
        template_contents = path.read_text()
        template = jinja2.Template(template_contents)
        out = template.render(data)
        new_path = output_directory / path.relative_to(template_directory)
        if new_path.exists():
            continue
        new_path.parent.mkdir(exist_ok=True, parents=True)
        # Do not copy example script if an a010 script already exists.
        is_a010 = new_path.name.startswith("a010")
        has_a010 = bool(list(output_directory.glob("a010*.py")))
        if is_a010 and has_a010:
            continue
        with new_path.open("w") as fi:
            fi.write(out)


def init(path: Optional[Union[Path, str]] = None) -> Path:
    """
    Initialize a stooge project in a target directory.

    Parameters
    ----------
    path
        The target directory path. If it does not exist, it is created.
        If not provided, use the current working directory.

    Returns
    -------
    Path
        Path to the initialized project directory.
    """
    out_path = Path(path) if path is not None else Path.cwd()
    out_path.mkdir(exist_ok=True, parents=True)
    data = {"project_name": out_path.name}
    _init_directory(stooge._template_path, out_path, data=data)
    write_metadata(out_path)
    return out_path
