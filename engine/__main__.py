"""Entry point. `python -m engine` starts the sidecar.

On startup, prints a JSON line `{"port": <int>, "token": "<uuid>"}` to stdout
so the parent process (Electron main) can read the connection details.

If `TAL_ENGINE_PIDFILE` is set (Electron main passes a path under the app's
userData dir), the engine writes its OS pid there on startup and removes it on
clean exit. This lets the parent reap exactly the engine it spawned on a prior
crashed session, rather than broad-matching every `python -m engine` process
(which would kill an unrelated dev engine running in another terminal).
"""

from __future__ import annotations

import atexit
import json
import os
import secrets
import socket
import sys
import uvicorn

from .server import build_app


def _pick_port() -> int:
    """Reserve a free TCP port on localhost."""
    requested = os.environ.get("TAL_ENGINE_PORT")
    if requested:
        return int(requested)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_pidfile(path: str) -> None:
    """Write this process's pid to `path` (atomic-ish: write tmp + replace).

    Best-effort: a failure to write the pidfile must never stop the engine
    from starting — the orphan-reaping it enables is a convenience, not a
    correctness requirement. Creates parent dirs if missing.
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError:
        pass


def _remove_pidfile(path: str) -> None:
    """Remove the pidfile, but only if it still holds *our* pid.

    Guards against deleting a newer engine's pidfile if ours is shutting
    down late: only unlink when the recorded pid matches getpid().
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            recorded = fh.read().strip()
        if recorded == str(os.getpid()):
            os.unlink(path)
    except OSError:
        pass


def _selftest_full_debate() -> None:
    """Import the full-debate stack and exit — a packaging probe.

    The server lazy-imports full_debate only when a Pro run starts, so a
    frozen build (PyInstaller) can boot and pass /health while missing the
    LangChain/LangGraph/tradingagents stack entirely. Release verification
    runs the frozen binary with TAL_SELFTEST=full_debate: exit 0 proves the
    whole import graph is bundled; a traceback names exactly what is not.
    """
    from . import full_debate  # noqa: F401 — the import IS the test

    sys.stdout.write("selftest ok: full_debate import graph loads\n")


def main() -> None:
    if os.environ.get("TAL_SELFTEST") == "full_debate":
        _selftest_full_debate()
        return

    token = os.environ.get("TAL_ENGINE_TOKEN") or secrets.token_urlsafe(24)
    port = _pick_port()

    pidfile = os.environ.get("TAL_ENGINE_PIDFILE")
    if pidfile:
        _write_pidfile(pidfile)
        # atexit covers a clean uvicorn shutdown (SIGTERM/SIGINT). A SIGKILL
        # can't be caught, so the pidfile is left behind — that's the orphan
        # case the parent reaps on next launch, exactly as intended.
        atexit.register(_remove_pidfile, pidfile)

    # Hand connection details to the parent process before binding the server.
    sys.stdout.write(json.dumps({"port": port, "token": token}) + "\n")
    sys.stdout.flush()

    app = build_app(token=token)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level=os.environ.get("TAL_ENGINE_LOG_LEVEL", "warning"),
        access_log=False,
    )


if __name__ == "__main__":
    main()
