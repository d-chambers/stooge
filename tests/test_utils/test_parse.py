"""Tests for parsing helpers."""

from pathlib import Path

import pytest

from stooge.exceptions import StoogeParseError
from stooge.utils.parse import parse_local, parse_script


@pytest.fixture
def local_project(tmp_path):
    """Create a minimal project with a local.py file for parser tests."""
    local_path = tmp_path / "local.py"
    local_path.write_text(
        "from pathlib import Path\n"
        "project_path = Path(__file__).parent\n"
        "input_path = project_path / 'inputs'\n"
        "output_path = project_path / 'outputs'\n"
        "earthquake_csv = input_path / 'earthquakes.csv'\n"
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

        assert out["project_path"] == Path(".")
        assert out["input_path"] == Path("inputs")
        assert out["output_path"] == Path("outputs")
        assert out["earthquake_csv"] == Path("inputs/earthquakes.csv")
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

    def test_supports_literals_aliases_and_parent_chains(self, tmp_path):
        """Evaluate every expression in the static local.py contract."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "root = Path(__file__).parent\n"
            "parent = Path(__file__).parent.parent\n"
            "relative = Path('inputs')\n"
            "alias = relative\n"
            "joined = alias / 'nested' / 'data.csv'\n"
        )
        out = parse_local(tmp_path)
        assert out["root"] == Path(".")
        assert out["parent"] == tmp_path.parent
        assert out["alias"] == Path("inputs")
        assert out["joined"] == Path("inputs/nested/data.csv")

    @pytest.mark.parametrize("base_name", ["_base", "base"])
    def test_base_helpers_preserve_parent_paths(self, tmp_path, base_name):
        """Resolve helper parents before normalizing the returned artifact paths."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            f"{base_name} = Path(__file__).parent\n"
            f"data_path = {base_name} / 'data'\n"
            f"das_data_path = {base_name}.parent / 'recordings'\n"
            "a010_output = data_path / 'a010_output.h5'\n"
        )
        out = parse_local(tmp_path)
        assert out["data_path"] == Path("data")
        assert out["das_data_path"] == tmp_path.parent / "recordings"
        assert out["a010_output"] == Path("data/a010_output.h5")
        assert (base_name in out) is (not base_name.startswith("_"))

    @pytest.mark.parametrize("suffix", ["Path('data')", "_suffix"])
    def test_path_joins_accept_static_path_operands(self, tmp_path, suffix):
        """Allow Path literals and earlier path helpers on the right of a join."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "_base = Path(__file__).parent\n"
            "_suffix = Path('data')\n"
            f"data_path = _base / {suffix}\n"
        )
        assert parse_local(tmp_path) == {"data_path": Path("data")}

    def test_overrides_recompute_private_intermediates(self, tmp_path):
        """Public overrides propagate through private aliases and parent access."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "output_path = Path(__file__).parent / 'outputs'\n"
            "_nested = output_path / Path('nested')\n"
            "a010_output = _nested / 'result.txt'\n"
            "parent = output_path.parent\n"
        )
        out = parse_local(tmp_path, overrides={"output_path": tmp_path})
        assert out["a010_output"] == Path("nested/result.txt")
        assert out["parent"] == tmp_path.parent
        assert "_nested" not in out
        with pytest.raises(StoogeParseError, match="Unknown local variable.*_nested"):
            parse_local(tmp_path, overrides={"_nested": tmp_path})

    @pytest.mark.parametrize("suffix", ["Path(name)", "Path('data').resolve()"])
    def test_path_joins_still_reject_dynamic_operands(self, tmp_path, suffix):
        """Supporting Path operands must not enable dynamic path evaluation."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "_base = Path(__file__).parent\n"
            f"data_path = _base / {suffix}\n"
        )
        with pytest.raises(StoogeParseError, match="Unsupported local.py"):
            parse_local(tmp_path)

    def test_ignores_unused_dynamic_private_values(self, tmp_path):
        """Leave unrelated private expressions unevaluated and untracked."""
        marker = tmp_path / "marker.txt"
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "_unused = (Path(__file__).parent / 'marker.txt').write_text('bad')\n"
            "a010_output = Path('outputs/result.txt')\n"
        )
        assert parse_local(tmp_path) == {"a010_output": Path("outputs/result.txt")}
        assert not marker.exists()

    def test_rejects_public_path_using_dynamic_private_helper(self, tmp_path):
        """Report unsupported private helpers when a public path needs them."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "_base = Path(__file__).resolve().parent\n"
            "data_path = _base / 'data'\n"
        )
        with pytest.raises(StoogeParseError, match="'data_path' on line 3"):
            parse_local(tmp_path)

    def test_ignores_non_path_assignments_and_definitions(self, tmp_path):
        """Ignore constants and definitions that cannot describe artifacts."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "count = 3\n"
            "label = 'research'\n"
            "def helper():\n    return 1\n"
            "root = Path(__file__).parent\n"
        )
        assert parse_local(tmp_path) == {"root": Path(".")}

    def test_rejects_dynamic_path_expressions(self, tmp_path):
        """Reject calls that attempt to calculate or mutate declared paths."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "root = Path(__file__).parent\n"
            "outputs = ensure_folder_exists(root / 'outputs')\n"
        )
        with pytest.raises(StoogeParseError, match="function calls other than Path"):
            parse_local(tmp_path)

    def test_overrides_replace_base_and_derived_values(self, local_project):
        """Bind overridden names and recompute variables derived from them."""
        out = parse_local(
            local_project, overrides={"output_path": Path("/tmp/stooge_dbg")}
        )
        assert out["output_path"] == Path("/tmp/stooge_dbg")
        assert out["cleaned_csv"] == Path(
            "/tmp/stooge_dbg/a010_cleaned_earthquakes.csv"
        )
        # Variables not derived from the override are unchanged.
        assert out["earthquake_csv"] == Path("inputs/earthquakes.csv")

    def test_unknown_override_name_raises_with_available(self, local_project):
        """List available variable names when an override cannot bind."""
        with pytest.raises(StoogeParseError, match="bogus.*available.*output_path"):
            parse_local(local_project, overrides={"bogus": Path("/tmp/x")})


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

        assert out == {
            "inputs": {Path("inputs/earthquakes.csv")},
            "outputs": {Path("outputs/a010_cleaned_earthquakes.csv")},
        }


class TestParseScriptImports:
    """Tests for deriving artifact use from supported import forms."""

    def test_parse_script_uses_variable_name_for_output(self, tmp_path, local_project):
        """Treat vars prefixed with script id as outputs even if path name is not."""
        script_path = tmp_path / "a010_example.py"
        script_path.write_text(
            "from local import a010_named_output\nout_path = a010_named_output\n"
        )
        param_dict = parse_local(local_project)

        out = parse_script(script_path, param_dict)

        assert out == {"inputs": set(), "outputs": {Path("outputs/custom_name.csv")}}

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

        assert out == {
            "inputs": {Path("inputs/earthquakes.csv")},
            "outputs": {Path("outputs/a010_cleaned_earthquakes.csv")},
        }

    def test_parse_script_from_local_star_import(self, tmp_path, local_project):
        """Parse local usage from `from local import *` style imports."""
        script_path = tmp_path / "a010_example.py"
        script_path.write_text(
            "from local import *\nin_path = earthquake_csv\nout_path = cleaned_csv\n"
        )
        param_dict = parse_local(local_project)

        out = parse_script(script_path, param_dict)

        assert out == {
            "inputs": {Path("inputs/earthquakes.csv")},
            "outputs": {Path("outputs/a010_cleaned_earthquakes.csv")},
        }
