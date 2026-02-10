"""
Utilities for stooge.
"""
import contextlib
import fnmatch
import hashlib
import importlib.util
import os
from pathlib import Path
from typing import Optional, Union

from stooge.exceptions import SPFInitError

# def get_task_list(project_path):
#     """
#     Return a list of pre-DoIt style task dicts.
#
#     The dicts have the following keys:
#         script_path - The path to the script relative to the project path.
#         basename - The Name of the task
#         inputs - A list of file inputs
#         outputs - A list of file outputs
#     """
#     path = path_or_cwd(project_path)
#     nodes = get_project_nodes(path)
#     out = []
#     for item, value in nodes.items():
#         name = Path(item).name.split('_')[0]
#         task = {
#             'basename': name,
#             'script_path': str(item),
#             'inputs': [str(x) for x in value['inputs']],
#             'outputs': [str(x) for x in value['outputs']],
#         }
#         out.append(task)
#     return out


def get_python_scripts(project_path) -> tuple[Path]:
    """
    Return a tuple of python scripts which *may* produce outputs.

    Returned paths are relative to project path.
    """
    path = path_or_cwd(project_path)
    out = []
    for pypath in path.glob("*.py"):
        name = pypath.name.split(".py")[0]
        if len(name) < 4:
            continue
        letter = name[0]
        numbers = name[1:4]
        if letter.isalpha() and numbers.isnumeric():
            out.append(pypath.relative_to(path))
    return tuple(out)


def _get_task_dict_from_script(path, project_path):
    """Get the inputs and outputs for a python script."""
    local_contents = get_local_contents(project_path)
    script_str = (project_path / path).read_text()
    script_lines = script_str.split("\n")
    prefix = path.name.split("_")[0]
    nodes = []
    for name, value in local_contents.items():
        if name not in script_str:
            continue
        # simple case where variable is used as local.{name}
        if f"local.{name}" not in script_str:
            # now need to check from local import name style
            match = f"*from local import *{name}*"
            has_from_input = [fnmatch.fnmatch(x, match) for x in script_lines]
            # we only get here if an unrelated local variable shares a name
            # with a project variable
            if not any(has_from_input):
                continue
        nodes.append(name)

    is_output = {x: local_contents[x].name.startswith(prefix) for x in nodes}
    outputs = [str(local_contents[x]) for x in nodes if is_output[x]]
    inputs = [str(local_contents[x]) for x in nodes if not is_output[x]]
    out = dict(
        file_outputs=tuple(outputs),
        file_inputs=tuple(inputs),
        name=Path(path).name.split("_")[0],
        script_path=path,
    )
    return out


def get_project_task_list(project_path):
    """Get the inputs and outputs for each script in the project."""
    project_path = path_or_cwd(project_path)
    scripts = get_python_scripts(project_path)
    return {x: _get_task_dict_from_script(x, project_path) for x in scripts}


def get_local_contents(project_path) -> dict:
    """Get a dict of variable_name: path for each input/output path"""

    def _get_artifacts(local):
        """extract all potential inputs/outputs from local."""
        info = {}
        input_str = str(input_path)
        output_str = str(output_path)
        for name in dir(local):
            # skip any dunders and non-paths
            if name.startswith("__"):
                continue
            var = getattr(local, name)
            if not isinstance(var, (str, Path)):
                continue
            path_str = str(Path(var))
            in_inputs = path_str.startswith(input_str) and path_str != input_str
            in_outputs = path_str.startswith(output_str) and path_str != output_str
            if in_inputs or in_outputs:
                info[name] = Path(var).relative_to(project_path)
        return info

    # get path to local.py
    path = path_or_cwd(project_path).absolute()
    if not path.name.endswith("local.py"):
        path = project_path / "local.py"
    else:
        project_path = path.parent
    # load module
    with working_directory(path.parent):  # chdir to local
        spec = importlib.util.spec_from_file_location("local", str(path))
        local = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(local)
    input_path, output_path = local.input_path, local.output_path
    return _get_artifacts(local)


def path_or_cwd(path: Optional[Union[str, Path]] = None) -> Path:
    """Return a Path from path or, if None, return Path of cwd."""
    if path is None:
        path = Path.cwd()
    return Path(path)


def ensure_spf_project(project_path: Union[str, Path]) -> Path:
    """
    Ensure the path is a stooge project by checking for stooge metadata.

    Parameters
    ----------
    project_path
        Path to project.

    Returns
    -------

    """
    path = path_or_cwd(project_path)
    if not path.exists():
        msg = (
            f"{path.parent} is not yet an " f"stooge project. Try running `stooge init`."
        )
        raise SPFInitError(msg)
    return path


@contextlib.contextmanager
def working_directory(path):
    """Changes working directory and returns to previous on exit."""
    prev_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


def file_hash(fname: Union[str, Path], algorithm="sha256") -> str:
    """
    Calculate the hash of a given file.

    Useful for checking if a file has changed or been corrupted.

    Parameters
    ----------
    fname : str
        The name of the file.
    algorithm : str
        The type of the hashing algorithm

    Examples
    --------
    >>> fname = "test-file-for-hash.txt"
    >>> with open(fname, "w") as f:
    ...     __ = f.write("content of the file")
    >>> print(file_hash(fname))
    0fc74468e6a9a829f103d069aeb2bb4f8646bad58bf146bb0e3379b759ec4a00
    >>> import os
    >>> os.remove(fname)

    Notes
    -----
    This implementation was taken from the excellent Pooch project:
    https://github.com/fatiando/pooch
    """
    if algorithm not in hashlib.algorithms_available:
        raise ValueError(f"Algorithm '{algorithm}' not available in hashlib")
    # Calculate the hash in chunks to avoid overloading the memory
    chunksize = 65536
    hasher = hashlib.new(algorithm)
    with open(fname, "rb") as fin:
        buff = fin.read(chunksize)
        while buff:
            hasher.update(buff)
            buff = fin.read(chunksize)
    return hasher.hexdigest()
