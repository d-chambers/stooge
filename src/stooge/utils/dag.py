"""
Utilities for working with the DAG
"""

from collections import deque


def topological_sort(dependencies: dict[str, list[str]]) -> list[str]:
    """
    Return tasks in topological order for execution using Kahn's algorithm.

    Parameters
    ----------
    dependencies
        Dictionary mapping task_id -> [dependent_task_id, ...].

    Returns
    -------
    List[str]
        Task IDs in execution order.

    Notes
    -----
    - (Kahn's algorithm)[https://en.wikipedia.org/wiki/Topological_sorting]

    Raises
    ------
    ValueError
        If circular dependency is detected in the task graph.
    """
    all_task_ids = set(dependencies.keys())
    for task_dependents in dependencies.values():
        all_task_ids.update(task_dependents)

    # Kahn's algorithm for topological sorting
    in_degree = {task_id: 0 for task_id in all_task_ids}
    adjacency: dict[str, list[str]] = {task_id: [] for task_id in all_task_ids}

    for task_id, task_dependents in dependencies.items():
        for dependent_id in task_dependents:
            adjacency[task_id].append(dependent_id)
            in_degree[dependent_id] += 1

    # Start with tasks that have no dependencies
    queue = deque(task_id for task_id, degree in in_degree.items() if degree == 0)
    result = []

    while queue:
        current = queue.popleft()
        result.append(current)

        # Reduce in-degree for dependent tasks
        for downstream_id in adjacency[current]:
            in_degree[downstream_id] -= 1
            if in_degree[downstream_id] == 0:
                queue.append(downstream_id)

    if len(result) != len(all_task_ids):
        raise ValueError("Circular dependency detected in pipe")

    return result
