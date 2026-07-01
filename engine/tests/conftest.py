"""Shared fixtures for engine tests.

The CostGuard + storage modules use a module-level cached DB path resolved
from the TAL_SESSIONS_DB env var. Tests need a fresh path per test to avoid
state bleed.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Per-test SQLite DB path. Resets the cached path on the engine modules."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("TAL_SESSIONS_DB", str(db_path))

    # Re-resolve the cached path on both modules.
    from engine import cost_guard, storage

    storage._reset_for_tests()
    cost_guard._reset_for_tests()

    yield db_path

    # Best-effort cleanup — pytest's tmp_path handles the rest.
    if db_path.exists():
        try:
            os.unlink(db_path)
        except OSError:
            pass
