# Scout research: visual + process telemetry for Auto Picker and Fishing

Status: Phase A parallel logger implemented; process-memory/reflection backends remain research/design only.

## Goal

Add a **Scout** subsystem that observes RuneScape: Dragonwilds through more than one independent data source and records those observations on a common timeline.

The first objective is diagnostic: collect parallel evidence from the current screen/OCR detectors and from safe process-level telemetry, then compare the streams offline. Only after a signal proves stable across sessions should it be eligible to influence Auto Picker or Fishing.

The long-term target is a fused controller that can answer questions such as:

- Is an interaction prompt really active?
- Is fishing waiting for a bite, fighting, reeling, or showing a result?
- Did the visual detector miss a state transition that process telemetry saw?
- Did process telemetry change because of unrelated Unreal activity rather than gameplay state?

This should remain **fail-safe**: stale, contradictory or low-confidence data must release/withhold input instead of guessing.

## Current visual sources

The project already has useful visual evidence that should remain the baseline:

### Auto Picker

- selected capture region;
- OCR text/key recognition;
- visual availability/keycap checks;
- action allow-list and preview mode;
- focus and stale-result safety.

### Fishing

- BAR colour/burn-down detector;
- STOP Fishing region;
- PULL L and PULL R regions;
- REEL OCR;
- RESULT OCR;
- optional SPOT detector;
- current controller state and held input.

The earlier design note, `AHK-OCR-AutoPresser-Idea.md`, already recommends timestamped observations, stable recognition across consecutive captures, a persistent worker, and rejecting stale recognition. Scout should extend that architecture rather than replace it.

## What "process Scout" should mean

There are several very different techniques hiding under the phrase "read Unreal data". They should be evaluated in this order.

### Tier 0 — ordinary OS process telemetry

Low risk and easy to ship:

- PID and executable path;
- process start time;
- foreground/background state;
- window/client rectangle;
- loaded module names and base addresses;
- CPU, RAM and thread count;
- process lifetime/restart detection.

This will not reveal fishing or prompt state, but it gives every log a stable process/session identity and lets us correlate crashes, restarts and module changes.

### Tier 1 — Unreal's own supported telemetry, if the shipped build exposes it

Unreal provides **Unreal Insights / Trace**, a structured tracing system. Epic documents a trace server, live trace sessions and high-rate event collection. If Dragonwilds can be launched with useful trace channels enabled, this would be preferable to blind memory scanning because the data is structured and timestamped.

Research checks:

1. Test offline/single-player launch with conservative trace flags only.
2. Check whether a live session appears in Unreal Insights.
3. Inventory available channels.
4. Determine whether any channel contains gameplay/UI state useful to Auto Picker or Fishing.
5. Never assume developer-only or custom game events exist in a retail build.

Important limitation: Unreal Insights is primarily a developer/profiling facility. Standard traces may expose performance, frame, task, memory or UI activity without exposing semantic values such as "FishingState = Reel".

### Tier 2 — Unreal Remote Control, only if already exposed by the game/mod environment

Epic's Remote Control system can expose Unreal properties/functions over HTTP/WebSocket, but it is a project/plugin feature and is disabled by default in packaged projects. It is therefore **not an out-of-the-box external API for arbitrary retail Unreal games**.

It becomes attractive only if:

- Dragonwilds ships the relevant plugin/configuration; or
- an allowed Dragonwilds mod can expose a small read-only telemetry endpoint.

A purpose-built mod endpoint is much cleaner than address scanning. A possible local schema:

```json
{
  "session": "uuid",
  "ts_monotonic": 12345.678,
  "interaction": {
    "prompt": "Collect",
    "key": "E",
    "hold": false,
    "available": true
  },
  "fishing": {
    "phase": "WAIT_BITE",
    "bar": 0.82,
    "reel": false,
    "result": null
  }
}
```

The helper would consume this as another Scout source and never require it for basic operation.

### Tier 3 — community Unreal reflection/mod tooling

Tools such as **UE4SS** can discover `UObject` instances and reflected properties/functions in compatible Unreal games. This is technically much richer than raw memory scanning because Unreal reflection gives objects names/classes and typed properties.

Potential value:

- enumerate UI/widget/controller objects;
- discover state-like properties;
- inspect values while known visual phases occur;
- prototype a Dragonwilds-specific read-only mod/telemetry bridge.

Risks:

- compatibility depends on the game's exact Unreal version/build;
- it is injected/runtime mod tooling rather than an external observer;
- updates can break signatures/layouts;
- multiplayer/shared-world use may violate Dragonwilds rules if it provides an unfair advantage;
- it increases support and account-risk surface substantially.

Treat UE4SS as an **experimental offline research path**, not a mandatory runtime dependency.

