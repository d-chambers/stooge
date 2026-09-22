"""
Tests for initiating new stooge projects.
"""

import pytest

import stooge


class TestBasicInit:
    """Simple init test case for init."""

    @pytest.fixture(scope="class")
    def basic_spf(self, tmp_path_factory):
        """Create a default stooge directory."""
        path = tmp_path_factory.mktemp(basename="test_basic_init")
        return stooge.init(path)

    def test_created_directory(self, basic_spf):
        """Simply ensure directory was created."""
        assert basic_spf.exists()
        assert basic_spf.is_dir()

    def test_expected_files_exist(self, basic_spf):
        """Ensure the expected files exist."""
        template_names = {
            x.name
            for x in stooge._template_path.rglob("*")
            if x.is_file()
            and "__pycache__" not in x.parts
            and x.suffix not in {".pyc", ".pyo"}
        }
        output_names = {x.name for x in basic_spf.rglob("*")}
        assert output_names.issuperset(template_names)

    def test_project_name_inserted(self, basic_spf):
        """Ensure the project name occurs in local.py"""
        name = basic_spf.name
        local_path = basic_spf / "local.py"
        assert local_path.exists()
        contents = local_path.read_text()
        assert name in contents

    def test_files_not_overwritten(self, tmp_path_factory):
        """Simply ensure files which already exist do not get overwritten."""
        path = tmp_path_factory.mktemp(basename="test_no_overwrite")
        # write a local file and get its timestamp
        local = path / "local.py"
        with local.open("w") as fi:
            fi.write("default local")
        current_mtime = local.stat().st_mtime
        # init directory, ensure mtime hasnt changed
        stooge.init(path)
        new_mtime = local.stat().st_mtime
        assert current_mtime == new_mtime

    def test_existing_task_suppresses_starter(self, tmp_path):
        """Skip the starter a010 script when any task already exists."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "root = Path(__file__).parent\n"
            "v010_out = root / 'outputs/v010_out.txt'\n"
        )
        (tmp_path / "v010_plot.py").write_text(
            "from local import v010_out\nprint(v010_out)\n"
        )
        stooge.init(tmp_path)
        assert not (tmp_path / "a010_first_script.py").exists()
        assert set(stooge.load_project(tmp_path).tasks) == {"v010"}

    def test_manifest_exists(self, basic_spf):
        """Initialization writes the canonical root manifest."""
        assert (basic_spf / ".stooge.toml").is_file()
        assert not (basic_spf / ".stooge").exists()

    def test_python_backend_omits_uv_project(self, tmp_path):
        """Python projects do not receive an unnecessary uv manifest."""
        project = stooge.init(tmp_path / "python_project", backend="python")
        assert not (project / "pyproject.toml").exists()
