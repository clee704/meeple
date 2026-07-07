"""The generic FastAPI backend: match lifecycle + turn flow for any game
registered with a `GameView`. Game-specific knowledge never appears here —
it comes through the view SPI (P5), and every action is re-validated
server-side against `legal_actions` (P8).

All endpoints are `async def` without awaits: they run on the single event
loop thread, which serializes store access — no locking needed at this
scale (two LAN players). This is load-bearing and unenforced: it holds ONLY
while every handler stays await-free AND the server runs a single worker.
Adding an `await` inside a handler (e.g. awaiting an AI move) or running
`--workers N` would let store mutations race — two `/join`s claiming the same
seat, a lost `version` bump. Add a lock (or re-establish this invariant
deliberately) before doing either."""

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from meeple.framework import registry
from meeple.web.matches import (
    BadTokenError,
    IllegalActionError,
    Match,
    MatchFullError,
    MatchStore,
    NotYourTurnError,
    UnknownMatchError,
)
from meeple.web.schemas import ActionRequest, CreateMatchRequest, JoinMatchRequest

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class FrontendBuildMissingError(RuntimeError):
    """Raised when the browser server is started before the SPA is built."""


def frontend_build_missing_message(path: Path = FRONTEND_DIST) -> str:
    return (
        f"Frontend build not found at {path}. "
        "Build it with `cd frontend && npm install && npm run build`, "
        "then run `meeple` again. For frontend development, run "
        "`cd frontend && npm run dev` with the FastAPI server on port 8000."
    )


def create_app(
    store: MatchStore | None = None,
    *,
    frontend_dist: Path | None = FRONTEND_DIST,
) -> FastAPI:
    # `store` is injectable so tests can seed a fixed deal via
    # MatchStore.create(seed=...) and then drive that match over HTTP — the
    # public API deliberately offers no client seed (see CreateMatchRequest).
    store = store if store is not None else MatchStore()
    app = FastAPI(title="MeepleMind")

    def _authenticated(match_id: str, token: str) -> tuple[Match, int]:
        try:
            match = store.get(match_id)
        except UnknownMatchError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None
        try:
            return match, match.seat_for_token(token)
        except BadTokenError as e:
            raise HTTPException(status_code=403, detail=str(e)) from None

    @app.get("/api/games")
    async def list_games() -> list[dict]:
        games = [
            {"game_id": game_id, "num_players": registry.make(game_id).spec().num_players}
            for game_id in registry.games_with_views()
        ]
        for info in games:
            # Lobby seat labels (e.g. Kahuna Black/White) ride along from
            # the game view, so the frontend needs no per-game map of its own.
            info["seat_names"] = registry.make_view(info["game_id"]).seat_names()
        return games

    @app.post("/api/matches", status_code=201)
    async def create_match(req: CreateMatchRequest) -> dict:
        try:
            match, token = store.create(req.game_id, creator_seat=req.seat)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None
        except ValueError as e:  # seat out of range for this game
            raise HTTPException(status_code=422, detail=str(e)) from None
        return {
            "match_id": match.match_id,
            "join_code": match.join_code,
            "game_id": match.game_id,
            "seat": req.seat,
            "token": token,
        }

    @app.post("/api/matches/join")
    async def join_match(req: JoinMatchRequest) -> dict:
        try:
            match, seat, token = store.join(req.join_code)
        except UnknownMatchError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None
        except MatchFullError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None
        return {
            "match_id": match.match_id,
            "join_code": match.join_code,
            "game_id": match.game_id,
            "seat": seat,
            "token": token,
        }

    @app.get("/api/matches/{match_id}/state")
    async def get_state(
        match_id: str,
        since: int | None = None,
        x_seat_token: str = Header(),
    ) -> dict:
        match, seat = _authenticated(match_id, x_seat_token)
        if since is not None and match.version == since:
            return {"changed": False, "version": match.version}
        # `meta` (static renderer bootstrap) only accompanies the initial
        # fetch — pollers pass `since` and never re-download it. `since`
        # also serves as the history cursor: only entries appended after
        # that version ride along.
        return match.envelope(seat, include_meta=since is None, since=since)

    @app.post("/api/matches/{match_id}/actions")
    async def post_action(
        match_id: str,
        req: ActionRequest,
        x_seat_token: str = Header(),
    ) -> dict:
        match, seat = _authenticated(match_id, x_seat_token)
        try:
            match.apply(seat, req.action)
        except (NotYourTurnError, IllegalActionError) as e:
            raise HTTPException(status_code=409, detail=str(e)) from None
        return match.envelope(seat, include_meta=False)

    @app.post("/api/matches/{match_id}/leave")
    async def leave_match(match_id: str, x_seat_token: str = Header()) -> dict:
        match, seat = _authenticated(match_id, x_seat_token)
        try:
            match.leave(seat)
        except IllegalActionError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None
        return match.envelope(seat, include_meta=False)

    if frontend_dist is not None:
        if not frontend_dist.is_dir():
            raise FrontendBuildMissingError(frontend_build_missing_message(frontend_dist))
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app
