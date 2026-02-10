"""
Tests for stooge utils.
"""
from pathlib import Path

import pytest

from stooge.utils import get_local_contents, get_project_task_list, get_python_scripts


class TestGetLocalContents:
    """Tests for extracting info from local.py"""

    @pytest.fixture(scope="class")
    def local_contents(self, spf_example_project):
        """return contents of local from example project"""
        return get_local_contents(spf_example_project)

    def test_exist(self, local_contents):
        """Ensure something is returned from example."""
        assert local_contents is not None
        assert len(local_contents)

    def test_works_with_local_path(self, spf_example_project, local_contents):
        """Ensure a path to local also works."""
        local_path = spf_example_project / "local.py"
        new_contents = get_local_contents(local_path)
        assert new_contents == local_contents


class TestGetPythonScripts:
    """Tests for finding the scripts which produce inputs/outputs."""

    def test_get_python_script_tuple(self, spf_example_project):
        """ensure the scripts are returned from the example project."""
        scripts = get_python_scripts(spf_example_project)
        assert len(scripts)
        assert all([str(x).endswith(".py") for x in scripts])
        expected_prefix = {"a010", "a020", "a030"}
        prefixes = {str(x.name)[:4] for x in scripts}
        assert prefixes.issuperset(expected_prefix)


class TestGetProjectTasks:
    """Tests for getting nodes (input/output) form a python script."""

    @pytest.fixture(scope="class")
    def project_tasks(self, spf_example_project):
        """return a dict of {script_path: {inputs: (...), outputs:(...)}}"""
        return get_project_task_list(spf_example_project)

    def test_nodes(self, project_tasks):
        """Tests for known relationships."""
        path = Path("a010_clean_data.py")
        out = project_tasks[path]
        assert len(out["file_inputs"]) == 1
        assert str(out["file_inputs"][0]).endswith("bingham_earthquakes.csv")
        assert len(out["file_outputs"]) == 1
        assert "a010" in str(out["file_outputs"][0])
