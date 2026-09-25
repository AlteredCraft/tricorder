"""A tiny planning tree following the framework, written to a temp dir."""

from __future__ import annotations

import tempfile
from pathlib import Path

FILES = {
    "planning/milestones.md": """# Milestones

## M-0001: Ship the thing

**Status:** In progress

**Scope:** Everything small.

**Done when:** G-0001 is Met.

**Active spec:** [G-0001.01](plans/G-0001.01-first.md#open)

| Goal | Status |
| --- | --- |
| [G-0001 First goal](plans/G-0001-first-goal.md) | In progress |

## Later

- Something else.
""",
    "planning/plans/G-0001-first-goal.md": """# G-0001. First goal

**Milestone:** [M-0001](../milestones.md#m-0001-ship-the-thing)

**Status:** In progress

**Outcome:** People can do the thing.

**Specs:**

| Spec | Status |
| --- | --- |
| [.01 First](G-0001.01-first.md) | In progress |
| [.02 Second](G-0001.02-second.md) | Partial |
""",
    "planning/plans/G-0001.01-first.md": """# G-0001.01. First

Status: In progress
Goal: [G-0001](G-0001-first-goal.md) — the thing works.
ADRs: [0001](../adrs/ADR-0001-choice.md)
Revision: 2026-01-02: tightened check 2.

## Hypothesis

The thing works under **load**.

**Refuted if:** it doesn't.

## Checks

1. [pass] Host tests pass.
2. [open] Three runs
   at speed.
3. [fail] Rated 4/5.

## Observed

- 2026-01-01 — [C1 pass] Tests green. Evidence: `tests` · `abc1234`. → ADR-0001
- 2026-01-03 — [C3 fail] Rated 3. Evidence: `run-1` · #12.
- ~~2026-01-02 — Wrong numbers. Evidence: `run-0` · `def5678`.~~ (superseded 2026-01-03)
- 2026-01-04 — Uncited note.

## Open

1. Three runs (C2).
2. Cold starts (C4; needs the user).
""",
    "planning/plans/G-0001.02-second.md": """# G-0001.02. Second

Status: Confirmed
Goal: [G-0001](G-0001-first-goal.md)
ADRs: None

## Checks

1. [pass] Fine.
2. [open] Not yet.

## Observed

## Open

1. Leftover.
""",
    "planning/plans/G-0009-orphan.md": """# G-0009. Orphan goal

**Milestone:** [M-0001](../milestones.md)

**Status:** Not started
""",
    "planning/adrs/ADR-0001-choice.md": """# ADR-0001. Use the choice

Status: Active · Decided: 2026-01-01 · Evidence: [G-0001.01](../plans/G-0001.01-first.md#observed)

## Decision

We chose. See [missing](nope.md).
""",
    "planning/adrs/ADR-template.md": "# ADR-NNNN. Title\n\nStatus: Active\n",
    "planning/protocol.md": "# Protocol\n\n```sh\n## not a heading\n```\n",
    "README.md": "# Repo\n",
}


def make_tree() -> tuple[tempfile.TemporaryDirectory, Path]:
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    (base / ".git").mkdir()
    for rel, text in FILES.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp, base
