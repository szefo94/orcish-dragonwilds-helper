# Game signals: memory, bridges and process hooks next to vision

> **Status: architecture reference (active).** Describes the implemented signal-source layer and the contract every future game-internal source must follow. Promotion rules live in [SCOUT_CANDIDATES.md](SCOUT_CANDIDATES.md); the hands-on data workflow in [RESEARCH_DATA_GUIDE.md](RESEARCH_DATA_GUIDE.md).

Vision (BAR / STOP / PULL / REEL / RESULT) is what the controllers trust. Everything else the helper can learn about the game is a **signal**: a named value with a role, a source and a timestamp. `src/orcpresser/game_signals.py` gives all of them one shape so new sources can be added without touching the controllers, and so the analyzer can compare any of them with the controller's own view.

```text
                      vision (capture + OCR)             game signals (game_signals.SignalHub)
                      ───────────────────────            ─────────────────────────────────────
  Fishing controller  observes Observation ──┐           MemoryCandidateSource   read-only RPM
  (fishing.py)                               │           hub.ingest_bridge()     Cheat Engine / UE4SS JSONL
        decisions ─────────────────────────► │           CallbackHookSource      Frida / mods / custom DLL (future)
                                             ▼                    │
                                 fishing_decision event  ◄── hub.snapshot()  (details.signals, shadow only)
                                             │
                                 scout_analysis.py: shadow agreement, candidate ↔ landmark correlation
```

## The shape

```python
SignalSample(source, domain, role, name, value, mono, ok=True, error=None, details={})
```

- `source`: `memory`, `cheat_engine`, `ue4ss`, `frida`, or any producer name from a bridge line.
- `domain` / `role`: the semantic-candidate vocabulary (`CANDIDATE_ROLES`): `fishing/phase`, `fishing/reel_allowed`, `auto_picker/can_interact`, … `infer_role(name, domain)` derives the role from a free-text name (`"fishing phase"` → `phase`), which is what the Cheat Engine import and the bridge use.
- `mono`: `time.monotonic()` on the Scout timeline. Samples carry the time they were read, not the time the game changed.

## Sources

| Kind | Class | How values arrive | Invasive? |
|---|---|---|---|
| memory | `MemoryCandidateSource` | Scout thread reads each semantic candidate (plain address or pointer chain) through `ReadOnlyMemory` every sampling tick | No (ReadProcessMemory only) |
| bridge | `SignalHub.ingest_bridge()` | `JsonlBridgeProvider` tails a JSONL file written by Cheat Engine (`orcish_scout_ce.lua`), UE4SS or another producer; `property_change` / `state_change` / `function_call` / `event` lines become samples | No for Orcish (the producer may be) |
| hook | `CallbackHookSource` | A hook running inside the game process (Frida `Interceptor`, a UE4SS Lua `RegisterHook`, a custom DLL) calls `push(label, value, …)` from its own thread; the Scout thread drains it in `poll()` | **Yes**: opt-in only |

`SignalHub.poll(now)` runs every source on the Scout sampling thread, records memory rows exactly as before (`memory.jsonl` is unchanged), and keeps the latest sample per `(domain, role, name)`. `hub.snapshot(now)` returns the fresh successful ones for the active domain plus `general`.

### What the Fishing panel does with it

Nothing for control. After every controller decision, `fishing_ui.py` asks the sidecar for `snapshot()` and stores it as `details.signals` on the `fishing_decision` event. That is the raw material for the **shadow agreement** section of the analyzer report: for each signal, how often each value was seen in each controller state, with a purity score. A signal worth promoting has purity near 1.0 over many sessions *and* a candidate ↔ landmark correlation with a stable negative median Δ (it leads vision).

## Adding a new source

1. Subclass `SignalSource` (or use `CallbackHookSource` for anything callback-driven). Implement `start()`, `poll(now) -> list[SignalSample]`, `close()`, `status()`.
2. Register it on the session's hub in `ScoutLabSession.__init__` (or through `InternalTelemetryHub` if it is an external producer that writes JSONL: then no code is needed, only a bridge path).
3. Add a pure-logic test that drives `poll()` with a fake clock and asserts the samples and events; see `tests/test_game_signals.py`.
4. Keep the invariants: the source only *observes*; it never writes game memory, never sends input, and never blocks the main thread. Hooks set `invasive = True` and stay behind an explicit opt-in checkbox.
5. Document what the source needs (tool, game build, admin rights) and how it fails (missing module, null pointer, detached process) so the analyzer can tell "object does not exist right now" from "source is broken".

## In-process hooks: the intended path

The project has two hook paths already and both stay parked until a game build supports them (see [INTERNAL_TELEMETRY.md](INTERNAL_TELEMETRY.md)): Frida function-entry hooks (`internal_telemetry.FridaFunctionProvider`) and the UE4SS Lua mod (`tools/ue4ss/OrcishScout`). When either becomes usable, the adapter is small: Frida's `_on_message` or the UE4SS JSONL lines call `CallbackHookSource.push(label, value, role=…)`; nothing else changes. The same holds for a custom read-only DLL or an Unreal Remote Control endpoint.

Hooks must be **observational**: `onEnter` only, no argument or return rewriting, no code patches, no writes. They are research instruments for discovering *where* fishing state lives; the production path is a validated read-only memory candidate (pointer chain), because it needs no injected code at runtime.

## From signal to control: the gates

1. Record: the signal rides along in `fishing_decision.details.signals` and in `memory.jsonl` / `process.jsonl`.
2. Agreement report: shadow agreement purity and candidate ↔ landmark correlation over 5+ sessions, 3+ launches, day and night, two spots (checklist in [RESEARCH_DATA_GUIDE.md](RESEARCH_DATA_GUIDE.md#validation-checklist-before-a-signal-is-used-by-the-bot)).
3. Shadow mode (not implemented yet): the controller computes what it *would* do with the signal and logs disagreements, still acting on vision.
4. Promotion: a focused change adds the signal as a `FishingConfig` option with vision fallback and explicit invalidation (module missing, chain broken, build changed), with state-machine tests for every fallback path.

Steps 3 and 4 are deliberately not in the code yet. Nothing in this layer lets a controller read a signal; that is a design choice, not an omission.
