"""ISMCTS determinization for Kahuna (`KahunaState.resample_from_infostate`):
sample a full state consistent with everything a viewer has observed, by
replaying the state's public action log from a fresh initial state with the
hidden parts re-sampled.

What the viewer's masked log hides is the identity behind exactly two kinds
of event: the opponent's blind draws (including their initial deal) and the
opponent's face-down discards. Those identities are tightly constrained —
the opponent's *open* plays prove they held specific cards at specific
times, every forced observed outcome needs its card in the pile at that
moment, and each reshuffle rebuilds the pile from exactly what was
discarded since the previous one — so independent guessing almost never
produces a consistent world. Instead:

1. `_compile` flattens the masked log into the viewer's-eye card flow: ops
   that move known identities (observed deals and draws, face-up takes,
   open plays, the viewer's own face-down discards, reshuffles) and the
   two *decision* ops for the opponent's hidden identities.
2. `_search` runs a randomized depth-first search over the decisions in
   chronological order, simulating the pile, the opponent's hand, and the
   discard accumulator as multisets. A branch dies when a forced outcome
   is missing from the pile, an open play exceeds the hypothetical hand,
   or the pile isn't empty at a reshuffle (scoring only triggers on
   depletion, which is what makes each epoch's draws exhaust its pile). A
   per-epoch balance ledger — observed + hidden draws vs. pile contents,
   where a hidden discard in epoch e "returns" into epoch e+1's pile —
   prunes doomed branches early instead of deep. Candidate identities are
   tried in a copies-weighted random order, so the first solution found is
   a plausible (if not exactly posterior-weighted) sample.
3. `_apply` re-applies the whole log through the real engine with every
   hidden identity forced to its chosen value; `apply_action`'s legality
   checks backstop the whole construction.

The support is exactly the worlds consistent with
`information_state_key(viewer)`, including the interleaving constraints
the log carries, and the sample is internally consistent: its zones are
derived from its own replayed log. World *weights* approximate the exact
posterior rather than equalling it (the search takes the first completable
branch of a shuffled tree); sampling the exact posterior under the log's
constraints has no cheap closed form. Opponent decisions are deliberately
not modeled at all — belief-weighted determinization belongs in `ai/`,
layered over this sampler (see the `State.resample_from_infostate`
contract).
"""

import random
from collections import Counter
from dataclasses import dataclass

from meeple.framework.game import CHANCE, Action
from meeple.games.kahuna.engine import (
    BRIDGES,
    DECK,
    DISCARD_BASE,
    DRAW_BLIND,
    FACEUP_BASE,
    NUM_FACEUP_SLOTS,
    PLACE_B_BASE,
    REMOVE_AA_BASE,
    REMOVE_AB_BASE,
    REMOVE_BB_BASE,
    SKIP,
    KahunaGame,
    KahunaState,
    _LogNode,
)
from meeple.games.kahuna.graph import ISLANDS

_MAX_ATTEMPTS = 20
_SEARCH_BUDGET = 20_000  # candidate applications per attempt; restarts reshuffle


def resample_from_infostate(state: KahunaState, viewer: int, rng: random.Random) -> KahunaState:
    entries: list[_LogNode] = []
    node = state.log
    while node is not None:
        entries.append(node)
        node = node.parent
    entries.reverse()

    flow = _compile(entries, viewer)
    for _ in range(_MAX_ATTEMPTS):
        choices = _search(flow, rng)
        if choices is None:
            continue
        sample = _apply(entries, viewer, *choices)
        if sample is not None:
            return sample
    # The true world is always reachable, so exhausting the attempts is
    # statistically impossible short of a bug in the search above.
    raise RuntimeError(f"no world consistent with the log sampled in {_MAX_ATTEMPTS} attempts")


def _spent_cards(action: Action) -> tuple[str, ...]:
    """Which card(s) a place/remove action pays — the identities are part
    of the action encoding (see the engine's module docstring)."""
    a, b = BRIDGES[action % len(BRIDGES)]
    if action < PLACE_B_BASE:
        return (a,)
    if action < REMOVE_AA_BASE:
        return (b,)
    if action < REMOVE_BB_BASE:
        return (a, a)
    if action < REMOVE_AB_BASE:
        return (b, b)
    return (a, b)


