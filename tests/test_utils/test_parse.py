"""Tests for parsing helpers."""

from pathlib import Path

import pytest

from stooge.utils.parse import build_dependency_graph, parse_local, parse_script


@pytest.fixture
def local_project(tmp_path):
    """Create a minimal project with a local.py file for parser tests."""
    local_path = tmp_path / "local.py"
    local_path.write_text(
        "from pathlib import Path\n"
        "project_path = Path(__file__).parent\n"
        "input_path = project_path / 'inputs'\n"
        "output_path = project_path / 'outputs'\n"
        "earthquake_csv = input_path / 'bingham_earthquakes.csv'\n"
        "cleaned_csv = output_path / 'a010_cleaned_earthquakes.csv'\n"
        "a010_named_output = output_path / 'custom_name.csv'\n"
        "calc_csv = output_path / 'a020_calculated_earthquakes.csv'\n"
    )
    return tmp_path


class TestParseLocal:
    """Tests for parsing `local.py` path variables."""

    def test_parse_local_from_project_path(self, local_project):
        """Parse `Path` variables from a project directory."""
        out = parse_local(local_project)

        assert "project_path" in out
        assert "input_path" in out
        assert "output_path" in out
        assert all(isinstance(value, Path) for value in out.values())

    def test_parse_local_from_local_file_path(self, local_project):
        """Parse `Path` variables from a direct `local.py` path."""
        project_out = parse_local(local_project)
        file_out = parse_local(local_project / "local.py")

        assert file_out == project_out

    def test_parse_local_raises_on_missing_local(self, tmp_path):
        """Raise when local.py cannot be found."""
        with pytest.raises(FileNotFoundError, match="Cannot find local.py"):
            _ = parse_local(tmp_path / "not_local.py")


class TestParseScript:
    """Tests for parsing script usage of `local` variables."""

    def test_parse_script_import_local(self, tmp_path, local_project):
        """Parse local usage from `import local` style imports."""
        script_path = tmp_path / "a010_example.py"
        script_path.write_text(
            "import local\n"
            "in_path = local.earthquake_csv\n"
            "out_path = local.cleaned_csv\n"
        )
        param_dict = parse_local(local_project)

        out = parse_script(script_path, param_dict)

        assert out == {"inputs": {"earthquake_csv"}, "outputs": {"cleaned_csv"}}


class TestBuildDependencyGraph:
    """Tests for deriving script dependency graph from local vars."""

    def test_build_dependency_graph(self, local_project):
        """Build {task_id: [dependent_ids...]} from script/local relationships."""
        (local_project / "a010_clean.py").write_text(
            "import local\n" "x = local.earthquake_csv\n" "y = local.cleaned_csv\n"
        )
        (local_project / "a020_calc.py").write_text(
            "from local import cleaned_csv, calc_csv\n"
            "x = cleaned_csv\n"
            "y = calc_csv\n"
        )
        (local_project / "a030_plot.py").write_text(
            "from local import calc_csv\n" "x = calc_csv\n"
        )
        (local_project / "notes.py").write_text("x = 1\n")

        out = build_dependency_graph(local_project)

        assert out == {"a010": ["a020"], "a020": ["a030"], "a030": []}

    def test_parse_script_uses_variable_name_for_output(self, tmp_path, local_project):
        """Treat vars prefixed with script id as outputs even if path name is not."""
        script_path = tmp_path / "a010_example.py"
        script_path.write_text(
            "from local import a010_named_output\n" "out_path = a010_named_output\n"
        )
        param_dict = parse_local(local_project)

        out = parse_script(script_path, param_dict)

        assert out == {"inputs": set(), "outputs": {"a010_named_output"}}

    def test_parse_script_from_local_import(self, tmp_path, local_project):
        """Parse local usage from `from local import var` style imports."""
        script_path = tmp_path / "a010_example.py"
        script_path.write_text(
            "from local import earthquake_csv as eq, cleaned_csv\n"
            "in_path = eq\n"
            "out_path = cleaned_csv\n"
        )
        param_dict = parse_local(local_project)

        out = parse_script(script_path, param_dict)

        assert out == {"inputs": {"earthquake_csv"}, "outputs": {"cleaned_csv"}}

    def test_parse_script_from_local_star_import(self, tmp_path, local_project):
        """Parse local usage from `from local import *` style imports."""
        script_path = tmp_path / "a010_example.py"
        script_path.write_text(
            "from local import *\n"
            "in_path = earthquake_csv\n"
            "out_path = cleaned_csv\n"
        )
        param_dict = parse_local(local_project)

        out = parse_script(script_path, param_dict)

        assert out == {"inputs": {"earthquake_csv"}, "outputs": {"cleaned_csv"}}
