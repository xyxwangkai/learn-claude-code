# Tests Directory Summary

Files under `tests/`:

- `tests/test_agents_smoke.py`
  - Smoke test for Python agent scripts in `agents/`.
  - Collects all `.py` files in the `agents` directory except `__init__.py`.
  - Verifies each script compiles successfully with `py_compile`.
  - Also checks that at least one agent script exists.

- `tests/test_s_full_background.py`
  - Focused unit test for background-task behavior in `agents/s_full.py`.
  - Loads `s_full.py` in an isolated temporary environment using mocked `anthropic` and `dotenv` modules.
  - Tests that `BackgroundManager.check("abc123")` returns the placeholder string `[running] (running)` when a tracked task is still running and its result is `None`.

Overall, the current `tests/` directory contains one broad smoke test for agent script validity and one targeted regression-style test for background task status handling in the full agent implementation.
