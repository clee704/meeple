"""In-memory match store: lifecycle (create → join → play → finish), per-seat
auth tokens, and the per-viewer state envelope the API serves. Matches are
lost on restart — fine for the local/LAN scope; persistence would swap in
behind the same `MatchStore` methods."""

import random
import secrets
from dataclasses import dataclass, field

from meeple.framework import registry
from meeple.framework.chance import resolve_chance
from meeple.framework.game import Game, State
from meeple.framework.view import GameView

# Join codes avoid easily-confused characters (0/O, 1/I/L).
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 5


class MatchError(Exception):
    """Base for domain failures the API layer maps onto HTTP errors."""


class UnknownMatchError(MatchError):
    pass


class BadTokenError(MatchError):
    pass


class MatchFullError(MatchError):
    pass


class NotYourTurnError(MatchError):
    pass


class IllegalActionError(MatchError):
    pass


@dataclass
class Match:
    match_id: str
    join_code: str
    game_id: str
    game: Game
    view: GameView
    state: State
    rng: random.Random
    tokens: list[str | None]
    # One history per seat: entries are pre-masked by `describe_action` at
    # append time, so a viewer's log never holds what they may not see.
    histories: list[list[dict]]
    version: int = 1

    @property
    def status(self) -> str:
        if None in self.tokens:
            return "waiting"
        return "finished" if self.state.is_terminal() else "in_progress"

    def seat_for_token(self, token: str) -> int:
        for seat, seat_token in enumerate(self.tokens):
            if seat_token is not None and secrets.compare_digest(seat_token, token):
                return seat
        raise BadTokenError("bad seat token")

    def apply(self, seat: int, action: int) -> None:
        if self.status != "in_progress":
            raise NotYourTurnError(f"match is {self.status}, not in progress")
        if self.state.current_player() != seat:
            raise NotYourTurnError(f"it is seat {self.state.current_player()}'s turn")
        # The server, not the client, is authoritative about legality.
        if action not in self.state.legal_actions():
            raise IllegalActionError(f"action {action} is not legal now")
        self.state = self.state.apply_action(action)
        for viewer in range(len(self.tokens)):
            entry = {"actor": seat, "meta": self.view.describe_action(action, viewer, seat)}
            self.histories[viewer].append(entry)
        self.state = resolve_chance(self.state, self.rng)
        self.version += 1

    def envelope(self, seat: int, include_meta: bool) -> dict:
        spec = self.game.spec()
        in_progress = self.status == "in_progress"
        your_turn = in_progress and self.state.current_player() == seat
        env = {
            "version": self.version,
            "game_id": self.game_id,
            "seat": seat,
            "status": self.status,
            "to_move": self.state.current_player() if in_progress else None,
            "your_turn": your_turn,
            "observation": self.view.observation(self.state, seat),
            "legal_actions": [
                {"action": a, "name": spec.action_names[a], "meta": self.view.action_metadata(a)}
                for a in (self.state.legal_actions() if your_turn else [])
            ],
            "history": list(self.histories[seat]),
            "result": self.view.result(self.state) if self.state.is_terminal() else None,
        }
        if include_meta:
            env["meta"] = self.view.game_meta()
        return env


@dataclass
class MatchStore:
    _matches: dict[str, Match] = field(default_factory=dict)
    _by_code: dict[str, str] = field(default_factory=dict)

    def create(self, game_id: str, seed: int | None = None) -> tuple[Match, str]:
        view = registry.make_view(game_id)  # KeyError for games without a web view
        game = registry.make(game_id)
        rng = random.Random(secrets.randbits(64) if seed is None else seed)
        num_players = game.spec().num_players
        token = secrets.token_urlsafe(16)
        match = Match(
            match_id=secrets.token_urlsafe(9),
            join_code=self._new_join_code(),
            game_id=game_id,
            game=game,
            view=view,
            state=resolve_chance(game.new_initial_state(), rng),
            rng=rng,
            tokens=[token] + [None] * (num_players - 1),
            histories=[[] for _ in range(num_players)],
        )
        self._matches[match.match_id] = match
        self._by_code[match.join_code] = match.match_id
        return match, token

    def join(self, join_code: str) -> tuple[Match, int, str]:
        match_id = self._by_code.get(join_code.strip().upper())
        if match_id is None:
            raise UnknownMatchError(f"no match with join code {join_code!r}")
        match = self._matches[match_id]
        if None not in match.tokens:
            raise MatchFullError("all seats are taken")
        seat = match.tokens.index(None)
        token = secrets.token_urlsafe(16)
        match.tokens[seat] = token
        match.version += 1  # wakes the creator's poll: status flips to in_progress
        return match, seat, token

    def get(self, match_id: str) -> Match:
        try:
            return self._matches[match_id]
        except KeyError:
            raise UnknownMatchError(f"unknown match {match_id!r}") from None

    def _new_join_code(self) -> str:
        while True:
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
            if code not in self._by_code:
                return code
