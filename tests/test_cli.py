"""Tests for the stooge CLI."""

import json
from pathlib import Path

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

    def test_init_json(self, tmp_path):
        """Init JSON reports the created path and backend."""
        result = runner.invoke(app, ["init", str(tmp_path / "proj"), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["command"] == "init"
        assert data["ok"] is True
        assert data["backend"] == "uv"
        assert Path(data["path"]).is_dir()

    def test_info_json(self, tmp_path):
        """Info JSON uses the shared success envelope."""
        project_path = stooge.init(tmp_path / "cli_info_project")
        result = runner.invoke(app, ["info", str(project_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["command"] == "info"
        assert data["ok"] is True
        assert data["stooge_version"] == stooge.__version__
        assert data["backend"] == "uv"

    def test_parse_dry_run(self, workflow_project):
        """Parse dry-run validates a project without changing its manifest."""
        manifest = workflow_project / ".stooge.toml"
        before = manifest.read_text()
        result = runner.invoke(app, ["parse", str(workflow_project), "--dry-run"])
        assert result.exit_code == 0
        assert "Parsed 3 task(s)" in result.stdout
        assert manifest.read_text() == before

    def test_parse_json_has_task_definitions(self, workflow_project):
        """Expose parsed inputs, outputs, and dependencies to agents."""
        result = runner.invoke(
            app, ["parse", str(workflow_project), "--dry-run", "--json"]
        )
        data = json.loads(result.stdout)
        assert result.exit_code == 0
        assert data["command"] == "parse"
        assert data["tasks"]["a020"]["dependencies"] == ["a010"]
        assert data["execution_order"] == ["a010", "a020", "a030"]

    def test_parse_does_not_execute_local_side_effects(self, tmp_path):
        """Static parse ignores top-level expressions and creates no outputs."""
        marker = tmp_path / "marker.txt"
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "root = Path(__file__).parent\n"
            "a010_out = root / 'outputs/result.txt'\n"
            "Path('marker.txt').write_text('bad')\n"
        )
        (tmp_path / "a010_task.py").write_text(
            "from local import a010_out\nprint(a010_out)\n"
        )
        result = runner.invoke(app, ["parse", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
        assert not marker.exists()
        assert not (tmp_path / "outputs").exists()

    def test_run_and_remove(self, workflow_project, monkeypatch):
        """Run and remove commands operate from the current project."""
        monkeypatch.chdir(workflow_project)
        run_result = runner.invoke(app, ["run", "a030"])
        remove_result = runner.invoke(app, ["remove", "a020"])
        assert run_result.exit_code == 0
        assert "a010 (missing_output)" in run_result.stdout
        assert remove_result.exit_code == 0
        assert not (workflow_project / "outputs/a020_calc.txt").exists()

    def test_run_path_dry_run_json(self, workflow_project):
        """Preview a project outside cwd with reasons and no execution."""
        result = runner.invoke(
            app,
            ["run", "a030", str(workflow_project), "--dry-run", "--json"],
        )
        data = json.loads(result.stdout)
        assert result.exit_code == 0
        assert data["command"] == "run"
        assert data["planned"] == ["a010", "a020", "a030"]
        assert data["executed"] == []
        assert data["plan"][0]["reason"] == "missing_output"
        assert not (workflow_project / "outputs/a030_result.txt").exists()

    def test_remove_accepts_path_and_json(self, workflow_project):
        """Remove task outputs without changing the current directory."""
        stooge.run_project(workflow_project, "a030")
        result = runner.invoke(app, ["remove", "a020", str(workflow_project), "--json"])
        data = json.loads(result.stdout)
        assert result.exit_code == 0
        assert data["removed"] == ["outputs/a020_calc.txt"]

    def test_json_error_is_stdout_envelope(self, workflow_project):
        """Return machine-readable, typed errors on stdout with a failing status."""
        result = runner.invoke(app, ["run", "a999", str(workflow_project), "--json"])
        data = json.loads(result.stdout)
        assert result.exit_code == 1
        assert data == {
            "command": "run",
            "ok": False,
            "kind": "task_not_found",
            "error": "Unknown task ID: a999",
        }

    def test_json_run_failure_reports_partial_progress(self, workflow_project):
        """Include tasks that completed before a mid-plan failure."""
        (workflow_project / "a020_calc.py").write_text(
            "from local import a010_clean, a020_calc\n"
            "print(a010_clean, a020_calc)\n"
            "raise SystemExit(3)\n"
        )
        result = runner.invoke(app, ["run", "a030", str(workflow_project), "--json"])
        data = json.loads(result.stdout)
        assert result.exit_code == 1
        assert data["ok"] is False
        assert data["kind"] == "run_error"
        assert data["executed"] == ["a010"]
        assert (workflow_project / "outputs/a010_clean.txt").exists()

    def test_run_set_override_is_ephemeral(self, workflow_project, tmp_path):
        """Redirect derived outputs outside the project without touching state."""
        debug_dir = tmp_path / "dbg"
        manifest_before = (workflow_project / ".stooge.toml").read_text()
        result = runner.invoke(
            app,
            [
                "run",
                "a030",
                str(workflow_project),
                "--set",
                f"out_dir={debug_dir}",
                "--json",
            ],
        )
        data = json.loads(result.stdout)
        assert result.exit_code == 0
        assert data["ephemeral"] is True
        assert data["overrides"] == {"out_dir": str(debug_dir)}
        assert data["executed"] == ["a010", "a020", "a030"]
        assert (debug_dir / "a030_result.txt").read_text() == "raw-clean-calc-result"
        assert not (workflow_project / "outputs/a030_result.txt").exists()
        assert (workflow_project / ".stooge.toml").read_text() == manifest_before

    def test_local_file_overrides_and_set_precedence(self, workflow_project, tmp_path):
        """Apply override files, ignore helper names, and let --set win."""
        override_file = tmp_path / "debug_local.py"
        override_file.write_text(
            "from pathlib import Path\n"
            "helper = Path(__file__).parent / 'file_dbg'\n"
            "out_dir = helper\n"
        )
        file_result = runner.invoke(
            app,
            ["run", "a010", str(workflow_project), "--local-file", str(override_file)],
        )
        assert file_result.exit_code == 0
        assert (tmp_path / "file_dbg/a010_clean.txt").exists()

        set_dir = tmp_path / "set_dbg"
        set_result = runner.invoke(
            app,
            [
                "run",
                "a010",
                str(workflow_project),
                "--local-file",
                str(override_file),
                "--set",
                f"out_dir={set_dir}",
            ],
        )
        assert set_result.exit_code == 0
        assert (set_dir / "a010_clean.txt").exists()

    def test_override_errors_are_typed(self, workflow_project):
        """Reject malformed and unknown --set entries with parse errors."""
        malformed = runner.invoke(
            app, ["run", "a030", str(workflow_project), "--set", "nonsense", "--json"]
        )
        assert malformed.exit_code == 1
        assert json.loads(malformed.stdout)["kind"] == "parse_error"

        unknown = runner.invoke(
            app,
            ["run", "a030", str(workflow_project), "--set", "bogus=/tmp/x", "--json"],
        )
        data = json.loads(unknown.stdout)
        assert unknown.exit_code == 1
        assert data["kind"] == "parse_error"
        assert "available" in data["error"] and "out_dir" in data["error"]

    def test_dry_run_with_overrides_plans_against_override(
        self, workflow_project, tmp_path
    ):
        """Plan staleness against overridden paths without executing."""
        stooge.run_project(workflow_project, "a030")
        debug_dir = tmp_path / "plan_dbg"
        result = runner.invoke(
            app,
            [
                "run",
                "a030",
                str(workflow_project),
                "--set",
                f"out_dir={debug_dir}",
                "--dry-run",
                "--json",
            ],
        )
        data = json.loads(result.stdout)
        assert result.exit_code == 0
        assert data["ephemeral"] is True
        reasons = {item["task_id"]: item["reason"] for item in data["plan"]}
        assert reasons == {task: "missing_output" for task in ("a010", "a020", "a030")}
        assert not debug_dir.exists()

    def test_override_run_preserves_non_path_constants(
        self, workflow_project, tmp_path
    ):
        """Scripts still import non-path names from local during override runs."""
        local = workflow_project / "local.py"
        local.write_text(local.read_text() + "label = 'wf'\n")
        (workflow_project / "a010_clean.py").write_text(
            "from local import raw, a010_clean, label\n"
            "a010_clean.write_text(raw.read_text() + '-' + label)\n"
        )
        debug_dir = tmp_path / "const_dbg"
        result = runner.invoke(
            app,
            ["run", "a010", str(workflow_project), "--set", f"out_dir={debug_dir}"],
        )
        assert result.exit_code == 0
        assert (debug_dir / "a010_clean.txt").read_text() == "raw-wf"

    def test_dry_run_previews_plan_with_missing_input(self, workflow_project):
        """Report missing raw inputs as plan reasons instead of failing."""
        (workflow_project / "inputs/raw.txt").unlink()
        result = runner.invoke(
            app, ["run", "a030", str(workflow_project), "--dry-run", "--json"]
        )
        data = json.loads(result.stdout)
        assert result.exit_code == 0
        assert data["ok"] is True
        reasons = {item["task_id"]: item["reason"] for item in data["plan"]}
        assert reasons["a010"] == "missing_input"
        # An actual run still fails loudly on the missing input.
        run_result = runner.invoke(app, ["run", "a030", str(workflow_project)])
        assert run_result.exit_code == 1