### Tier 4 — Cheat Engine / external memory research

Cheat Engine is primarily a process-memory scanner/debugger. Its documented workflow is to attach to a target process, search memory for exact or unknown values, then narrow the candidate set using changed/unchanged/increased/decreased scans. Dynamic addresses can later be followed through pointers.

For this project, Cheat Engine is best treated as a **manual discovery instrument**, not as the production Scout.

Useful discovery experiments:

#### Fishing

Record visual timestamps for:

1. no cast;
2. cast landed / STOP Fishing appears;
3. fish bites / STOP disappears / PULL L-R appear;
4. bar changes red/blue;
5. REEL appears;
6. REEL disappears;
7. catch/failure result.

While doing that, use unknown-value/change scans to look for candidates that:

- switch exactly once at a phase boundary;
- remain stable for the entire phase;
- return predictably on the next cast;
- survive a new fishing session;
- preferably survive a process restart through a stable pointer chain.

Candidate types to test include byte/bool, 4-byte enum/int and float values.

#### Auto Picker

Choose one prompt and repeatedly create controlled transitions:

- prompt absent -> present;
- available -> unavailable/dimmed;
- Collect -> other action;
- tap prompt -> hold prompt;
- target object A -> target object B.

Search for values that correlate only with the selected interaction state.

### Do not promote a memory candidate too early

A candidate address is not useful just because it changed at the right moment once. Require:

- repeatability across at least 20 transitions;
- at least 3 game launches;
- more than one world/scene;
- no false correlation during unrelated combat/UI activity;
- documented module/pointer resolution rather than a one-session absolute address;
- read-only access;
- automatic invalidation when build/version changes.

## Legal and operational constraints

Jagex's Dragonwilds-specific EULA expressly supports community modifications subject to its Dragonwilds Modding Guidelines. Those guidelines allow single-player cheats but prohibit cheats that give an unfair advantage in multiplayer/shared environments. Jagex's broader terms also restrict automation, reverse engineering and unauthorized third-party software, while the Dragonwilds schedule provides a game-specific mod framework.

Practical project policy:

- develop/test process Scout against **offline or private/single-player environments**;
- do not design anti-cheat bypasses;
- do not hide the helper from monitoring software;
- do not patch/write game memory;
- do not intercept or alter network traffic;
- do not make process-memory access mandatory;
- clearly mark experimental process/reflection backends;
- keep the visual-only helper usable independently.

This document is an engineering plan, not a statement that a particular third-party tool is permitted by Jagex.

## Parallel logging architecture

All Scouts should emit one normalized envelope so visual and process evidence can be compared directly.

```json
{
  "session_id": "uuid",
  "seq": 10482,
  "mono": 12345.678901,
  "wall_utc": "2026-09-23T05:10:11.123Z",
  "source": "vision|process|unreal_trace|mod_bridge",
  "domain": "auto_picker|fishing|system",
  "signal": "reel",
  "value": true,
  "confidence": 0.97,
  "latency_ms": 47,
  "fresh_ms": 12,
  "details": {}
}
```

Use monotonic time for correlation. Wall time is only for human navigation.

### Suggested session files

```text
data/scout_sessions/20260923-071500/
    manifest.json
    vision.jsonl
    process.jsonl
    controller.jsonl
    screenshots/
    summary.json
```

`manifest.json` should include:

- helper git commit/version;
- game executable/module version information;
- Windows version;
- game resolution/UI scale if known;
- enabled Scout backends;
- hashes/IDs of calibration regions, not screenshots unless recording is enabled;
- whether the session was Preview or Live;
- whether gameplay was offline/private/shared. The current project scope assumes single-player/private testing for Scout research.

## Signals to log

### Auto Picker

Vision:

- OCR prompt text;
- recognized key;
- hold/tap classification;
- visual available/dimmed score;
- selected action;
- capture/OCR latency.

Process/Unreal candidate stream:

- candidate ID;
- resolved module + offset or reflected object/property name;
- raw value;
- normalized value;
- resolution success/failure;
- read latency.

Controller:

- action accepted/rejected;
- reason;
- intended input;
- physical held state;
- focus/stale/watchdog events.

### Fishing

Vision:

- STOP yes/no/confidence;
- PULL L yes/no;
- PULL R yes/no;
- BAR state/red ratio/blue ratio;
- REEL OCR confirmation;
- RESULT classification;
- SPOT candidate/confidence;
- controller state;
- intended/physical A, D, LMB.

Process/Unreal candidate stream:

- candidate phase enum/bool;
- bobber/fishing interaction active candidate;
- candidate UI widget visibility;
- candidate bar/stamina/progress float;
- candidate result/catch state;
- object/property identity and resolution method.

## Temporal alignment: OCR is reactive and delayed

