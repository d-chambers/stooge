"""Tests for the stooge CLI."""

import json

from typer.testing import CliRunner

import stooge
from stooge.cli import app

runner = CliRunner()


class TestCli:
    """Test CLI commands."""

    def test_version(self):
        """Version command returns package version."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert result.stdout.strip() == stooge.__version__

    def test_init(self, tmp_path):
        """Init command creates a project directory."""
        project_path = tmp_path / "cli_project"
        result = runner.invoke(app, ["init", str(project_path)])
        assert result.exit_code == 0
        assert project_path.exists()
        assert (project_path / "local.py").exists()

    def test_info(self, tmp_path):
        """Info command prints JSON metadata for a project."""
        project_path = stooge.init(tmp_path / "cli_info_project")
        result = runner.invoke(app, ["info", str(project_path)])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["spf_version"] == stooge.__version__
