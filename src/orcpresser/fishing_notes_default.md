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

### Pull direction
- [IMPLEMENTED] Calibrated **PULL L** / **PULL R** regions provide the preferred fast direction evidence when one side is clearly stronger.
- [IMPLEMENTED] Ambiguous PULL evidence is ignored rather than guessed.
- [IMPLEMENTED] BAR red/blue state remains a fallback. The controller holds one A/D direction continuously, keeps it held through blue, and swaps once on a stable blue→red transition.
- [IMPLEMENTED] Short unknown-detector gaps preserve the held direction; sustained uncertainty beyond the safety grace releases it.

### Reel
- [IMPLEMENTED] **REEL has highest priority** during the fight.
- [IMPLEMENTED] Two consistent fast REEL samples or two distinct OCR confirmations of `Reel (Hold)` immediately release A/D and hold LMB.
- [IMPLEMENTED] When the fight returns to red after REEL, LMB is released and A/D control resumes.

### End of round
- [IMPLEMENTED] Catch/recoverable-failure messages can return to the recurring-round wait state.
- [IMPLEMENTED] Depleted/no-fish and bait-required messages are hard stops that require manual intervention.
- [IMPLEMENTED] With recurring rounds, STOP clear→reappear is the preferred re-arm handshake; BAR disappearance/return is the fallback when STOP is not calibrated.

## 4. Current controller state sketch

```text
READY / WAIT_CAST
    -> WAIT_BITE          when STOP is confirmed
WAIT_BITE
    -> BITE_PENDING       when confirmed STOP disappears
BITE_PENDING
    -> FIGHT              when BAR/PULL evidence appears
    -> WAIT_BITE          when candidate expires / STOP returns
FIGHT
    -> REEL               when fast REEL or OCR Reel (Hold) is confirmed
REEL
    -> FIGHT              when red fight state returns
FIGHT / REEL
    -> WAIT_CAST          on recoverable round end when recurring mode is enabled
    -> STOP               on depletion, bait-required, timeout, focus loss, stale capture, or F8
```

The exact implementation in `src/orcpresser/fishing.py` is authoritative if this sketch ever falls behind.

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
