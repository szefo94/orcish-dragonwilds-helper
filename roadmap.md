# Roadmap

The project should become easier to install, easier to calibrate, and increasingly self-configuring while keeping the real-time control loop local, deterministic, bounded, and recoverable.

This roadmap describes the state of `main`. Items under **Completed foundation** are implemented in the repository; later sections are planned or validation work.

## Completed foundation

### Core helper
- Repeat and Hold modes with persisted settings.
- Auto Presser with persistent capture region, action allowlist/exclusions, Preview/Live separation, learned recognition data, optional speed paths, and Stats benchmarking.
- Shared **GAME & CAPTURE** controls and a single **COMMAND CENTER** for game binding, requirements, and next-action guidance.
- One click-through **top-left stacked HUD rail** instead of separate four-corner runtime panels.
- Clean tab isolation: switching modes stops active workers/controllers, releases helper-owned inputs, and resets transient state without deleting persisted configuration.
- GitHub `orcish-dragonwilds-helper-main.zip` snapshots can be applied by `Update.cmd`, including same-version snapshots from newer commits.

### Fishing
- Explicit **Fishing Bot 101** and **Advanced · EXP** modes.
- Persistent BAR/REEL/STOP/PULL L/PULL R/RESULT/SPOT calibration.
- Manual recording and local Scout telemetry for detector/controller evidence.
- Transition-driven fallback control: hold A/D continuously, keep direction through blue, swap once on stable blue→red, and let REEL override immediately with LMB.
- Fast visual PULL-L/PULL-R direction evidence and fast REEL evidence, each requiring consistent samples before use.
- Bounded `BITE_PENDING` state after STOP disappears.
- Recurring-round flow with STOP clear/reappear handshake when STOP is calibrated, and BAR fallback when it is not.
- F7 / **NEW SPOT / REACQUIRE** for manual movement between spots.
- Manual cast bracket calibration (SHORT/MID/LONG + SHORT/LONG/HIT feedback).

### Scout / internal telemetry research
- Scout semantic read-only memory candidates for Fishing, Auto Picker, and general signals.
- Candidate transition recording and correlation against visual/controller landmarks.
- Optional external JSONL bridge for UE4SS or another local producer.
- Optional Frida native-function entry telemetry.
- Guided telemetry toolkit installer/status checks.
- WinGDK-aware Dragonwilds targeting.
- Experimental **Setup option 9** UE4SS recovery path with backup/rollback and post-launch status diagnostics.

## Priority 1 — validate one reliable WinGDK internal telemetry path

The immediate research gate is narrow:

```text
Dragonwilds (WinGDK)
-> UE4SS starts without PS-scan timeout
-> OrcishScout Lua reaches bridge_start / bridge_ready
-> data\ue4ss\orcish_scout_ue4ss.jsonl receives events
```

Do not expand controller dependence on game-internal signals until this path survives repeated launches and a Dragonwilds update. Visual control remains the fallback.

After the bridge is stable:
- discover real Fishing UFunction/property candidates;
- correlate them with STOP/BITE/PULL/REEL/result landmarks;
- validate candidates across multiple launches and areas;
- promote only signals with enough evidence and graceful invalidation.

## Priority 2 — automatic calibration and clearer first-run UX

- Scan likely HUD areas for BAR, REEL, STOP and PULL candidates; rank them and let the user confirm.
- Add a guided “what did I read?” flow for locally labeling detector examples.
- Detect UI scale/resolution/layout changes and request reacquisition when saved regions no longer fit.
- Build a calibration-health surface: region presence, confidence, last REEL/PULL evidence, capture latency, OCR freshness and stale-region warnings.
- Reduce duplicate setup text further so each feature page shows only feature-specific settings.

## Priority 3 — reduce installation prerequisites

1. Keep the one-command Windows bootstrap and isolated local `.venv` reliable.
2. Keep optional research/acceleration dependencies outside the normal runtime path.
3. Produce a self-contained Windows build so normal users do not need Python or pip.
4. Add signed/versioned release artifacts and stronger upgrade verification.
5. Test install/update/recovery on clean Windows 10/11 machines, including Steam-style and WinGDK packaging where supported.

## Priority 4 — Advanced Fishing

Advanced mode remains separate from Bot 101. Add automation only when recordings or internal telemetry provide repeatable evidence:

- reliable pool/ripple candidate detection and confidence scoring;
- automatic target selection among multiple visible pools;
- cast landing detection and automatic recalibration;
- controlled camera/player positioning toward a selected pool;
- controlled travel between spots after depletion;
- bounded repeated cast/fight/catch cycles;
- stamina/progress detection if a trustworthy signal is found;
- bait/inventory handling only after its state can be detected safely.

Movement or meaningful camera rotation must invalidate position-dependent cast calibration. Screen-fixed HUD regions may stay valid if their confidence remains healthy.

## Priority 5 — data-assisted improvement

Record only opt-in crops and telemetry needed to reproduce recognition errors. Keep analysis local by default. A reviewed/offline LLM workflow may help classify samples or summarize sessions, but live control must not depend on an online LLM.

## Engineering gates

Every new control feature must preserve:
- F8 and focus-loss input release;
- Preview-before-Live validation where applicable;
- bounded queues, timeouts and stale-data handling;
- no action from ambiguous detector evidence;
- deterministic local control logic;
- synthetic/state-machine tests for new transitions;
- graceful fallback when optional telemetry is missing or invalid;
- explicit opt-in for invasive instrumentation or movement automation.
