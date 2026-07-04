"""Request bodies the API accepts. Responses are built as plain dicts (the
state envelope's `observation`/`meta` shapes are game-defined, so a rigid
response model would add nothing)."""

from pydantic import BaseModel


class CreateMatchRequest(BaseModel):
    game_id: str
    seat: int = 0  # which seat the creator takes (seat 0 always moves first)
    seed: int | None = None  # fixed seed => reproducible deal, used by tests


class JoinMatchRequest(BaseModel):
    join_code: str


class ActionRequest(BaseModel):
    action: int
