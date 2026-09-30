"""Shared test runner.

Every ``test_*.py`` file in this package can run **both**:
  * under pytest              (``pytest tests/``), and
  * standalone                (``python -m tests.test_load_data``)

This module provides the standalone runner. pytest ignores it (it has no ``test_``
prefix). Each test file ends with a ``__main__`` block that calls
``run_module(sys.modules[__name__])``.

Why a custom runner?  In some environments pytest may not be on PATH, and the
project's own modules are fully integrated here, so we need a dependency-
free way to confirm "is my pipeline still intact?" after any
change.
"""

import inspect


def run_module(mod) -> int:
    """Discover and run every ``test_*`` function in module ``mod``.

    Returns the number of failures (0 == all passed).
    """
    funcs = [
        f for _, f in inspect.getmembers(mod, inspect.isfunction)
        if f.__name__.startswith("test_")
    ]
    passed = failed = 0
    print(f"\n=== {mod.__name__}  ({len(funcs)} tests) ===")
    for f in funcs:
        try:
            f()
            print(f"  PASS  {f.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {f.__name__}: {e}")
            failed += 1
        except Exception as e:  # pragma: no cover - surfaced loudly
            print(f"  ERROR {f.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"  -> {passed} passed, {failed} failed")
    return failed