# One op per card movement the viewer can reason about, in log order:
#   ("draw_seen", island, epoch)    observed deal/draw: pile -> a visible zone
#   ("draw_hidden", epoch)          DECISION: pile -> opponent hand
#   ("gain", island)                witnessed face-up take -> opponent hand
#   ("spend", cards)                opponent's open play: hand -> discards
#   ("shed", cards)                 viewer's open play / face-down discard -> discards
#   ("discard_hidden", index, epoch)  DECISION: opponent hand -> hidden discards
#   ("reshuffle",)                  discards become the new pile (pile must be empty)
_Op = tuple


@dataclass
class _Flow:
    ops: list[_Op]
    num_epochs: int
    # Per-epoch balance constants: observed draws (left side) and known
    # pile contents (right side: the deck for epoch 0, known returns
    # after); decisions add to the live sides during the search.
    observed: list[Counter]
    known_pile: list[Counter]


def _compile(entries: list[_LogNode], viewer: int) -> _Flow:
    face_up: list[str | None] = [None] * NUM_FACEUP_SLOTS
    ops: list[_Op] = []
    epoch = 0
    previous_was_reshuffle = False
    observed = [Counter()]
    known_pile = [Counter(DECK)]

    for index, entry in enumerate(entries):
        if entry.actor == CHANCE:
            card = ISLANDS[entry.action]
            destination = entry.destination
            if destination.startswith("reshuffle:"):
                destination = destination.removeprefix("reshuffle:")
                if not previous_was_reshuffle:
                    epoch += 1
                    observed.append(Counter())
                    known_pile.append(Counter())
                    ops.append(("reshuffle",))
                previous_was_reshuffle = True
            else:
                previous_was_reshuffle = False
            if destination == f"hand{1 - viewer}":
                ops.append(("draw_hidden", epoch))
            else:
                if destination.startswith("faceup"):
                    face_up[int(destination[len("faceup") :])] = card
                ops.append(("draw_seen", card, epoch))
                observed[epoch][card] += 1
            continue
        previous_was_reshuffle = False
        action = entry.action
        if FACEUP_BASE <= action < SKIP:
            slot = action - FACEUP_BASE
            if entry.actor != viewer:
                ops.append(("gain", face_up[slot]))
            face_up[slot] = None
        elif action in (DRAW_BLIND, SKIP):
            continue
        elif action >= DISCARD_BASE:
            if entry.actor == viewer:
                ops.append(("shed", (ISLANDS[action - DISCARD_BASE],)))
            else:
                ops.append(("discard_hidden", index, epoch))
        else:
            cards = _spent_cards(action)
            ops.append(("spend", cards) if entry.actor != viewer else ("shed", cards))

    # Openly-discarded cards (both players' plays, the viewer's face-down
    # discards) return into the *next* epoch's pile.
    epoch = 0
    for op in ops:
        if op[0] == "reshuffle":
            epoch += 1
        elif op[0] in ("spend", "shed") and epoch + 1 < len(known_pile):
            for card in op[1]:
                known_pile[epoch + 1][card] += 1
    return _Flow(ops, epoch + 1, observed, known_pile)