Visual/OCR evidence is not instantaneous. A game-state transition happens first, then the frame is rendered, captured, queued for OCR, processed, and only afterwards reaches the controller. Scout correlation must therefore use **causal time windows**, not exact timestamp equality.

Each visual event should distinguish at least:

- `frame_mono` — when the source frame was captured;
- `queued_mono` — when it entered the OCR/detector queue;
- `detected_mono` — when recognition completed;
- `consumed_mono` — when the controller received the result;
- `latency_ms = detected_mono - frame_mono`.

For OCR-backed signals such as REEL/RESULT/PULL prompts, the analyzer should search a configurable window around the visual event. Initial research defaults:

- process/unreal candidate may lead OCR by up to **500 ms**;
- process/unreal candidate may lag OCR by up to **150 ms**;
- use measured per-signal latency distributions to replace these defaults after enough sessions.

Do not interpret a process event 100–300 ms before OCR as disagreement. It may be the same underlying transition observed earlier.

The analyzer should compute cross-correlation and transition lead/lag for every candidate, then report median, p95 and jitter. A candidate that consistently leads REEL OCR by 80 ms is potentially valuable even if timestamps never match exactly.

For controller safety, fusion should operate on freshness windows:

```text
vision_reel_fresh  = now - reel_frame_mono <= visual_ttl
process_reel_fresh = now - process_event_mono <= process_ttl
```

The source timestamp should be the time the evidence existed, not merely the time a slower worker returned it.

## Scout-assisted calibration and tighter overlays

Process/Unreal data may also help reduce manual overlay calibration. There are two different possibilities.

### Direct widget geometry

If an Unreal-native/reflection/mod bridge exposes UMG/Slate widget information, Scout may be able to obtain:

- viewport size and DPI/UI scale;
- widget visibility;
- absolute or viewport-local widget geometry;
- render transform / layout transform;
- widget class/name;
- bounds for prompt containers, fishing HUD elements or interaction rows.

This would be the strongest calibration source. Instead of asking the user to draw a large REEL/PULL/STOP box, the helper could map the widget geometry into game-client pixels and create or tighten the region automatically.

This must be treated as **optional metadata** because a retail build may not expose useful widget objects or geometry externally.

### Process-triggered visual tightening

Even without pixel coordinates, a process signal can make the visual search much easier.

Example:

1. process Scout reports `fishing_phase = WAIT_BITE`;
2. visual Scout scans a broader HUD search area for STOP only;
3. once STOP is found, shrink and persist a tight ROI around it;
4. when process phase changes to FIGHT, scan nearby for PULL L/R;
5. when process candidate says REEL is possible, search only the expected prompt band;
6. track the detected box frame-to-frame with a small margin.

This changes calibration from **user draws exact box** to **user supplies rough search area, Scout tightens it**.

### Visual-only auto-tightening

The same machinery should work even without process access:

- start from the saved user ROI;
- find the actual text/glyph bounding box;
- expand by a small configurable padding;
- keep an exponentially smoothed rectangle;
- refuse large jumps unless confirmed across several frames;
- reset to the user's original ROI after resolution/UI-scale changes.

Suggested stored structure:

```json
{
  "signal": "reel",
  "user_region": [0.42, 0.61, 0.18, 0.08],
  "tight_region": [0.47, 0.625, 0.09, 0.035],
  "source": "vision",
  "confidence": 0.94,
  "samples": 186,
  "ui_scale_key": "2560x1440@100"
}
```

### Calibration-health metrics

For each region, log:

- percentage of frames with a valid detection;
- bounding-box jitter in pixels;
- average margin between detection and ROI edge;
- clipping incidents;
- resolution/UI-scale changes;
- process-vs-visual phase agreement.

The UI can then show:

`REEL calibration: GOOD · 96% detected · 8 px margin`

or:

`PULL R calibration: CLIPPING RIGHT EDGE · expand by ~12 px`

This should eventually make overlay calibration evidence-driven instead of trial-and-error.

## Offline correlation and analysis

The first "super bot" work should be an **analyzer, not an actor**.

For each candidate process signal calculate:

- precision/recall against visually labelled states;
- transition latency relative to vision;
- stability during the phase;
- false positives outside the phase;
- missing reads/resolution failures;
- survival across restarts/builds.

Example target table:

| Signal | Visual source | Process candidate | Agreement | Median lead/lag | Stable across restart? |
|---|---|---|---:|---:|---|
| STOP | visual glyph | candidate_17 | 99.2% | -28 ms | yes |
| FIGHT | PULL L/R + BAR | candidate_31 enum=2 | 98.8% | -61 ms | yes |
| REEL | OCR | widget candidate_8 | 100% | -92 ms | no |
| Collect available | OCR + border | candidate_52 | 95.1% | -35 ms | yes |

