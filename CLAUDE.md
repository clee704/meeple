# CLAUDE.md — Operating contract for MeepleMind

> **Read this fully at the start of every session, before doing anything.**
> Then read `PLAN.md` — project identity, goals, and the roadmap live there,
> not here. If you are working on a specific game, also read
> `games/<game>/RULES.md`.
>
> This file exists so that a *smaller/cheaper model* can continue the project
> safely. It is intentionally prescriptive. When in doubt, follow the gates
> below literally and escalate to the human rather than improvising.
>
> **No rule here is beyond question.** These are defaults that make sense most
> of the time, not dogma. If one stops making sense for what's actually in
> front of you, say so explicitly and propose an alternative — don't silently
> comply with something you think is wrong, and don't silently route around it
> either.

Project **MeepleMind**, Python package **`meeple`**, CLI **`meeple`**. See
`PLAN.md` for what the project is, its goals, and the roadmap — this file is
process only, so that isn't repeated here.

## Progress ledger — nothing important lives only in a chat

This project spans many sessions and models. A session can end at any point,
so progress must be durable and resumable from the repo alone:

- **`PLAN.md`** is the strategic doc (goals, architecture, roadmap). It
  changes rarely.
- **Each phase's granular progress** — checklist, decisions, open blockers —
  is tracked in a GitHub issue labeled `phase`, linked from `PLAN.md`'s phase
  table. Update the issue (check off items, leave a comment on any nontrivial
  decision) as you go, so a fresh session can resume from `PLAN.md` + that
  issue alone, without reading this conversation.
- **A game's rules and their verification status** live in
  `games/<g>/RULES.md` — already durable via git.
- **Tech debt** is tracked as GitHub issues labeled `tech-debt`, not a
  markdown backlog.
- This repo is public — never put secrets or anything you wouldn't want
  public into an issue, commit message, or code comment.

## Guiding principles

- **P1 — Always reach a game through the seam.** `ai`/`eval`/`web` import
  *only* `framework/`; game code lives under `games/<g>/` and is reached only
  through the interface. What's non-negotiable is *having and using* this
  boundary — the exact shape of the `Game`/`State` interface is our current
  best guess, not sacred, and should improve as more games reveal what it's
  missing. If a game keeps forcing awkward workarounds, that's a signal to
  deliberately revise the interface (propose the change and why — see G8) —
  not to quietly route around it.
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
  in that phase's GitHub issue).
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

## Engineering guardrails (keep the codebase small and honest)

> AI agents tend to *add* code and rarely delete, consolidate, or reorganize,
> because each session sees only a slice of the repo and additive changes feel
> safer. Counter it with the rules below — and lean on **G10**, which
> mechanically enforces what you can't eyeball across the codebase.

### Code hygiene

- **H1 — Survey before adding.** Before writing new logic, grep for code that
  already does it; extend/refactor that rather than duplicating. Reuse > new.
- **H2 — Subtractive bias.** Prefer deleting/merging to adding. Leave every file
  you touch at least as clean as you found it (within your current area).
- **H3 — No cruft.** No dead code, commented-out blocks, unused params/deps, or
  speculative abstractions (YAGNI). Delete it — git keeps the history.
- **H4 — Refactor ≠ feature.** Two commits: a behavior-preserving refactor (tests
  green before *and* after), then the feature. Never mix; keep diffs reviewable.
- **H5 — Log debt, don't detour.** Spot a bigger or out-of-scope refactor? Open
  a GitHub issue labeled `tech-debt` (don't silently leave it; don't balloon
  scope). Drain that backlog in dedicated refactor passes — before a release,
  or when a file crosses a size/complexity budget (e.g. > ~400 lines).

### Test hygiene

- **T1 — A test must be able to fail.** Before trusting a test, imagine
  reverting the change it's meant to guard — would it actually go red? Don't
  assert on tautologies (a mock returning what you told it to return, a
  constant compared to itself, an untyped `assert result is not None`).
- **T2 — Cover reachable behavior, not a percentage.** Coverage is a floor,
  not the goal — padding it with trivial tests of getters or constants
  doesn't pin down behavior that matters. Every branch a caller can actually
  reach should have a test; branches that can't be reached (defensive code for
  states that can't happen) should usually be deleted (H3), not tested around.
- **T3 — No redundant tests.** If two tests would fail on the exact same bug,
  keep one. Parametrize genuinely distinct cases instead of copy-pasting
  near-identical test functions.

### File & module hygiene

- **F1 — One concern per file.** Don't bundle unrelated classes/functions into
  one file for convenience; a file's contents should share a single reason to
  change.
- **F2 — Size is a smell, not a limit.** The ~400-line budget in H5 is a
  prompt to split a file, not a rule to route around with tricks.
- **F3 — Reorganize freely.** Moving or renaming files/folders for a clearer
  structure is encouraged, not overhead avoided — do it as its own refactor
  commit (H4), updating imports and tests in that same commit.

## STOP and ask the human when:

- a rule is ambiguous or you can't verify it from a source;
- a rule (in this file or elsewhere) seems wrong for the situation you're in —
  say so and propose an alternative instead of silently overriding or
  silently complying;
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
5. Register the game — and its `GameView` if it's web-playable — in
   `meeple/games/__init__.py` (both go through `meeple/framework/registry.py`).
6. Reuse existing AI (pick via the matrix), the eval harness, and the web
   backend; add only a per-game `view.py` (the `GameView` SPI) and one React
   renderer component in `frontend/src/games/`. **No core changes (G8).**

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

- **CLAUDE.md** (this file) — *how* to work: principles, gates, engineering
  guardrails, recipe.
- **PLAN.md** — *what* to build, why, and the phase table (each phase links to
  a GitHub issue for granular tracking).
- **meeple/games/<g>/RULES.md** — the **authoritative** rules for a game (verified).
- **docs/RULES_TEMPLATE.md** — template every new game's RULES.md is copied from.
- **GitHub issues** — the durable progress ledger: `phase` label for
  per-phase checklists/decisions, `tech-debt` label for the refactor backlog.

If these documents ever conflict, the precedence is: a game's RULES.md (for that
game's rules) > CLAUDE.md (for process) > PLAN.md (for scope/ordering).
