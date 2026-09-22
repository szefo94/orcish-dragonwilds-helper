# Roadmap

The project should become easier to install, easier to calibrate, and increasingly self-configuring while keeping the real-time control loop local and deterministic.

## Priority 1 — biggest wins, lowest risk

- **Persist every calibration.** Auto Presser capture region and Fishing BAR/PROMPT/RESULT/SPOT regions should survive restarts. Persist cast calibration separately and invalidate only the geometry-dependent part after player/camera movement.
- **Fishing Bot 101.** Make BAR (tension) and PROMPT (especially `Reel (Hold)`) the minimum supported setup. Keep player movement and positioning manual. RESULT is recommended for `No fish` / depleted messages; SPOT remains optional.
- **Guided setup.** The Fishing tab should say exactly what it needs next: bind game → select BAR → select PROMPT → Preview → Live. A failed/no-fish result should stop input and ask the player to move, then reacquire.
- **Remove experimental switches that contradict confirmed logic.** Prefer one safe behavior over checkboxes for obsolete alternatives.

## Priority 2 — automatic calibration

- Scan likely HUD areas for the red/blue tension bar and text prompt, rank candidates, and let the user confirm the best match.
- Add a guided “what did I read?” calibration flow: show a crop and the detector result, then let the user label it. Store labels locally for tuning/tests.
- Detect UI scale/resolution changes and ask for reacquisition when saved normalized regions no longer match.
- Build a calibration health screen: BAR confidence, PROMPT OCR confidence, last Reel confirmation, capture latency, and stale-region warnings.

## Priority 3 — reduce installation prerequisites

1. Ship a documented one-command Windows bootstrap and keep dependencies isolated in the local virtual environment.
2. Audit dependencies and make optional acceleration packages truly optional.
3. Produce a self-contained Windows build (for example a frozen executable) so normal users do not install Python or libraries.
4. Add signed/versioned release artifacts and upgrade verification. This is harder because OCR/native capture dependencies and Windows security tooling must be tested on clean machines.

## Priority 4 — Advanced Fishing mode

Advanced mode is deliberately separate from Bot 101. Add capabilities only after recordings demonstrate reliable cues:

- fish-pool/ripple candidate detection and confidence scoring;
- automatic target selection from multiple screen candidates;
- cast landing feedback and automatic recalibration;
- camera/player positioning toward a selected pool;
- controlled travel between spots after depletion;
- repeated cast/fight/catch cycles with bounded timeouts and emergency release.

Movement or meaningful camera rotation must invalidate position-dependent cast calibration. BAR/PROMPT HUD regions can remain valid when they are screen-fixed.

## Priority 5 — data-assisted improvement

Record only opt-in crops/telemetry needed to reproduce recognition errors. A local ask-and-answer workflow should let a user label examples such as “this is Reel (Hold)” or “this is No fish”. These examples can improve rules and tests. An LLM may be offered later for offline analysis of reviewed samples, but core fishing must never require an online LLM.

## Engineering gates

Each step should preserve F8/focus-loss input release, Preview-before-Live validation, bounded queues/timeouts, and local-only recognition. Add synthetic tests for every new state transition and use Windows/Linux CI where applicable. Advanced movement should remain opt-in until validated in real gameplay.
