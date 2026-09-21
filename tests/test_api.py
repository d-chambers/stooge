"""Tests for the supported top-level Stooge Python API."""

import stooge


class TestPublicAPI:
    """Verify every documented public name is directly importable."""

    def test_all_names_exist(self):
        """Keep __all__ synchronized with concrete module attributes."""
        expected = {
            "Project",
            "RunPlan",
            "RunReason",
            "RunReport",
            "StoogeError",
            "StoogeInitError",
            "StoogeParseError",
            "StoogeRunError",
            "StoogeTaskNotFoundError",
            "TaskSpec",
            "__version__",
            "info",
            "init",
            "load_project",
            "plan_run",
            "remove_task_outputs",
            "reparse_project",
            "resolve_overrides",
            "run_project",
            "task_stale_reason",
        }
        assert set(stooge.__all__) == expected
        assert all(hasattr(stooge, name) for name in expected)
        assert "_template_path" not in stooge.__all__
