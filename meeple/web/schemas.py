"""Request bodies the API accepts. Responses are built as plain dicts (the
state envelope's `observation`/`meta` shapes are game-defined, so a rigid
response model would add nothing)."""

from pydantic import BaseModel, ConfigDict


class _Request(BaseModel):
    # Unknown fields are a version-skew signal (a rebuilt frontend talking to
    # a not-yet-restarted server): fail with a 422 instead of silently
    # dropping the field and doing something the user didn't ask for.
    model_config = ConfigDict(extra="forbid")


class CreateMatchRequest(_Request):
    game_id: str
    seat: int = 0  # which seat the creator takes (seat 0 always moves first)
    # NB: no client-supplied seed. A chosen seed would let the creator
    # reconstruct the whole deal (both hidden hands + pile order), defeating the
    # per-seat masking the view layer exists to enforce. Tests that need a fixed
    # deal call MatchStore.create(seed=...) directly, not this endpoint.


class JoinMatchRequest(_Request):
    join_code: str


class ActionRequest(_Request):
    action: int
