"""GameSpec — the static description the AI layer uses to pick a compatible
solver (e.g. CFR only applies to 2-player zero-sum imperfect-info games).
Code that consumes a GameSpec should branch on these properties, never on a
specific game's name."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameSpec:
    num_players: int
    perfect_information: bool
    has_chance: bool
    zero_sum: bool
    num_distinct_actions: int
    action_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.action_names) != self.num_distinct_actions:
            raise ValueError(
                f"action_names has {len(self.action_names)} entries, "
                f"expected num_distinct_actions={self.num_distinct_actions}"
            )
