# MeepleMind — Strategic Plan

> A game-agnostic platform: one engine interface, one set of AI algorithms, one
> eval harness, one web backend — reused across many games. **Kahuna is game #1**
> (next: Quarto / Splendor / Patchwork). Terminal + web play, a strategy coach,
> and a from-scratch CFR stack for ML learning. Hostable from this machine behind
> Cloudflare.
>
> **Before coding, read `AGENTS.md`** (operating rules + hard gates — this
> doc is the *what*, that one is the *how*). For a game's rules,
> `meeple/games/<g>/RULES.md` is authoritative.
>
> This is the durable strategic reference and changes rarely. Granular,
> per-phase progress (checklists, decisions, blockers) lives in each phase's
> GitHub issue (labeled `phase`), not here — a session should be able to
> resume from this file + the open issues alone, without any chat history.
>
> Project **MeepleMind**; Python package **`meeple`** (all sub-packages live under
> `meeple/`); CLI **`meeple`** (runs the web server — play happens in the
> browser; there is no terminal UI).

## Goals (priority order)

1. **Fun:** play against a genuinely good AI. *Ship a strong opponent early — do
   not gate this on Deep CFR.*
2. **Learn strategy:** a **coach mode** that explains the best
   move, its win-probability swing, and the control changes it causes.
3. **Deep ML learning:** re-implement the core from scratch — own `Game`/`State`
   interface, own engines, own tabular + Deep CFR, own exploitability calculator.
   OpenSpiel is a **reference/validation oracle only**, never a game backend.
4. **Host it:** backend on this machine, behind Cloudflare, with bot protection
   (Turnstile) and a wait queue to bound concurrent AI requests.
5. **Reuse for other games:** the engine interface, AI, eval, and web backend
   must work for **Quarto, Splendor, Patchwork** with **no core changes** —
   adding a game = rules contract + engine + adapter + renderer (see the
   per-game recipe in `AGENTS.md`).

### Scoping goal #3 (so it doesn't become infinite)
"From scratch" = your interface + engines + tabular CFR + Deep CFR + an
exploitability/NashConv calculator, plus a **native Kuhn** impl to exercise the
interface without OpenSpiel. It does **not** mean re-implementing OpenSpiel's
breadth. OpenSpiel stays the oracle you cross-check CFR against on Kuhn/Leduc.

---

## Architecture (the seam is the whole design)

```
   AI layer (game-agnostic)            Web backend (game-agnostic)
   heuristic · MCTS · ISMCTS ·         FastAPI · queue · store · Turnstile
   tabular CFR · Deep CFR · coach          │  uses framework/registry +
        │  imports ONLY framework/         │  a per-game renderer
        └───────────────┬─────────────────┘
                        ▼
            framework/  Game · State · GameSpec · GameView · registry   ← the seam
                        ▲
        ┌───────────────┼───────────────┬──────────────┐
   games/kahuna     games/quarto     games/kuhn     OpenSpielAdapter
   (game #1)      (reuse proof)   (seam smoke-test)   (oracle only)
```

- **Solvers/search/web import only `framework/`.** They never import `games/`.
- A game is reached only through `Game`/`State`, described by a **`GameSpec`**
  (`num_players`, `perfect_information`, `has_chance`, `zero_sum`,
  `num_distinct_actions`, action labels), and discovered via a **registry**.
- The AI layer picks a compatible solver from the **solver-compatibility matrix
  in `AGENTS.md`** using the `GameSpec` (e.g. CFR only for 2p zero-sum
  imperfect-info; MCTS for perfect-info; ISMCTS for imperfect-info; heuristic
  always). **CFR does not generalize to Quarto/Patchwork/Splendor — MCTS/ISMCTS
  does.**
- The interface's current shape is a best guess, not final — see AGENTS.md's
  P1: if a game keeps forcing awkward workarounds, that's signal to
  deliberately revise `Game`/`State`, not route around it.

**Platform components (build once, reused):** `framework/`, `ai/`, `eval/`,
`web/`, `coach`. **Per-game components (repeat via the recipe):**
`meeple/games/<g>/RULES.md`, engine, adapter, renderer, tests, `GameSpec`.

---

## Stack

