# CLAUDE.md — Operating contract for MeepleMind

> **Read this fully at the start of every session, before doing anything.**
> Then read `PLAN.md` (the roadmap). If you are working on a specific
> game, also read `games/<game>/RULES.md`. Work within the current phase only.
>
> This file exists so that a *smaller/cheaper model* can continue the project
> safely. It is intentionally prescriptive. When in doubt, follow the gates
> below literally and escalate to the human rather than improvising.

## What this project is

A **game-agnostic board-game AI platform**. The same engine interface, AI
algorithms, evaluation harness, and web backend are reused across many games.
**Kahuna is game #1.** Planned next: **Quarto, Splendor, Patchwork**. The whole
point is that adding a game requires *no changes* to the AI / web / eval core.

Goals (priority order): (1) fun opponent, (2) a coach that teaches strategy,
(3) from-scratch ML learning (own interface/engine/CFR), (4) host it from this
machine behind Cloudflare, (5) reuse the backend for other games.

**Identity:** project **MeepleMind**; Python package **`meeple`** — everything
(`framework/`, `ai/`, `eval/`, `web/`, `games/`) lives under `meeple/`, e.g.
`from meeple.framework import Game`. CLI **`meeple`** (`meeple play kahuna`,
`meeple coach kahuna`, `meeple serve`). Below, a bare `framework/` etc. refers to
that `meeple/` sub-package.

## Guiding principles

- **P1 — The seam is sacred.** AI / eval / web import *only* `framework/`. Game
  code lives under `games/<g>/` and is reached only through the interface.
- **P2 — Rules before code.** Never implement a game from memory. The verified
  `games/<g>/RULES.md` must exist and be signed off first (see Gate G1).
- **P3 — Test before moving on.** Every engine ships with passing tests.
- **P4 — Simplest strong opponent first.** Heuristic → ISMCTS gives a fun, strong
  opponent fast. Deep CFR is the later ML capstone, *not* the first AI.
- **P5 — Game-agnostic by default.** Core code (`framework/ai/eval/web`) must
  never reference a specific game by name. Anything game-specific is in
  `games/<g>/` or expressed through `GameSpec`.
- **P6 — Verify, don't assume.** Check that a library imports, a game is
  registered, a rule is real — by running a command or citing a source.
- **P7 — One phase at a time.** Build the smallest shippable increment. Do not
  start a later phase before the current one is "done" (see Definition of Done
  in `PLAN.md`).
- **P8 — Server is authoritative.** The web backend re-validates every move.
- **P9 — Reversibility.** `git commit` at every green checkpoint so work can be
  undone.
- **P10 — Escalate, don't guess.** When blocked, STOP and ask the human.

## Mandatory safeguards (HARD GATES — never bypass)

- **G1 — RULES-FIRST (BLOCKING).** No engine / game-logic code for game *X* until
  `meeple/games/X/RULES.md` exists, **every rule is cited to a source**, all
  `MUST-VERIFY` items are resolved, and the **"Human verified" checkbox is
  checked**. If any rule is uncertain, mark it `MUST-VERIFY` and **STOP — ask the
  human.** Do not infer rules from training data.
- **G2 — SEAM.** `ai/`, `eval/`, `web/` import only `framework/` (+ std/3rd-party).
  They must **never** import from `games/`. `games/X/` imports only `framework/`.
  If you feel you must break this, the interface is wrong — **STOP and ask.**
- **G3 — TESTS.** Every engine has passing tests covering: legal-action
  generation, **illegal-action rejection**, terminal detection, scoring /
  win-condition, **determinism under a fixed seed**, and one full playthrough. A
  phase is never "done" with failing or skipped tests.
- **G4 — SOLVER MATCH.** Choose the AI via the **solver-compatibility matrix**
  below. Never run CFR on a game that is not 2-player zero-sum imperfect-info.
  Default to MCTS / ISMCTS.
- **G5 — EVAL, NOT VIBES.** A new agent isn't "done" until the tournament harness
  shows it beats `random` decisively and it has been measured vs the heuristic.
- **G6 — ENV.** Verify the environment before relying on it. **OpenSpiel is
  oracle-only and optional** — never a game backend, never a hard dependency.
- **G7 — WEB SECURITY.** Server re-validates every action against
  `legal_actions`. The **wait queue, per-IP rate limit, and Cloudflare Turnstile
  must exist before exposing the server publicly.** Secrets live in env, never in
  code.
- **G8 — NO REGRESSION.** Adding game *N* must not modify `framework/ai/web`
  core. If it forces a core change, **STOP and reconsider the interface with the
  human.** All existing games' tests must still pass.