def _search(flow: _Flow, rng: random.Random) -> tuple[list[str], dict[int, str]] | None:
    """Choose an island for every hidden draw and hidden discard such that
    the whole flow simulates cleanly. Returns the draw identities in op
    order and the discard identities by log-entry index."""
    pile = Counter(DECK)
    hand: Counter = Counter()
    discards: Counter = Counter()
    lhs = [Counter(observed) for observed in flow.observed]
    rhs = [Counter(known) for known in flow.known_pile]
    pending_draws = [0] * flow.num_epochs  # decision potentials, by epoch
    pending_returns = [0] * flow.num_epochs
    for op in flow.ops:
        if op[0] == "draw_hidden":
            pending_draws[op[1]] += 1
        elif op[0] == "discard_hidden" and op[2] + 1 < flow.num_epochs:
            pending_returns[op[2] + 1] += 1

    def balanced(epoch: int) -> bool:
        # Necessary for the pending decisions to complete this epoch's
        # balance; the final epoch never fully drains, so only draws
        # exceeding the possible pile invalidate it there.
        for island in ISLANDS:
            drawn, in_pile = lhs[epoch][island], rhs[epoch][island]
            if drawn > in_pile + pending_returns[epoch]:
                return False
            if epoch < flow.num_epochs - 1 and in_pile > drawn + pending_draws[epoch]:
                return False
        return True

    if not all(balanced(epoch) for epoch in range(flow.num_epochs)):
        return None
    draw_choices: list[str] = []
    discard_choices: dict[int, str] = {}
    budget = _SEARCH_BUDGET

    def candidates(zone: Counter) -> list[str]:
        # Distinct islands in a copies-weighted random order.
        instances = list(zone.elements())
        rng.shuffle(instances)
        return list(dict.fromkeys(instances))

    def run(position: int) -> bool:
        nonlocal budget
        undo: list[_Op] = []

        def fail() -> bool:
            for op in reversed(undo):
                if op[0] == "reshuffle":
                    pile.clear()
                    pile.update(op[1])
                    discards.clear()
                    discards.update(op[2])
                else:
                    op[1][op[2]] -= op[3]
            return False

        while position < len(flow.ops):
            op = flow.ops[position]
            kind = op[0]
            if kind == "draw_seen":
                island = op[1]
                if pile[island] == 0:
                    return fail()
                # Already counted in the ledger's observed prefill.
                pile[island] -= 1
                undo.append(("", pile, island, -1))
            elif kind == "gain":
                hand[op[1]] += 1
                undo.append(("", hand, op[1], 1))
            elif kind in ("spend", "shed"):
                for card in op[1]:
                    if kind == "spend":
                        if hand[card] == 0:
                            return fail()
                        hand[card] -= 1
                        undo.append(("", hand, card, -1))
                    discards[card] += 1
                    undo.append(("", discards, card, 1))
            elif kind == "reshuffle":
                if any(count > 0 for count in pile.values()):
                    return fail()
                undo.append(("reshuffle", dict(pile), dict(discards)))
                pile.clear()
                pile.update(discards)
                discards.clear()
            else:  # a decision: draw_hidden or discard_hidden
                if kind == "draw_hidden":
                    epoch, return_epoch = op[1], None
                    zone = pile
                else:
                    epoch = op[2] + 1 if op[2] + 1 < flow.num_epochs else None
                    return_epoch = epoch
                    zone = hand
                if return_epoch is not None:
                    pending_returns[return_epoch] -= 1
                elif kind == "draw_hidden":
                    pending_draws[epoch] -= 1
                for island in candidates(zone):
                    if budget <= 0:
                        break
                    budget -= 1
                    zone[island] -= 1
                    checked = []
                    if kind == "draw_hidden":
                        hand[island] += 1
                        lhs[epoch][island] += 1
                        checked.append(epoch)
                        draw_choices.append(island)
                    else:
                        discards[island] += 1
                        if return_epoch is not None:
                            rhs[return_epoch][island] += 1
                            checked.append(return_epoch)
                        discard_choices[op[1]] = island
                    if all(balanced(e) for e in checked) and run(position + 1):
                        return True
                    zone[island] += 1
                    if kind == "draw_hidden":
                        hand[island] -= 1
                        lhs[epoch][island] -= 1
                        draw_choices.pop()
                    else:
                        discards[island] -= 1
                        if return_epoch is not None:
                            rhs[return_epoch][island] -= 1
                        del discard_choices[op[1]]
                if return_epoch is not None:
                    pending_returns[return_epoch] += 1
                elif kind == "draw_hidden":
                    pending_draws[epoch] += 1
                return fail()
            position += 1
        return True

    if run(0):
        return draw_choices, discard_choices
    return None


def _apply(
    entries: list[_LogNode],
    viewer: int,
    draw_choices: list[str],
    discard_choices: dict[int, str],
) -> KahunaState | None:
    state = KahunaGame().new_initial_state()
    draw_iter = iter(draw_choices)
    for index, entry in enumerate(entries):
        if entry.actor == CHANCE:
            if entry.destination == f"hand{1 - viewer}":
                action = ISLANDS.index(next(draw_iter))
            else:
                action = entry.action
        elif index in discard_choices:
            action = DISCARD_BASE + ISLANDS.index(discard_choices[index])
        else:
            action = entry.action
        try:
            state = state.apply_action(action)
        except ValueError:
            # By construction this shouldn't fire — the search simulated
            # every constraint the engine checks — but a sampler bug must
            # surface as a RuntimeError upstream, never as a silently
            # wrong world.
            return None
    return state
