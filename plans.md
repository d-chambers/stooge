# Future work

The first supported workflow is `init → parse → run → remove` using uv or the
current Python interpreter. Candidate follow-up work should be evaluated only
after this workflow is stable:

- Define environment lifecycle semantics for miniforge and marimo backends.
- Add explicit custom-interpreter configuration for the Python backend.
- Explore parallel execution for independent branches of the task graph.