Do not use a process signal for control until it meets a threshold agreed from real recordings.

## Fusion model

After reliable candidates exist, create a **Scout Fusion** layer.

Example policy:

```text
CONFIRMED_REEL =
    process_reel fresh and trusted
    OR
    (vision_reel confirmed twice)

CONFIRMED_FIGHT =
    trusted process_phase == FIGHT
    OR
    (pull_prompt confirmed and bar valid)

AUTO_PICK_ACTION =
    process interaction candidate agrees with
    visual action/key/availability
```

A process signal may provide faster phase detection while vision remains an independent sanity check. For dangerous/irreversible actions, require agreement instead of OR logic.

Every fused decision should log which source(s) caused it.

## Proposed implementation modules

```text
src/orcpresser/scout/
    events.py          # normalized ScoutEvent schema
    recorder.py        # JSONL session writer
    process_info.py    # Tier 0 process/module telemetry
    memory_watch.py    # optional read-only address/pointer watches
    unreal_trace.py    # experimental Unreal Insights importer/probe
    mod_bridge.py      # optional localhost telemetry consumer
    fusion.py          # no input; produces fused observations
    analysis.py        # correlation metrics/report generation
```

Existing Auto Picker and Fishing modules publish their visual observations into `recorder.py`. They should not depend on any experimental backend.

## Development phases

### Phase A — parallel logger

Implemented foundation:

- common Scout event envelope and bounded JSONL session recorder;
- per-run session manifest and summary;
- visual Auto Picker observations with queue/capture/detection/consume timing;
- visual Fishing observations with frame/OCR timing and STOP/PULL/BAR/text evidence;
- controller decision/state logging for both domains;
- Tier 0 PID/process/module snapshot at session start;
- local session storage under `data/scout_sessions/` with a 20 MiB per-session event cap.

Still pending in Phase A:

- offline correlation/report generator;
- optional screenshot sampling tied to event IDs;
- calibration-health statistics derived from recorded sessions.

No game-memory reads are required for the implemented Phase A logger.

### Phase B — manual discovery support

Add a UI panel to register named experimental candidates discovered with Cheat Engine:

- name;
- module;
- offset/pointer description;
- type;
- expected semantic state.

The helper only reads and records them. Invalid/unresolved candidates show clearly as unavailable.

### Phase C — evaluate Unreal-native paths

In this order:

1. Unreal Insights / Trace probe.
2. Dragonwilds-compatible read-only mod telemetry bridge.
3. UE4SS/reflection research in offline/private testing.
4. Raw external memory candidate reader only for stable, well-understood signals.

### Phase D — Scout Fusion

Promote only candidates that pass recorded validation. Run fusion in Preview first. Compare fused actions against what the existing controller would have done.

### Phase E — optional control

Enable fused state as a controller input only after:

- false-positive rate is acceptable;
- stale handling is proven;
- game update invalidation is implemented;
- F8/focus/watchdog release paths remain authoritative.

## Recommendation from this research

1. **Build the parallel logging layer first.** It improves the project immediately and gives us objective data for both Auto Picker and Fishing.
2. **Use Cheat Engine only as a discovery tool initially.** It is excellent for narrowing changing values but poor as a runtime dependency.
3. **Probe Unreal Insights because it is an official structured telemetry system**, but expect mostly profiling data unless Dragonwilds exposes useful gameplay channels.
4. **Investigate a Dragonwilds mod telemetry bridge before committing to raw offsets.** If the game's supported mod ecosystem can expose read-only semantic state, that will be more maintainable than pointer chains.
5. **Keep screen recognition as an independent fallback/check.** A process-based Scout should improve latency and confidence, not create a single fragile point of failure.

## Sources

- Epic Games, Unreal Insights: https://dev.epicgames.com/documentation/unreal-engine/unreal-insights-in-unreal-engine
- Epic Games, Trace developer guide: https://dev.epicgames.com/documentation/unreal-engine/developer-guide-to-tracing-in-unreal-engine
- Epic Games, Remote Control: https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control
- UE4SS UObject documentation: https://docs.ue4ss.com/lua-api/classes/uobject.html
- Cheat Engine memory scanning documentation: https://wiki.cheatengine.org/index.php?title=Cheat_Engine:Memory_Scanning
- Jagex Dragonwilds EULA schedule: https://legal.jagex.com/docs/terms/eula
- Jagex Dragonwilds Community Modding Guidelines: https://legal.jagex.com/docs/policies/runescape-dragonwilds-community-modding-guidelines
- Jagex Terms & Conditions: https://legal.jagex.com/docs/terms/terms-and-conditions
- Earlier project note: `AHK-OCR-AutoPresser-Idea.md`
