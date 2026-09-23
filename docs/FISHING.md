# Fishing — Bot 101 and staged Advanced mode

Read `src/orcpresser/fishing_notes_default.md` for the original observations. User-edited `data/fishing_notes.md` remains untouched. This implementation has synthetic tests, but has not been tested in a live Dragonwilds session.

## First manual recording

1. Equip a rod, stand near the fishing spot and keep position/camera fixed.
2. Choose Fishing and bind the game. Select BAR tightly around the red/blue indicator, REEL around Cast/Reel, and optionally RESULT around result/error messages and SPOT around the ripple.
3. Move the helper outside these regions or minimize it. Choose Record manual test and PREVIEW, then switch to the game.
4. Fish manually. F8 stops. A click-through, non-activating overlay shows selected regions and proposed actions. It is hidden if Windows capture exclusion is unavailable.
5. Review `data/fishing_sessions/`: timestamped observations and physical A/D/LMB states in JSONL, plus up to one set of cropped images per second. Recording is capped at five minutes / approximately 100 MiB per run; detection can continue. Share reviewed crops and timestamps to refine cue recognition.

Preview simulates controller decisions and sends no input. It can stop on a result or timeout, so restart Preview to record another attempt. Overlay behavior and capture exclusion require a Windows runtime test.

## Cast calibration

Use SHORT (100 ms) then LONG (1200 ms) as conservative initial bounds, not proven game minimum/maximum. Change the hold field within 50–3000 ms if needed. Enable Trial cast only, choose LIVE, and return to the game. Two distinct OCR observations of Cast + Hold trigger one timed LMB hold. The mode releases LMB and stops.

Label the landing WAS SHORT / LONG / HIT manually. Short and long feedback choose the next midpoint; HIT saves the duration. Keep the camera, player and rod fixed. This does not estimate world distance or automatically walk away from the pond. A bright-contour candidate in SPOT is only an overlay diagnostic, not a validated fishing-circle detector.

## Supervised fight loop

Start LIVE after a manual cast, or enable Automatic cast to begin with the saved duration. Two consistent color samples are needed. Red tries A, then switches A/D after 300 ms of persistent red. Blue is a neutral/wait state: directional input is released while the controller waits for fresh prompt evidence. Two fresh OCR observations of Reel + Hold while blue release any direction before holding LMB. This prevents A/D probing from continuing during a confirmed reel opportunity. Red overrides a cached Reel prompt immediately after color confirmation, releasing LMB before pulling.

A confirmed caught/bait/failure message stops the single round. `No fish was caught.` is treated as a recoverable failed round (WAIT_CAST in recurring mode), while `no fish here` / `depleted` still mean the spot should be abandoned. Disappearing prompts or unknown color never count as a catch. Unknown color releases input; focus loss, stale capture (>750 ms), F8 and timeouts stop/release. Result phrases are provisional: `fish caught`, `you caught`, `caught a`, `consider bait`, `escaped`, `startled`, `too close`, `no fish was caught`, `no fish here`, `depleted`.

Color capture targets 20 Hz. In addition, calibrated REEL / PULL L / PULL R regions now have a lightweight white-UI geometry pass about every 100 ms. The fast PULL resolver only emits A or D when one calibrated side is materially stronger than the other; if both regions light up similarly, direction is marked ambiguous and the controller falls back to the bar transition logic rather than guessing. Two consecutive fast samples are required before a visual A/D or REEL decision is trusted.

Prompt OCR remains queued about every 400 ms, subject to actual OCR runtime, and is now primarily semantic confirmation/diagnostics for time-critical fight actions. Raw OCR text per calibrated region is recorded in Scout telemetry so mis-calibrated or overlapping PULL regions can be diagnosed. Cropped capture and OCR run on separate workers with bounded queues.

## Remaining work after a real recording

Verify bite and catch cues, red/blue meaning, pull direction and prompt placement. Add fish-direction tracking, reliable ripple/landing detection and stamina measurement. Stamina support exists in the controller data model but no screen detector feeds it yet. No bait inventory handling, walking, automatic recast loop, stamina management, 3D distance estimation or LLM runtime control is included.

An LLM can analyze selected recording frames offline. It is not in the real-time loop. The recommended structure is fast color/geometry plus slower OCR, with an explicit state machine and bounded actions.

## Fishing Bot 101 and travel

BAR and PROMPT are the two required calibrations. RESULT is recommended for detecting `No fish here`, `depleted`, and other terminal messages. SPOT remains experimental and is not required for the basic mode.

When a result reports no fish/depletion, the controller stops and releases all held input. Move the player manually to another fishing position, then use **NEW SPOT / REACQUIRE**. Player movement or a meaningful camera change invalidates cast timing because the required hold duration depends on geometry; screen-fixed BAR/PROMPT regions remain saved and should be checked in Preview before resuming.

Cast buttons are a bracket search: **USE SHORT** = current lower bound, **USE LONG** = upper bound, **USE MID** = halfway. Label the landing with **WAS SHORT**, **WAS LONG**, or **WAS HIT**; HIT stores the successful duration.

Advanced automatic pool detection, positioning and travel are intentionally separate from Bot 101. See `roadmap.md`.

## Mode split

**Fishing Bot 101** is the minimal supervised mode. Configure BAR and REEL, cast and position manually, and let the controller manage the fight. It holds one A/D direction continuously, keeps it held through blue, swaps once on a stable blue→red transition, and lets confirmed `Reel (Hold)` override A/D with LMB. F7 or **NEW SPOT / REACQUIRE** pauses the workflow after manual movement and invalidates position-dependent cast timing.

**Advanced · EXP** enables automatic cast timing/calibration and the SPOT diagnostic. It is deliberately not presented as autonomous navigation: pool selection, camera steering, walking, and unattended multi-spot cycles are still pending.

The old editable Fishing notes textbox has been removed. Runtime state and next-action guidance are displayed directly in the Fishing panel; longer explanations live here and in the README.

## Faster bite / A-D / REEL evidence

When STOP Fishing has previously been confirmed and then disappears, the controller now enters a bounded `BITE_PENDING` state immediately. It does **not** press anything on STOP disappearance alone. It waits for BAR or PULL evidence, but this state lets the fast detector react before the slower OCR cycle catches up.

During the fight, an exclusive fast PULL-L / PULL-R visual result directly selects A / D after two consistent samples. Ambiguous results (both regions look active, or their scores are too similar) are never used for direction; the existing red/blue transition state machine remains the fallback. A fast REEL visual confirmation has higher priority than A/D and switches to LMB before the slower two-frame OCR confirmation.

Scout records the new fields `pull_direction`, `pull_confidence`, left/right visual scores, `reel_visible`, `reel_score`, per-region OCR text, and their timestamps so we can measure which signal led each controller action.

## Recurring rounds and ACTIVE signal

The optional **ACTIVE** region should tightly cover the `Stop Fishing` label/icon that appears while the game considers a fishing round active. With **Recurring rounds** enabled, the controller does not stop after a normal catch or recoverable failure. It releases A/D/LMB, waits for the previous ACTIVE signal to disappear, then waits for a fresh ACTIVE signal before rearming BAR/REEL handling. This clear-then-reappear handshake prevents stale end-of-round UI from immediately starting another fight. If ACTIVE is not calibrated, the controller falls back to waiting for the BAR to disappear and return. `No fish here`, `depleted`, and bait-required states still stop the bot for manual intervention.
