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
        template_names = {x.name for x in stooge._template_path.rglob("*")}
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

    def test_spf_directory_exists(self, basic_spf):
        """The stooge directory, which contains stooge metadata, should exist."""
        from stooge.meta import METADATA_DIRECTORY_NAME, METADATA_FILE_NAME

        expected_path = basic_spf / METADATA_DIRECTORY_NAME
        assert expected_path.exists()
        assert (expected_path / METADATA_FILE_NAME).exists()
