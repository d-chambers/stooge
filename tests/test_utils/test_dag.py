"""Tests for DAG utilities."""

import pytest

from stooge.utils.dag import topological_sort


class TestTopologicalSort:
    """Tests for topological sort of DAG task ids."""

    def test_topological_sort_with_inputs_outputs_dict(self):
        """Sort tasks when graph is modeled as node inputs/outputs."""
        dependencies = {
            "a": {"inputs": set(), "outputs": {"x"}},
            "b": {"inputs": {"x"}, "outputs": {"y"}},
            "c": {"inputs": {"x"}, "outputs": {"z"}},
            "d": {"inputs": {"y", "z"}, "outputs": set()},
        }

        order = topological_sort(dependencies)

        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_topological_sort_includes_independent_nodes(self):
        """Include nodes that do not consume or produce shared artifacts."""
        dependencies = {
            "a": {"inputs": set(), "outputs": {"x"}},
            "b": {"inputs": {"x"}, "outputs": set()},
            "c": {"inputs": set(), "outputs": set()},
        }

        order = topological_sort(dependencies)

        assert set(order) == {"a", "b", "c"}
        assert order.index("a") < order.index("b")

    def test_topological_sort_raises_on_cycle(self):
        """Raise when inputs/outputs create a cycle between nodes."""
        dependencies = {
            "a": {"inputs": {"y"}, "outputs": {"x"}},
            "b": {"inputs": {"x"}, "outputs": {"y"}},
        }

        with pytest.raises(ValueError, match="Circular dependency detected"):
            _ = topological_sort(dependencies)
