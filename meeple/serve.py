"""Composition root: the one module that stands on both sides of the seam,
importing `meeple.games` for its registration side effect and handing the
game-agnostic web app to uvicorn. Everything under `meeple.web` never sees
a concrete game."""

from pathlib import Path

import uvicorn

from meeple.web.app import FRONTEND_DIST, FrontendBuildMissingError, create_app


def make_app(frontend_dist: Path | None = FRONTEND_DIST):
    import meeple.games  # noqa: F401 — side effect: registers games + views

    return create_app(frontend_dist=frontend_dist)


def main() -> None:
    # LAN-visible on purpose (two browsers on the local network); public
    # exposure is Phase 9's job and gated on queue/rate-limit/Turnstile (G7).
    try:
        app = make_app()
    except FrontendBuildMissingError as e:
        raise SystemExit(str(e)) from None
    uvicorn.run(app, host="0.0.0.0", port=8000)
