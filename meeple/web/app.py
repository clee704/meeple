"""The generic FastAPI backend: match lifecycle + turn flow for any game
registered with a `GameView`. Game-specific knowledge never appears here —
it comes through the view SPI (P5), and every action is re-validated
server-side against `legal_actions` (P8).

All endpoints are `async def` without awaits: they run on the single event
loop thread, which serializes store access — no locking needed at this
scale (two LAN players)."""

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

_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app() -> FastAPI:
    store = MatchStore()
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
        return [
            {"game_id": game_id, "num_players": registry.make(game_id).spec().num_players}
            for game_id in registry.games_with_views()
        ]

    @app.post("/api/matches", status_code=201)
    async def create_match(req: CreateMatchRequest) -> dict:
        try:
            match, token = store.create(req.game_id, req.seed)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None
        return {
            "match_id": match.match_id,
            "join_code": match.join_code,
            "game_id": match.game_id,
            "seat": 0,
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
        # fetch — pollers pass `since` and never re-download it.
        return match.envelope(seat, include_meta=since is None)

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
            match.forfeit(seat)
        except IllegalActionError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None
        return match.envelope(seat, include_meta=False)

    if _FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")

    return app