- **G9 — CHECKPOINT.** `git commit` at every green state. Don't accumulate
  multiple phases in one uncommitted blob.
- **G10 — HYGIENE CHECKS (mechanical).** `ruff` (lint + unused imports/vars),
  `vulture` (dead code), `deptry` (unused deps), and the **seam check**
  (`import-linter` enforcing G2) run via pre-commit + CI. A phase isn't "done"
  until they pass with **no new ignores/suppressions**. These exist because you
  can't see the whole repo — let the tools see it for you.

## Code hygiene (keep the codebase small)

> AI agents tend to *add* code and rarely delete or consolidate, because each
> session sees only a slice of the repo and additive changes feel safer. Counter
> it with the rules below — and lean on **G10**, which mechanically enforces what
> you can't eyeball across the codebase.

- **H1 — Survey before adding.** Before writing new logic, grep for code that
  already does it; extend/refactor that rather than duplicating. Reuse > new.
- **H2 — Subtractive bias.** Prefer deleting/merging to adding. Leave every file
  you touch at least as clean as you found it (within your current area).
- **H3 — No cruft.** No dead code, commented-out blocks, unused params/deps, or
  speculative abstractions (YAGNI). Delete it — git keeps the history.
- **H4 — Refactor ≠ feature.** Two commits: a behavior-preserving refactor (tests
  green before *and* after), then the feature. Never mix; keep diffs reviewable.
- **H5 — Log debt, don't detour.** Spot a bigger or out-of-scope refactor? Append
  it to `docs/TECH_DEBT.md` (don't silently leave it; don't balloon scope). Drain
  that list in dedicated refactor passes — before a release, or when a file
  crosses a size/complexity budget (e.g. > ~400 lines).

## STOP and ask the human when:

- a rule is ambiguous or you can't verify it from a source;
- adding a game would require changing the `Game`/`State` interface;
- a security / deploy / networking step (exposing the server, DNS, tunnels,
  secrets, Cloudflare config);
- anything irreversible (deleting files/data, `git push --force`);
- tests won't pass and you're tempted to delete or skip them.

## Per-game onboarding recipe (repeat for every new game)

1. Write `meeple/games/<g>/RULES.md` from `docs/RULES_TEMPLATE.md`; cite sources; get
   the human's sign-off. **(Gate G1 — blocking.)**
2. Fill in `GameSpec`: `num_players`, `perfect_information`, `has_chance`,
   `zero_sum`, `num_distinct_actions`, action labels.
3. Implement the engine + `State`/`Game` adapter behind `framework/`.
4. Write and pass tests. **(Gate G3.)**
5. Register the game in the registry (`meeple/web/registry.py` / `meeple/games/__init__.py`).
6. Reuse existing AI (pick via the matrix), the eval harness, and the web
   backend; add only a per-game renderer/action-codec. **No core changes (G8).**

## Solver-compatibility matrix

| Solver | Requires | Use for |
|---|---|---|
| **Heuristic** | nothing | every game — baseline & fallback |
| **MCTS (UCT)** | perfect info; any #players (max-n) | Quarto, Patchwork, Splendor (determinized) |
| **ISMCTS / PIMC** | imperfect info; any #players | Kahuna, Splendor |
| **Tabular CFR** | 2p **zero-sum**, tiny tree | Kuhn, Leduc — **validation only** |
| **Deep CFR** | 2p **zero-sum**, imperfect info, large | Kahuna |

Per-game properties (drives the choice — confirm each in that game's RULES.md):
- **Kahuna** — 2p, imperfect-info (hidden hands + deck), has chance, zero-sum → ISMCTS, later Deep CFR.
- **Quarto** — 2p, **perfect-info**, no chance, zero-sum → MCTS (small enough for near-exhaustive).
- **Patchwork** — 2p, **perfect-info**, ~no chance, zero-sum → MCTS.
- **Splendor** — 2–4p, **not 2p-zero-sum**, chance + hidden deck → MCTS/ISMCTS. **CFR does not apply.**

## Doc map

- **CLAUDE.md** (this file) — *how* to work: principles, gates, recipe.
- **PLAN.md** — *what* to build and in what order, + Definition of Done.
- **meeple/games/<g>/RULES.md** — the **authoritative** rules for a game (verified).
- **docs/RULES_TEMPLATE.md** — template every new game's RULES.md is copied from.
- **docs/TECH_DEBT.md** — refactor/debt backlog (externalized cross-session memory; H5).

If these documents ever conflict, the precedence is: a game's RULES.md (for that
game's rules) > CLAUDE.md (for process) > PLAN.md (for scope/ordering).
