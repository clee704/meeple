# Tech debt & refactor backlog

> **Externalized big-picture memory.** Agents don't carry context across sessions
> and can't see the whole repo at once, so refactor opportunities live here — not
> in anyone's head. Per **CLAUDE.md H5**: when you notice something out of the
> current phase's scope, *log it here* instead of derailing or silently leaving
> it. Dedicated refactor passes (CLAUDE.md G10 / H4) drain this list.
>
> Format per item: **what** — `path/area` — **why it matters** — blast radius S/M/L.
> When resolved, move the item to "Done" with the commit hash.

## Open

- [ ] _(example — delete once real items exist)_ Duplicate legal-action filtering
  across engines — `meeple/games/*/engine.py` — extract a shared helper to cut
  drift — blast radius: M

## Done

- _(move resolved items here, e.g. `abc1234 — consolidated X`)_
