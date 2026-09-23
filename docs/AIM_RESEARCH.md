# Aim Lab research: visual tracking + Scout fusion

Status: first observational Aim Lab implemented. It tracks user-seeded targets, draws boxes/head-candidate bands, records crosshair error and visual impact candidates, and can run the independent Scout process/memory sidecar in the same session. It does **not** move the mouse, fire, or write game memory.

## Why start with tracking rather than automatic aiming

A useful aim assistant needs several separate measurements:

1. target detection / identity;
2. target tracking over time;
3. a stable target point (for example a head or weak-point candidate);
4. crosshair-to-target screen-space error;
5. target distance and relative elevation;
6. projectile speed / gravity / drag / launch offset if applicable;
7. target velocity and lead;
8. shot result: miss, ordinary hit, or critical hit.

Trying to jump directly to mouse movement hides which measurement is wrong. Aim Lab therefore records each layer independently so visual and memory evidence can be compared first.

## Current v1 visual tracker

The first tracker has no model dependency. The user places the cursor over a visible target and presses **ACQUIRE AT CURSOR**. Aim Lab stores a local grayscale appearance template and searches near the previous target position with normalized template matching.

Each Scout event records:

- target ID;
- client-pixel and normalized bounding box;
- tracking confidence;
- a provisional head-candidate band (upper 28% of the target box);
- crosshair-to-head-candidate error in pixels;
- lost-frame count.

The click-through overlay is excluded from capture where Windows display-affinity exclusion is available, so its rectangles should not feed back into the tracker.

This is intentionally a bootstrap tracker. It is expected to lose targets after large scale/pose changes, strong occlusion, or very fast camera movement.

## Research direction: detector + multi-object tracker

Modern multi-object tracking normally separates **detection** from **association/tracking**. A detector proposes boxes/classes; the tracker maintains IDs between frames.

Useful future options:

- custom YOLO detector trained on Dragonwilds target screenshots;
- ByteTrack as a lightweight ID association baseline;
- BoT-SORT when camera-motion compensation becomes important;
- pose/keypoint model if a reliable head/weak-point keypoint can be trained.

Ultralytics documents persistent video tracking and multiple trackers including ByteTrack and BoT-SORT. ByteTrack's original paper describes associating both high- and lower-confidence detection boxes to reduce fragmented tracks.

References:

- https://docs.ultralytics.com/modes/track/
- https://docs.ultralytics.com/datasets/track/
- https://arxiv.org/abs/2110.06864

A custom model is preferable to assuming a generic person detector will understand Dragonwilds enemies. Training data can be collected by Scout crops plus manual target/head labels.

## Hit / damage / critical-hit evidence

The game displays transient visual feedback when a shot damages a target. Rather than hard-code an unknown colour/font before enough samples exist, the current Aim Lab records a broad center-region **impact candidate** descriptor:

- frame-to-frame visual change;
- bright-pixel ratio;
- warm/red pixel ratio;
- yellow pixel ratio.

Manual **MARK HIT**, **MARK CRIT**, and **MARK MISS** annotations are written on the same monotonic timeline. This allows later analysis to learn which visual features actually distinguish ordinary damage, critical damage, and unrelated screen changes.

Next detector stages:

1. collect labelled hit/crit/miss sessions;
2. inspect where the damage/crit indicator appears;
3. derive a tighter ROI;
4. test colour / contour / OCR / template features;
5. measure precision and recall;
6. only then enable automatic hit/crit classification.

If damage numbers are readable, OCR can also provide a numeric damage value. If critical hits use a stable glyph/colour, template or colour segmentation may be more reliable and faster than OCR.

## Distance and projectile-drop research

A visual bounding box does not provide metric world distance by itself. Candidate distance sources should be evaluated in this order:

1. game/Unreal reflected property or read-only memory candidate;
2. depth or target-distance UI value if exposed;
3. calibrated monocular estimate based on known target dimensions;
4. empirical shot model fitted from labelled sessions.

For an empirical projectile model, record:

- target track / head-candidate screen coordinates;
- crosshair coordinates;
- candidate distance;
- target vertical offset / elevation if obtainable;
- bow/weapon/ammo identity;
- draw duration if variable;
- shot timestamp;
- target motion;
- HIT / CRIT / MISS result.

A first fitted model can predict the required vertical pixel offset as a function of distance. If later Scout exposes world-space camera, target position, projectile speed, and gravity, the model can move from screen-space fitting to a ballistic solution.

## Scout synchronization

Scout is the common evidence bus, not a separate feature silo.

Auto Picker, Fishing and Aim create their own domain session, while the optional **independent Scout sidecar** can simultaneously record:

- cursor/crosshair probes;
- OS process telemetry;
- configured read-only memory watches;
- shared annotations.

That means one Aim session can contain target boxes, impact candidates, memory values and process metadata under the same session ID and monotonic clock. The same sidecar can run with Auto Picker or Fishing, allowing candidate memory values to be correlated against all three feature domains.

The analyzer treats these streams independently but joins them by session and monotonic time.

## Next experiments

1. Collect several Aim sessions with one stationary target and repeated HIT / CRIT / MISS labels.
2. Repeat with the same enemy moving laterally.
3. Repeat at clearly different distances.
4. Inspect tracking-confidence and crosshair-error distributions.
5. Identify the visual region containing damage/crit feedback and tighten its detector.
6. Discover read-only candidates for target identity, target distance, camera pose or target transform.
7. Compare those candidates against the visual target track before considering any automatic mouse movement.

