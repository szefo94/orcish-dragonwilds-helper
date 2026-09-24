# Development instructions

This file is the authoritative entry point for coding agents and LLMs working in this repository.

## Source-of-truth order

When sources disagree, use this order unless the task explicitly says otherwise:

1. **Current code** in `src/orcpresser/` — what is implemented.
2. **Current tests** in `tests/` — executable behavioral contracts and regressions.
3. **This file (`AGENTS.md`)** — repository-wide engineering constraints.
4. **`roadmap.md`** — intended future direction and explicitly planned work.
5. **Feature docs** such as `docs/FISHING.md` — behavior rationale, state semantics, calibration rules, and known limitations.
6. **`README.md`** — public/user-facing setup and capability description.
7. **Research docs** (`*_RESEARCH.md`, `SCOUT_CANDIDATES.md`, `INTERNAL_TELEMETRY.md`) — hypotheses, experiments, evidence, and validation notes; not implementation contracts.
8. **`docs/CHANGELOG.md` and historical framework notes** — history and rationale.

If documentation conflicts with current code/tests, treat code/tests as current behavior and either update the stale documentation in the same focused change or call out the mismatch. Do not silently change working behavior merely to match an older document.

Read `docs/README.md` for the documentation map and status labels. Read `README.md` and the relevant feature doc before changing behavior; for Fishing, read `docs/FISHING.md`.

## Invariants

Keep internal `src/orcpresser` and `data/` paths compatible with existing installations. Do not overwrite user fishing notes.

All input must pass through the existing WinIO output guard. Preview must not emit input. Focus loss, stop, stale capture and watchdog must release held keys. Workers capture only; the main thread owns decisions and input.

Use pure logic tests for state changes and synthetic images for perception. Run `python -m unittest discover -s tests -t . -v`. Do not claim Windows or live-game testing from Linux. Never add user data, recordings, models or credentials to the repository.

## Change discipline

One feature per branch/PR. Avoid unrelated formatting changes in `app.py`. Document experimental behavior and unverified game cues.

Research notes are evidence, not authority. Do not promote an experimental cue, memory candidate, telemetry path, detector, or inferred game state into live control merely because a research document describes it; require the validation gates documented for that subsystem and preserve a safe fallback.
