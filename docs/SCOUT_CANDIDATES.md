# Scout semantic memory candidates

Scout can now attach **names and intended meanings** to read-only memory locations instead of treating every address as an anonymous watch.

A semantic candidate has four fields:

- **name** — your stable project-side identifier, e.g. `reel_flag_01`;
- **domain** — `fishing`, `auto_picker`, or `general`;
- **role** — what we suspect the value represents;
- **spec** — read-only address definition: `MODULE+0xOFFSET:type` or `0xADDRESS:type`.

Supported primitive types:

`u8 u16 u32 i32 u64 i64 ptr f32 f64`

`ptr` currently means "read a pointer-sized raw integer". Scout does not automatically dereference pointer chains.

## Recommended Fishing roles

Use these role names when testing candidates:

- `phase` — overall minigame phase/enum;
- `hooked` — fish has bitten / fight active;
- `reel_allowed` — REEL can/should be used;
- `pull_direction` — left/none/right state;
- `tension` — bar/tension value;
- `progress` — catch/fish progress;
- `spot_state` — active/depleted/no-fish/cooldown;
- `widget_stop` — STOP Fishing widget visibility/state;
- `widget_pull_left` / `widget_pull_right`;
- `widget_reel`;
- `result` — catch/fail/result state.

Priority discovery targets are `phase`, `reel_allowed`, and `pull_direction`.

## Recommended Auto Picker roles

- `focused_actor` — pointer/reference to the actor currently selected by the interaction system;
- `actor_class_id` — class/type identifier if a numeric candidate is found;
- `interaction_action` — pickup/open/talk/use/etc. enum;
- `can_interact` — availability boolean;
- `distance` — player/camera to focused object;
- `required_range` — interaction radius;
- `prompt_state` — hidden/visible/available/blocked state;
- `item_id`;
- `item_quantity`;
- `inventory_free`;
- `interaction_cooldown`.

Priority discovery targets are `focused_actor`, `interaction_action`, and `can_interact`.

## Recording behavior

When Auto Picker or Fishing starts with the independent Scout sidecar enabled:

1. only candidates for that active domain plus `general` candidates are sampled;
2. every read is written as a `memory/candidate` event;
3. when a value changes, Scout also writes a `memory/candidate_transition` event containing `from` and `to`;
4. visual/controller observations remain on the same monotonic timeline.

This produces records that can answer questions such as:

- did `reel_flag_01` change before REEL OCR appeared?
- does `pull_enum_02` flip consistently when PULL LEFT/PULL RIGHT changes?
- does `focused_actor_01` become non-zero before the pickup prompt becomes readable?
- does `can_interact_03` become true earlier than the visual prompt?

## Analyzer correlation

The standard Scout analyzer now matches candidate transitions against nearby domain landmarks.

Default correlation window:

- candidate may lead the visual/controller landmark by up to **500 ms**;
- candidate may lag it by up to **150 ms**.

Reports show candidate/role, landmark, match count, median delta and p95 absolute delta.

A negative delta means the memory transition happened **before** the corresponding visual/controller event.

Example:

```text
reel_flag_01 (reel_allowed) ↔ state:REEL
matches=19
median Δ=-74 ms
p95 |Δ|=91 ms
```

That is the kind of signal worth validating across more sessions.

## Candidate promotion rules

Do not use a discovered address for controller decisions merely because one run looks good.

Before treating it as trusted, validate at least:

- 20+ relevant transitions;
- 3+ game launches;
- multiple scenes/areas;
- low unrelated transition rate;
- stable module-relative resolution or documented pointer path;
- graceful invalidation after a game build change;
- read-only behavior.

Scout remains visual-first/fallback-capable until a candidate has enough evidence.