- **Python 3.12**, pinned. A plain `torch` + CUDA smoke test also passes on
  3.14 on this box, but 3.12 is the safer choice while the wider ML tooling
  ecosystem catches up to 3.14 — this box hit a hard error serving a model via
  vLLM on 3.14 recently, and this project will eventually lean on that same
  ecosystem for Deep CFR training. Re-evaluate 3.14 later if the ecosystem
  stabilizes.
- `torch` (Deep CFR), `numpy` (tabular), `open-spiel` (**oracle only**),
  `fastapi`+`uvicorn`+`pydantic` (web backend), React+Vite+TypeScript
  (`frontend/`, built to `frontend/dist` and served by the backend),
  `slowapi`/Redis (optional: rate-limit / shared state, Phase 9).
- Hygiene: `pyproject.toml` + lock, global seed control, a `Config` dataclass,
  checkpoints tagged with metadata (iterations, win-rates, exploitability).

---

## Core interface

```python
# meeple/framework/game.py
from abc import ABC, abstractmethod
import random
import torch
Action = int
CHANCE = -1

class State(ABC):
    @abstractmethod
    def legal_actions(self) -> list[Action]: ...
    @abstractmethod
    def apply_action(self, action: Action) -> "State": ...     # MUST be cheap to clone (CFR/MCTS recurse a lot)
    @abstractmethod
    def is_terminal(self) -> bool: ...
    @abstractmethod
    def returns(self) -> list[float]: ...                      # per-player payoff at terminal
    @abstractmethod
    def current_player(self) -> int: ...                       # -1 chance, else player index
    @abstractmethod
    def chance_outcomes(self) -> list[tuple[Action, float]]: ...
    @abstractmethod
    def information_state_tensor(self, player: int) -> torch.Tensor: ...  # Deep CFR input
    @abstractmethod
    def information_state_key(self, player: int) -> str: ...    # tabular CFR info-set key
    # ISMCTS determinization: a full state sampled from the worlds consistent
    # with `player`'s info set. Perfect-info games `return self` (immutable).
    @abstractmethod
    def resample_from_infostate(self, player: int, rng: random.Random) -> "State": ...

class Game(ABC):
    @abstractmethod
    def new_initial_state(self) -> State: ...
    @abstractmethod
    def spec(self) -> "GameSpec": ...                          # players, info type, zero_sum, action space
```

This interface must be general enough for: 2p vs n-player (`returns` is a list),
perfect vs imperfect info, chance vs no chance. If a new game needs a change
here, that's a deliberate interface revision (propose it, don't route around
it — AGENTS.md G8), not a quick patch.

