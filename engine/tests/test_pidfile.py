"""Tests for the engine pidfile helpers (Tier 1, 2026-05-23).

The engine writes its OS pid to `TAL_ENGINE_PIDFILE` on startup so Electron
main can reap exactly the engine it spawned on a prior crashed session, rather
than broad-matching every `python -m engine` (which also killed unrelated dev
engines in other terminals). These tests cover the write/remove contract.
"""

from __future__ import annotations

import os

from engine.__main__ import _remove_pidfile, _write_pidfile


def test_write_pidfile_records_current_pid(tmp_path):
    path = str(tmp_path / "engine.pid")
    _write_pidfile(path)
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as fh:
        assert fh.read().strip() == str(os.getpid())


def test_write_pidfile_creates_parent_dirs(tmp_path):
    """userData subdir may not exist yet on a first launch."""
    path = str(tmp_path / "nested" / "subdir" / "engine.pid")
    _write_pidfile(path)
    assert os.path.exists(path)


def test_write_pidfile_leaves_no_tmp(tmp_path):
    """The tmp+replace write must not leave a stray .tmp behind."""
    path = str(tmp_path / "engine.pid")
    _write_pidfile(path)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "engine.pid"]
    assert leftovers == []


def test_remove_pidfile_deletes_when_pid_matches(tmp_path):
    path = str(tmp_path / "engine.pid")
    _write_pidfile(path)
    _remove_pidfile(path)
    assert not os.path.exists(path)


def test_remove_pidfile_keeps_file_when_pid_differs(tmp_path):
    """A late shutdown must not delete a *newer* engine's pidfile. Only the
    process whose pid is recorded removes it."""
    path = str(tmp_path / "engine.pid")
    other_pid = os.getpid() + 1  # a pid that is not ours
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(str(other_pid))
    _remove_pidfile(path)
    assert os.path.exists(path)  # left intact — it wasn't ours


def test_remove_pidfile_missing_is_noop(tmp_path):
    """Removing a non-existent pidfile (SIGKILL already cleaned, or never
    written) must not raise."""
    _remove_pidfile(str(tmp_path / "does-not-exist.pid"))  # no exception


def test_write_pidfile_swallows_errors(tmp_path):
    """A pidfile write failure must never stop the engine from starting.
    Pointing at a path whose parent is a file (not a dir) forces an OSError
    that the helper must swallow."""
    blocker = tmp_path / "iam-a-file"
    blocker.write_text("x")
    # makedirs on "<file>/sub" raises NotADirectoryError (an OSError subclass).
    _write_pidfile(str(blocker / "sub" / "engine.pid"))  # no exception
