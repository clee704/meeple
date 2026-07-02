"""Composition root: the one module that stands on both sides of the seam,
importing `meeple.games` for its registration side effect and handing the
game-agnostic web app to uvicorn. Everything under `meeple.web` never sees
a concrete game."""

import uvicorn

import meeple.games  # noqa: F401 — side effect: registers games + views
from meeple.web.app import create_app

app = create_app()


def main() -> None:
    # LAN-visible on purpose (two browsers on the local network); public
    # exposure is Phase 9's job and gated on queue/rate-limit/Turnstile (G7).
    uvicorn.run(app, host="0.0.0.0", port=8000)