**Information-state contract:** `information_state_key(player)` returns the
player's full observation history — information states are **perfect
recall**. Engines derive the key from an append-only action log carried by
the state (chance outcomes masked per viewer), so recall holds by
construction; the log is the state's canonical representation, and zone
fields (hands, piles, board) are caches kept for O(1) simulation.
`information_state_tensor` is the only place a lossy fixed-size encoding is
permitted, and each game's RULES.md documents exactly what that encoding
drops. Agent-side belief models (e.g. difficulty via imperfect memory,
[#12](https://github.com/clee704/meeple/issues/12)) consume what the state
encodes; they never substitute for encoding it.

A game opts into the web UI by also registering a **`GameView`**
(`meeple/framework/view.py`) next to its `Game`: per-player JSON
`observation` (only what that viewer may see), structured `action_metadata`
for the frontend renderer, `describe_action` (viewer-masked move history),
`result`, and static `game_meta`. The backend is built entirely on this SPI;
the only per-game frontend code is one React renderer component registered
by game id in `frontend/src/games/registry.tsx`.

---

## Phases

Each phase's Definition of Done, checklist, and running log of decisions lives
in its GitHub issue (label `phase`). Don't start a phase before the previous
one's issue is closed. **[platform]** = build once & reuse; **[per-game]** =
repeat via the onboarding recipe in `AGENTS.md`.

| # | Phase | Tag | Scope | Issue |
|---|-------|-----|-------|-------|
| 0 | Setup | platform | venv, `pyproject.toml`, dev tooling (ruff/vulture/deptry/import-linter/pytest), pre-commit + CI | [#1](https://github.com/clee704/meeple/issues/1) (closed) |
| 1 | Framework seam | platform | `Game`/`State`/`GameSpec`/registry, native Kuhn poker, `OpenSpielAdapter` (oracle), `random_agent` | [#2](https://github.com/clee704/meeple/issues/2) (closed) |
| 2 | Kahuna engine | per-game | gated on `meeple/games/kahuna/RULES.md`'s 3 open `MUST-VERIFY` items; board graph, engine, cascade, scoring | [#3](https://github.com/clee704/meeple/issues/3) (closed) |
| 3 | Web UI (local) | shell + per-game renderer | `GameView` SPI, game-agnostic FastAPI match backend + React SPA shell, per-game renderers (Kahuna, Kuhn); human-vs-human over LAN | [#4](https://github.com/clee704/meeple/issues/4) |
| 4 | AI: heuristic + ISMCTS | platform | `ai/base.py`, `ai/heuristic.py` + per-game evaluation hook, determinization SPI (`resample_from_infostate`), `ai/ismcts.py`, minimal `eval/tournament.py`, AI seat in web matches | [#5](https://github.com/clee704/meeple/issues/5) |
| 5 | Eval harness | platform | extends Phase 4's minimal `eval/tournament.py`; `eval/exploitability.py` validated vs OpenSpiel on Kuhn | [#6](https://github.com/clee704/meeple/issues/6) |
| 6 | Tabular CFR | platform | `ai/cfr/tabular.py`, validated on native Kuhn | [#7](https://github.com/clee704/meeple/issues/7) |
| 7 | Coach / explain mode | platform | rank legal moves by win-prob, narrate control changes, `--hint` | [#8](https://github.com/clee704/meeple/issues/8) |
| 8 | Deep CFR | platform | `ai/cfr/deep_cfr.py`, advantage/strategy nets, external-sampling MCCFR | [#9](https://github.com/clee704/meeple/issues/9) |
| 9 | Deployment hardening | platform | wait queue, per-IP rate limit, Turnstile, persistent store, Cloudflare Tunnel + systemd (G7 gate before any public exposure) | [#10](https://github.com/clee704/meeple/issues/10) |
| 10 | Second game (reuse proof) | per-game | preceded by `ai/mcts.py` (plain UCT — needs this phase's perfect-info game to validate) as its own platform commit; then Quarto or Patchwork via the recipe, zero core changes | [#11](https://github.com/clee704/meeple/issues/11) |
| 11 | Polish / deploy | platform | checkpoints, difficulty levels (simulation budget + human-like imperfect-memory models — design sketched in #12), `--watch`, monitoring | [#12](https://github.com/clee704/meeple/issues/12) |

Status right now: **Phases 0-3 done** (tooling; framework seam, native Kuhn,
`OpenSpielAdapter`, `random_agent`; Kahuna engine merged in #15; web UI —
`GameView` SPI, FastAPI backend, React frontend with Kahuna/Kuhn renderers,
human-vs-human over LAN, see #4. The terminal-UI plan was dropped in favor of
going straight to the web UI; there is no terminal UI). **Phase 4 (AI: heuristic +
ISMCTS) is next** — see [#5](https://github.com/clee704/meeple/issues/5).

---

## File layout (canonical — supersedes any inline path above)

```
meeple/                         # the importable package (from meeple.framework import ...)
  framework/  game.py  spec.py  registry.py  view.py  chance.py
  games/                        # tests are co-located test_*.py files throughout
    kahuna/   RULES.md  graph.py  engine.py  view.py  board.svg
    kuhn/     RULES.md  engine.py  view.py
    quarto/   ...                              # second-game reuse proof
  ai/         random_agent.py  (later: heuristic.py  mcts.py  ismcts.py
              cfr/tabular.py  cfr/deep_cfr.py  cfr/networks.py)
  eval/       tournament.py  exploitability.py
  web/        app.py  matches.py  schemas.py   # game-agnostic; queue/turnstile arrive in Phase 9
  serve.py                      # composition root: registers games, runs uvicorn (the `meeple` script)
  coach.py  config.py  train_deep_cfr.py       # later phases
frontend/     React+Vite SPA — src/ shell + src/games/ per-game renderers; dist/ served by the backend
docs/         RULES_TEMPLATE.md
deploy/       cloudflared.yml  meeple.service  # Phase 9
AGENTS.md  CLAUDE.md  PLAN.md  pyproject.toml
```

Rule of thumb: if a file names a game, it lives under `meeple/games/<g>/`. If it's in
`framework/ai/eval/web`, it must not name any game (AGENTS.md G2/G5).
