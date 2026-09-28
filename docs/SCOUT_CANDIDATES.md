# Scout semantic memory candidates

> **Status: research evidence.** Candidate meanings and thresholds here are hypotheses until they pass the documented promotion criteria. Do not wire a candidate into live control solely because it appears in this file.


Scout can attach **names and intended meanings** to read-only memory locations instead of treating every address as an anonymous watch. These candidates are research evidence only: the current controllers remain visual-first/fallback-capable, and a candidate is not promoted into control logic merely because it correlates once.

A semantic candidate has four fields:

- **name** — your stable project-side identifier, e.g. `reel_flag_01`;
- **domain** — `fishing`, `auto_picker`, or `general`; `auto_picker` is the internal Scout domain name for Auto Presser interaction research;
- **role** — what we suspect the value represents;
- **spec** — read-only address definition: `MODULE+0xOFFSET:type`, `0xADDRESS:type`, or a pointer chain in Cheat Engine bracket notation.

Supported primitive types:

`u8 u16 u32 i32 u64 i64 ptr f32 f64`

`ptr` means "read a pointer-sized raw integer" at the final address.

## Pointer chains

Game objects such as a fishing component live on the heap and move every launch, so a stable address is usually a chain from a module-relative base:

```text
[[RSDragonwilds-WinGDK-Shipping.exe+0x4A1230]+0x10]+0x88:u32
```

`[x]` reads the 8-byte pointer stored at `x`; `+`/`-` add an offset. The base is a module (name ending in `.exe`/`.dll`, optionally in double quotes) or an absolute `0x` address; at most 12 levels. **Every number must have `0x`**: Cheat Engine shows offsets in hex, and a bare `10` is rejected instead of being silently read as decimal.

The chain is walked again on every read, so it follows the object when the game rebuilds it. A broken chain is recorded as `pointer_read_failed` or `null_pointer` with a `chain` trail (`0xAT->0xPOINTER` per level) showing which level failed; while the object does not exist (for example outside fishing) that is expected, and a transition from failure to a value is itself logged as `candidate_transition`.

## Importing a Cheat Engine table

SCOUT LAB → **IMPORT CE TABLE** reads a `.CT` file and adds every convertible record as a candidate of the domain selected in the candidate row. The record description becomes the name, and the role is taken from it when it contains a known role for that domain (`fishing phase` → `phase`, `pull direction` → `pull_direction`), otherwise `unknown`. A candidate with the same domain and name is replaced. Byte/2/4/8-byte (signed when *Show as signed*), float and double records with a module-relative or absolute hex address and hex offsets are converted; scripts, strings, byte arrays and symbol/AOB-based addresses are reported as skipped.

Cheat Engine stores pointer offsets with the offset applied last first; the importer reverses them. To check a converted chain, compare the value Scout records with the value Cheat Engine shows for the same record. Without the UI:

```bat
.\.venv\Scripts\python.exe src\orcpresser\ce_table.py data\cheat-engine\OrcishScout.CT
```

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

## Current integration status

- Candidate reads/transitions are recorded on the same monotonic timeline as visual/controller events.
- Domain filtering is implemented for Fishing and Auto Presser research.
- Analyzer correlation is implemented.
- Automatic promotion into controller decisions is **not** implemented; promotion remains a manual engineering decision after validation.
- Optional UE4SS/Frida events can be correlated through the separate internal-telemetry path documented in `INTERNAL_TELEMETRY.md`.

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
