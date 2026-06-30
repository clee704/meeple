# MeepleMind — Implementation Plan

> A game-agnostic platform: one engine interface, one set of AI algorithms, one
> eval harness, one web backend — reused across many games. **Kahuna is game #1**
> (next: Quarto / Splendor / Patchwork). Terminal + web play, a strategy coach,
> and a from-scratch CFR stack for ML learning. Hostable from this machine behind
> Cloudflare.
>
> **Before coding, read `CLAUDE.md`** (operating rules + hard gates). For a
> game's rules, `meeple/games/<g>/RULES.md` is authoritative.
>
> Project **MeepleMind**; Python package **`meeple`** (all sub-packages live under
> `meeple/`); CLI **`meeple`** (`meeple play kahuna`, `meeple coach`, `meeple serve`).

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
   per-game recipe in `CLAUDE.md`).

### Continuing with a smaller model
This plan + `CLAUDE.md` are written so a cheaper model can continue safely. Each
session: read `CLAUDE.md`, then this plan, then (if working a game) that game's
`RULES.md`. Obey the **hard gates** in `CLAUDE.md` literally; escalate instead of
guessing. Work one phase at a time and stop at its Definition of Done.

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
            framework/  Game · State · GameSpec · registry      ← the seam
                        ▲
        ┌───────────────┼───────────────┬──────────────┐
   games/kahuna     games/quarto     games/kuhn     OpenSpielAdapter
   (game #1)        (Phase 10)    (seam smoke-test)   (oracle only)
```

- **Solvers/search/web import only `framework/`.** They never import `games/`.
- A game is reached only through `Game`/`State`, described by a **`GameSpec`**
  (`num_players`, `perfect_information`, `has_chance`, `zero_sum`,
  `num_distinct_actions`, action labels), and discovered via a **registry**.
- The AI layer picks a compatible solver from the **solver-compatibility matrix
  in `CLAUDE.md`** using the `GameSpec` (e.g. CFR only for 2p zero-sum
  imperfect-info; MCTS for perfect-info; ISMCTS for imperfect-info; heuristic
  always). **CFR does not generalize to Quarto/Patchwork/Splendor — MCTS/ISMCTS
  does.**

**Platform components (build once, reused):** `framework/`, `ai/`, `eval/`,
`web/`, `coach`. **Per-game components (repeat via the recipe):**
`meeple/games/<g>/RULES.md`, engine, adapter, renderer, tests, `GameSpec`.

---

## Stack

- **Python**: pinned project venv. Box is 3.14.6; current OpenSpiel ships
  3.11–3.14 Linux wheels — **verify day one** (Phase 0). Keep a 3.12 venv as
  fallback (OpenSpiel is optional, so a missing wheel never blocks the platform).
- `torch` (Deep CFR), `numpy` (tabular), `rich` (terminal UI),
  `open-spiel` (**oracle only**), `fastapi`+`uvicorn` (web),
  `slowapi`/Redis (optional: rate-limit / shared state).
- Hygiene: `pyproject.toml` + lock, global seed control, a `Config` dataclass,
  checkpoints tagged with metadata (iterations, win-rates, exploitability).

---

## Core interface

```python
# meeple/framework/game.py
from abc import ABC, abstractmethod
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

class Game(ABC):
    @abstractmethod
    def new_initial_state(self) -> State: ...
    @abstractmethod
    def spec(self) -> "GameSpec": ...                          # players, info type, zero_sum, action space
```

This interface must be general enough for: 2p vs n-player (`returns` is a list),
perfect vs imperfect info, chance vs no chance. **If a new game needs a change
here, STOP and ask (CLAUDE.md G8).**

---

## Phases

> Each phase lists a **Done when** (Definition of Done). Don't start the next
> phase until the current one's Done-when holds and you've committed (G9).
> Tag: **[platform]** = build once & reuse; **[per-game]** = repeat via recipe.

### Phase 0 — Setup **[platform]**
- `git init` (so every checkpoint is revertible — G9); pinned venv;
  `pip install torch open-spiel rich`.
- **Verify the stack:** `python -c "import pyspiel; print(len(pyspiel.registered_games()))"`
  and a torch tensor op both succeed (fall back to a 3.12 venv if needed).
- `pyproject.toml`, `config.py` (seeds), package skeleton (see layout).
- **Dev hygiene tooling (CLAUDE.md G10):** `ruff`, `vulture`, `deptry`,
  `import-linter` (encode the seam G2 as a contract: `ai`/`eval`/`web` must not
  import `games`), `pytest`+coverage — all wired into `pre-commit` and CI. Seed
  `docs/TECH_DEBT.md`.
- **Done when:** clean checkout imports; smoke checks + `pre-commit run -a` pass;
  first commit made.

### Phase 1 — Framework seam **[platform]**
- `framework/game.py` (interface), `framework/spec.py` (`GameSpec`),
  `framework/registry.py` (id → `Game` factory + spec).
- **Native Kuhn poker** (`meeple/games/kuhn/`) to exercise the seam with zero OpenSpiel
  dependency. (Kuhn rules are standard — still drop a short `RULES.md`.)
- `OpenSpielAdapter` (oracle only) + `random_agent`.
- **Done when:** random agent plays full Kuhn games through the interface; Kuhn
  via your adapter and via OpenSpiel agree on `returns` over many seeded games.

### Phase 2 — Kahuna engine **[per-game]**  *(GATED by `meeple/games/kahuna/RULES.md`, G1)*
- **Resolve the 3 MUST-VERIFY items in `meeple/games/kahuna/RULES.md` first** (board
  graph + bridge count, removal cost, draw mechanics). No engine code until done.
- Encode the board (`graph.py`): adjacency + indexed bridge positions (this sets
  `num_distinct_actions`).
- Engine: atomic actions (`place`/`remove`/`end_turn`); **`recompute_control`
  fixpoint** + gain-control auto-removal + cascade; draw chance node; scoring at
  the 3 triggers (reshuffle, keep hands); supplies; `returns`.
- **Done when (G3):** tests pass for legal/illegal actions, strict-majority
  thresholds, **the cascade**, all 3 scorings + tiebreak, determinism, and a full
  playthrough; the worked-example position in RULES.md is a regression test.

### Phase 3 — Terminal UI + human-vs-human **[platform shell + per-game renderer]**
- `cli.py` game-agnostic shell; `meeple/games/kahuna/renderer.py` ASCII board (islands,
  owned/empty bridges, tokens), hand, face-up cards, scores.
- **Done when:** two humans can play a full Kahuna game in the terminal.

### Phase 4 — AI: heuristic + MCTS + ISMCTS **[platform]**  *(serves goals #1, #2, #5)*
- `ai/base.py` (Agent interface), `ai/heuristic.py` (per-game scoring hook),
  `ai/mcts.py` (UCT — perfect-info games), `ai/ismcts.py` (determinized — Kahuna,
  Splendor). Difficulty = simulation budget.
- **Done when (G5):** ISMCTS beats `random` decisively and beats the heuristic on
  Kahuna in the eval harness; agents select via the solver matrix from `GameSpec`.

### Phase 5 — Eval harness **[platform]**
- `eval/tournament.py` (head-to-head win-rates + CIs between any agents),
  `eval/exploitability.py` (your own NashConv) validated vs OpenSpiel on Kuhn.
- **Done when:** can run an N-game match between any two agents and report
  win-rate + CI; exploitability matches OpenSpiel on Kuhn.

### Phase 6 — Tabular CFR **[platform]**
- `ai/cfr/tabular.py`; validate on native Kuhn.
- **Done when:** exploitability on Kuhn → ~0 and matches OpenSpiel.

### Phase 7 — Coach / explain mode **[platform]**  *(serves goal #2)*
- `coach.py`: rank legal moves by estimated win-prob/value (ISMCTS stats),
  show the best move + swing, **narrate control changes**; `--hint` in play +
  post-game review.
- **Done when:** for a given Kahuna position, coach lists moves with win-prob and
  a human-readable reason for the top move.

### Phase 8 — Deep CFR **[platform]**  *(serves goal #3)*
- `ai/cfr/deep_cfr.py`, `ai/cfr/networks.py`, `train_deep_cfr.py`. Concrete
  info-state tensor (see RULES.md). **Advantage net per player + one strategy
  net; reservoir-sampled memories; retrain advantage net from scratch each CFR
  iteration; train strategy net once at the end** (do not "clear a replay
  buffer"). External-sampling MCCFR; consider Linear/Discounted CFR.
- **Done when:** trained strategy net beats the heuristic and is competitive with
  ISMCTS in the eval harness; training is reproducible from a seed + config.

### Phase 9 — Web backend **[platform]**  *(serves goal #4)*
- Design fact: a trained-net move = one forward pass (cheap); an ISMCTS move runs
  many sims (expensive). **Size the queue for the ISMCTS worst case.**
- FastAPI; REST (create / get-state / move→AI-reply / resign); **server
  re-validates every action** (G7). `web/registry.py` maps game-id → factory +
  renderer (game-agnostic). `web/store.py` (in-memory + TTL; Redis optional).
  `web/queue.py` (`asyncio.Semaphore(N)` + `asyncio.Queue`, returns **queue
  position**; per-move compute budget). `web/turnstile.py` (verify server-side).
- Edge: Cloudflare proxied DNS (WAF + Rate-Limiting Rules + Bot Fight Mode) +
  **Cloudflare Tunnel (`cloudflared`)** to expose this box with no port-forward.
  Run as **systemd** service; health endpoint; structured logs; global
  max-active-games cap overflowing into the queue.
- **Done when (G7):** a stranger can play Kahuna vs the AI over the internet;
  illegal moves are rejected server-side; load beyond N queues gracefully;
  Turnstile + rate limits active.

### Phase 10 — Second game (reuse proof) **[per-game]**  *(serves goal #5)*
- Add **Quarto** or **Patchwork** via the per-game recipe (RULES.md → engine →
  adapter → renderer → register). Perfect-info → reuse **MCTS**.
- **Done when (G8):** the new game is playable in terminal and web using the
  **existing** AI/eval/web core with **zero changes** to `framework/ai/web`; all
  prior games' tests still pass.

### Phase 11 — Polish / deploy **[platform]**
- Save/load checkpoints; difficulty levels; `--watch` AI-vs-AI; show move-prob
  distribution; deploy + monitor.

---

## File layout (canonical — supersedes any inline path above)

```
meeple/                         # the importable package (from meeple.framework import ...)
  framework/  game.py  spec.py  registry.py
  games/
    kahuna/   RULES.md  graph.py  engine.py  adapter.py  renderer.py  tests/
    kuhn/     RULES.md  game.py   tests/
    quarto/   ...                              # Phase 10
  ai/         base.py  heuristic.py  mcts.py  ismcts.py
              cfr/tabular.py  cfr/deep_cfr.py  cfr/networks.py
  eval/       tournament.py  exploitability.py
  web/        app.py  registry.py  queue.py  store.py  turnstile.py  static/
  coach.py  cli.py  config.py  train_deep_cfr.py
docs/         RULES_TEMPLATE.md
deploy/       cloudflared.yml  meeple.service
CLAUDE.md  PLAN.md  pyproject.toml
```

Rule of thumb: if a file names a game, it lives under `meeple/games/<g>/`. If it's in
`framework/ai/eval/web`, it must not name any game (CLAUDE.md G2/G5).

---

## Open questions

Kahuna's are tracked in **`meeple/games/kahuna/RULES.md`** (3 BLOCKING MUST-VERIFY items:
board graph/bridge count, removal cost, draw mechanics). Resolved already: deck =
24 (2/island); scoring = pile+face-up exhaustion, reshuffle, keep hands, 1/2/diff;
OpenSpiel has no Kahuna (oracle only).

---

## Starting point for next session

0. **Read `CLAUDE.md`**, then this plan, then `meeple/games/kahuna/RULES.md`.
1. **Phase 0:** `git init`; venv; verify `pyspiel` + torch import; first commit.
2. **Phase 1:** `framework/` seam + native Kuhn + random agent (no OpenSpiel
   needed to start).
3. **Phase 2 (gated):** resolve the 3 MUST-VERIFY rules items, then board graph →
   Kahuna engine + cascade tests.
4. Then **Phase 4 (ISMCTS)** for a fun opponent *before* Deep CFR.
