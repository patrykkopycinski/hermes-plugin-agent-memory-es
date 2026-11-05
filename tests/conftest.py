"""Shared test setup.

* HERMES_HOME points at a throwaway dir so tests never read the real stored config.
* The plugin imports hermes-agent modules (``agent.memory_provider``), so without a
  hermes-agent checkout on PYTHONPATH no test module can even be collected. In that case the
  suite stops at session start with one explicit SKIPPED message (exit 0) instead of import errors.
"""
from __future__ import annotations

import importlib
import os
import tempfile

import pytest

os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="ames-plugin-test-")


def _missing_hermes_agent() -> str | None:
    try:
        for mod in ("agent.memory_provider", "agent.memory_manager", "tools.schema_sanitizer"):
            importlib.import_module(mod)
    except ImportError as exc:
        return (f"hermes-agent is not importable ({exc}); put its checkout on PYTHONPATH "
                "(e.g. PYTHONPATH=~/.hermes/hermes-agent) to run the plugin tests")
    return None


_REASON = _missing_hermes_agent()


def pytest_sessionstart(session):
    # pytest imports the checkout-root __init__.py as a Package before any test runs, which
    # needs hermes-agent; stop here with one readable message instead of import errors.
    if _REASON:
        pytest.exit(f"SKIPPED: {_REASON}", returncode=0)
