# Fishing research notes and controller rationale

This file keeps the gameplay observations that originally motivated the Fishing controller. It is background material, not the implementation contract.

For the current user-facing behavior, calibration names, state-machine rules, and limitations, use **`docs/FISHING.md`**. For planned automation, use **`roadmap.md`**.

## Sources and confidence

The original notes were distilled from:
- the official RuneScape: Dragonwilds wiki Fishing material available during development;
- public gameplay guides;
- manual observations and hypotheses that still require in-game validation after game/UI updates.

Markers below:
- **[WIKI/GUIDE]** — gameplay rule described by external documentation used during the original research;
- **[OBSERVED/IMPLEMENTED]** — reflected in the current Orcish controller/detectors;
- **[TO VERIFY]** — do not treat as reliable automation input yet.

## 1. Unlock and gear background

- [WIKI/GUIDE] Fishing uses nets and rods, with spot/tool restrictions.
- [WIKI/GUIDE] Rod casting uses a hold/release interaction where hold duration affects cast distance.
- [WIKI/GUIDE] Fishing spots can deplete and may require moving to another position.
- [TO VERIFY] Exact unlock levels, recipes, fish/bait tables, and region progression should be checked against the current game build before publishing them as authoritative gameplay data.

## 2. Net fishing

Net fishing is conceptually simpler than rod fishing:
- interact with a valid net spot;
- wait for result/animation;
- repeat while the spot and player state allow it;
- stop or move when the spot is depleted.

Potential automation signals:
- interaction prompt;
- result/depletion message;
- stamina/availability;
- spot presence.

Net automation is not the current Fishing Bot 101 focus.

## 3. Rod fishing signals

### Cast
- [WIKI/GUIDE] Hold LMB to charge and release to cast.
- [IMPLEMENTED] Orcish can perform a timed trial cast and learn a position-dependent hold duration from manual SHORT/LONG/HIT feedback.
- [IMPLEMENTED] Player/camera movement invalidates position-dependent cast calibration.

### Waiting / bite
- [IMPLEMENTED] A calibrated **STOP** region can observe the `Stop Fishing` UI while waiting.
- [IMPLEMENTED] When STOP disappears after being confirmed, the controller enters a bounded `BITE_PENDING` state.
- [IMPLEMENTED] STOP disappearance alone does not send input; BAR or PULL evidence is still required.

### Fight direction and BAR feedback
- [WIKI/GUIDE + PLAYER REPORTS] Counter the fish's movement: **fish right -> hold A (left)**, **fish left -> hold D (right)**.
- [OBSERVED/TO VERIFY] A single fight/escape can contain several reversals; direction must therefore be tracked continuously, not chosen once per escape phase.
- [TARGET LOGIC] Fresh, confident movement/PULL direction is authoritative. Repeated movement in the same direction keeps the same key held.
- [TARGET LOGIC] BAR colour is validation/fallback, not the primary direction source: **blue** means the current counter-pull appears effective; **red** means the current choice is likely stale/wrong and direction should be reacquired quickly. A red transition may be used as a fallback swap only when reliable movement direction is unavailable.
- [IMPLEMENTED] Ambiguous PULL evidence is ignored rather than guessed. Short detector gaps preserve the held direction; sustained uncertainty releases it.

### Reel
- [WIKI/GUIDE + PLAYER REPORTS] **REEL has highest priority** while the prompt is valid: release A/D and hold LMB.
- [TARGET LOGIC] If the fish resumes fighting or the REEL signal disappears, release LMB immediately and resume continuous direction tracking; do not assume a fixed direction after REEL.
- [IMPLEMENTED] Fast REEL detection is preferred over slower OCR when available.
- [TO VERIFY / TUNING] Current rough manual estimates for red/blue stamina burn, reel duration, and total catch time are useful for simulation only. Measure them with a timer before treating them as controller constants.

### End of round
- [IMPLEMENTED] Catch/recoverable-failure messages can return to the recurring-round wait state.
- [IMPLEMENTED] Depleted/no-fish and bait-required messages are hard stops that require manual intervention.
- [IMPLEMENTED] With recurring rounds, STOP clear→reappear is the preferred re-arm handshake; BAR disappearance/return is the fallback when STOP is not calibrated.

## 4. Target controller sketch

```text
WAIT_BITE
    -> FIGHT              when the fish takes the hook

FIGHT
    fish moving RIGHT     -> hold A
    fish moving LEFT      -> hold D
    direction reverses    -> switch immediately, even multiple times in one fight
    blue BAR              -> current counter-pull is likely correct
    red BAR               -> reacquire direction; fallback swap only if direction is unavailable
    REEL confirmed        -> release A/D -> REEL

REEL
    while valid           -> hold LMB
    prompt ends / fight resumes
                          -> release LMB -> reacquire fish direction -> FIGHT
```

Round-end, depletion, focus-loss, stale-capture and timeout safety behavior remains as implemented. The implementation currently still differs from this target in several direction/fallback cases.

## 5. Signals still worth researching

- reliable fish/catch progress;
- stamina;
- trustworthy pool/ripple identity and depletion state;
- cast landing feedback;
- world/camera geometry for automatic targeting;
- game-internal Fishing phase, pull direction, reel availability, and result state.

Scout can correlate visual/controller events with read-only semantic memory candidates and optional UE4SS/Frida telemetry. See `docs/SCOUT_CANDIDATES.md` and `docs/INTERNAL_TELEMETRY.md`.

## 6. Safety and validation rules

- Never act on ambiguous PULL evidence.
- REEL overrides A/D and releases the directional input first.
- F8, focus loss, stale capture, and bounded timeouts must release helper-owned inputs.
- Visual control remains the fallback even if game-internal candidates are discovered.
- Validate internal candidates across multiple launches/areas and after game updates before using them in control logic.
