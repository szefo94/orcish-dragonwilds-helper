# Orc Presser Framework — reusable features and how to derive other games

> **Status: architecture reference / partially historical.** This document preserves reusable design patterns and older framework rationale. For current repository structure and implemented behavior, verify against `src/orcpresser/`, `tests/`, `AGENTS.md`, and `docs/README.md`.

**Entry point for new projects.** Orc Presser is split into a generic base and one game-specific profile. A new game is a new profile ("Dog") derived from the generic base ("Animal"). Only what differs gets overridden. Everything else in this document is inherited as-is.

Framework baseline: **2.2-era architecture notes**. The project has evolved beyond this snapshot; the feature log remains useful historical context, but concrete version/layout claims below should be checked against the current tree.

Legend for **Reuse** below:
- **Drop-in**: no changes needed for another game.
- **Profile**: works after filling in a `GameProfile` subclass.
- **Adapt**: code changes needed; the section says where.

---

## 1. Architecture at a glance

**Folder layout** (2.0+ baseline): the runtime split still centers on root launch/update scripts, `src/`, `data/`, `docs/`, and `tests/`. The current repository also contains project-governance, publication, website, roadmap, and agent-guidance files/directories; do not treat the older "four root files" convention as a current invariant.

| Folder | Contents | Shipped in updates? |
|---|---|---|
| `src/orcpresser/` | Code | Yes, replaced on update |
| `data/` | User data | No, created at runtime and never shipped |
| `docs/` | Documentation: CHANGELOG (history + verification log), FRAMEWORK | Yes |
| `tests/` | Unit tests | Yes |

- `paths.py` defines these locations and migrates the old flat layout.
- `maintenance.py` backs Setup.cmd (incl. `clean`, option 6); `updater.py` backs Update.cmd; `version.py` holds the version.
- A derived game project should copy this split: users see two scripts, updates can't overwrite their data.


```
   game_profile.py            GameProfile  (base: "text + bright keycap" prompt games)
                                   ├── Dragonwilds
                                   └── YourGame   ← you add this

   Pipeline (one scan, worker thread)
   capture.py      Grabber ─────► frame (BGR numpy)
   vision.py       keycaps() ──► strips() ──► OCR path ──► associate() ──► Prompt list
   learn.py        Learner (memory / templates) short-circuits OCR for known prompts
   engine.py       Controller ── confirmation, latch, repeat, hold ──► key down/up
   app.py          WinIO (SendInput, focus, F8/\ hotkeys) + tkinter UI shell
   settings.py     Settings (per-profile JSON persistence)
```

| File | Game-specific? | Role |
|---|---|---|
| `game_profile.py` | **Yes, only here** | Actions, text patterns, hold rules, keycap thresholds, window match |
| `vision.py` | No | Keycap detection, OCR paths, prompt association, exclusions |
| `learn.py` | No | Learned OCR shortcuts (nearest-neighbour memory, templates) |
| `engine.py` | No | Decision/timing state machine, no Windows or OCR dependency |
| `capture.py` | No | mss / DXGI screen capture |
| `settings.py` | No | Persistent settings, one section per profile |
| `app.py` | Mostly no | UI and Windows I/O. Theme and texts are Dragonwilds-flavoured (Adapt) |

---

## 2. Deriving a new game: step by step

1. **Collect evidence.**
   - Take 10–20 screenshots of the game's interaction prompts at your normal resolution and UI scale.
   - Include every action you want, both hold and tap variants, and bright and dark backgrounds.
   - Note what the prompt looks like: text position relative to the key box, key box colour, and how "hold" is shown.
2. **Check the base assumptions** (section 5). If the game breaks one, see the *Adapt* notes there.
3. **Create the profile** in `game_profile.py`:

   ```python
   class MyGame(GameProfile):                 # "Dog(Animal)"
       name = 'MyGame'                         # also the settings section and UI title
       window_match = ('mygame',)              # window title or process name contains this
       actions = (                             # longest phrases first
           ('Pick Up All', r'^pick up all\b'),
           ('Pick Up',     r'^pick up\b'),
           ('Open',        r'^open\b'),
       )
       default_allowed = ('Pick Up',)
       opt_in = ('Open',)                      # never ticked by default
       requires_hold = ()                      # actions that are only valid as holds
       hold_pattern = r'\bhold\b'              # how "hold" appears in the prompt text
       keycap_min_bright = 150                 # tune if keycaps are dimmer than Dragonwilds'
       data_dir = 'learned_mygame'             # keep learned data separate per game
   ```

4. **Select it.** Set the `ORC_PROFILE=MyGame` environment variable, for example in a copy of `Run.cmd` (add `set ORC_PROFILE=MyGame` before the python line), or call `load('MyGame')`. Settings and learned data are stored per profile.
5. **Tune in PREVIEW.**
   - **Keycaps:** watch the gold boxes. No gold box on a keycap means adjusting `keycap_min_bright`, `keycap_max_spread` or `keycap_size`.
   - **Text:** check the raw text line. If an action isn't recognised, fix its regex.
   - **Reads:** use "Last 5 reads" to check stability.
6. **Add a test** like `test_v16.Profiles.test_derived_profile` with your own classify and hold cases.
7. **Enable speed options one at a time** (section 3.7): memory, then templates, and so on.

---

## 3. Feature catalogue

Each entry covers: what it does, where it lives, how reusable it is, how to adapt it, and pitfalls.

### 3.1 Screen capture with fallback
- **Where:** `capture.Grabber` (`grab(rect)`, `set_dxgi(on)`).
- **Reuse:** Drop-in. **Needs:** mss; optionally dxcam (Windows only).
- **What:** captures via DXGI Desktop Duplication when enabled and the region is on one monitor; otherwise mss. It falls back per scan on any error. `last_backend` reports which method was used.
- **Pitfalls:**
  - Create the Grabber in the thread that uses it (mss is per-thread).
  - Call `SetProcessDpiAwareness(2)` so coordinates are physical pixels.

### 3.2 Window-relative capture region, region editor, crop advisor
- **Where:** `App.capture_rect`, `App.select_region(suggested=None)`, `App.suggest_crop`, `App.observe_geo`.
- **Reuse:** Drop-in. The editor and advisor are tkinter; the geometry maths is generic.
- **What:**
  - The region is stored as fractions of the game client area, so it follows window moves and resizes.
  - The editor supports edge drag (widen or narrow), move, new box, ENTER or double-click to apply, ESC to cancel.
  - The advisor builds a box from where recognised prompts actually appeared, and derives a text-span factor from the same observations.
- **Adapt:** the advisor assumes the text sits left of the key (`left = text_left`). Mirror it for right-hand text.

### 3.3 Keycap detection
- **Where:** `vision.keycaps(frame)`; thresholds in `GameProfile.keycap_*`.
- **Reuse:** Profile.
- **What:** masks bright, low-saturation pixels, closes the mask, finds contours, and keeps roughly square boxes of plausible size. It costs about 1–5 ms per frame. `has_glyph` separates real keycaps from letter holes (o, e).
- **Adapt:**
  - Coloured keycaps (e.g. yellow): replace the neutral-bright mask with an HSV range. Add a `keycap_mask(frame)` method to the profile and call it from `keycaps()`.
  - Round gamepad glyphs: aspect limits stay near 1, but raise the contour-area rule.

### 3.4 OCR paths (strip OCR)
- **Where:** `vision.Detector` with `ocr_strip`, `rec_only`, `reread_keys`, `strips`, `text_extent`.
- **Reuse:** Drop-in, given the base assumptions.
- **What:**
  - OCR runs only on strips around keycaps, not the whole region.
  - RapidOCR is configured with `det_limit_type='max'`. **Important for any project using RapidOCR:** the default `min/736` upscales every small input.
  - Three paths, chosen by options:

    | Path | Method | Synthetic result |
    |---|---|---|
    | Full | 2× upscale, then detection + recognition | ~220 ms |
    | Fast detection | Native-size detection, recognition from a 2× crop, text cut at the keycap | ~105 ms |
    | Recognition only | Text extent from bright columns, no detection model | ~107 ms |

  - The key letter gets a second, direct read if missed or low-confidence (`reread_keys`).
- **Pitfalls:** the RapidOCR models are Chinese+English; non-Latin UI languages need a different recognition model.

### 3.5 Prompt association and rules
- **Where:** `vision.associate`, `GameProfile.classify / is_hold / accept`, `Prompt` dataclass.
- **Reuse:** Profile.
- **What:**
  - Links row text to the key inside the box by position.
  - Classifies the action and detects hold.
  - Profile veto: e.g. Siphon without "Hold" is rejected, never turned into a tap.
  - The allowlist order is the priority order. A confidence gate of 0.82 applies.
- **Adapt:** override `accept()` for game rules such as "never press on a red prompt". Add fields to `Prompt` if needed.

### 3.6 Exclusions (skip by object name)
- **Where:** `vision.exclusions`, `excluded_term`, `context_text`; UI text box; persisted in settings.
- **Reuse:** Drop-in.
- **What:**
  - Comma list, case-insensitive, matching at a word start (`stone` hits `Stones`, not `Limestone`).
  - Context is the prompt row plus about 4 keycap heights above, where the object name is expected.
- **Adapt:** if the object name sits elsewhere, change the vertical window in `context_text` and in `strips(context=True)`.

### 3.7 Learned shortcuts (skip OCR for known prompts)
- **Where:** `learn.Learner`, `learn.Memory`, `learn.Templates`.
- **Reuse:** Drop-in. Data is per profile via `data_dir`.
- **What:**
  - **Memory:** a nearest-neighbour classifier over small normalised images labelled by OCR. Recall takes about 3 ms.
  - **Templates:** action wording and key letters learned separately, so they compose. About 12 ms.
  - **Commit rule:** a label is stored only after two agreeing OCR reads.
  - **Refusal:** an unknown or ambiguous image returns nothing, and OCR handles it.
  - **Storage:** size cap in MB, at most 30 samples per label, near-duplicates skipped.
  - **Persistence:** npz + JSON, no pickle.
- **Pitfalls:** thresholds were calibrated on synthetic images (see the Verification log in docs/CHANGELOG.md). Check them on the new game; they sit in `Memory.T_*` and `Templates.T_WORD`.

### 3.8 Decision engine (timing and safety state machine)
- **Where:** `engine.Controller`.
- **Reuse:** Drop-in. Pure Python and unit-testable.
- **What:**
  - N matching scans before the first press (1 or 2).
  - One-shot latch until the prompt disappears.
  - Optional clock-driven repeat: interval, tap length, and a 0.5 s freshness window.
  - Holds with a 15 s maximum.
  - Watchdog release when scans stop.
  - Manual modes: Repeat, Hold, Timed.
- **Adapt:** new behaviours (e.g. alternate two keys) go in `observation()` / `tick()`. Keep the `down()`/`release()` pairing.

### 3.9 Windows input and safety shell
- **Where:** `app.WinIO`.
- **Reuse:** Drop-in on Windows.
- **What:**
  - Output through SendInput.
  - Reserved keys: F8 is panic release+stop, `\` is start/stop.
  - Stops when the game loses focus.
  - A heartbeat watchdog releases held keys if the UI stalls.
  - Binds to the game window by title or process through `GameProfile.matches_window`.
- **Stuck-key protection:** `release_all()` sends key-up for every key used in the session plus all mouse buttons. It runs on F8, on close, at exit, and at start-up after an unclean exit. An extra key-up is harmless; a missing one leaves a button held system-wide.
- **Pitfalls:** games using raw input or anti-cheat may ignore or flag synthetic input. Check the game's rules before using it.

### 3.10 Scan scheduling and stale-result protection
- **Where:** `App.tick` (`SCAN_GAP`, single job in flight), `App.drain` (generation counter, 1.2 s staleness), `App.worker`.
- **Reuse:** Drop-in.
- **What:**
  - One scan in flight at a time.
  - Any settings change bumps a generation number, and results from older generations are dropped.
  - Scans are also discarded if focus changed or the result is too old.

### 3.11 UI shell features
- **Where:** `app.App`.
- **Reuse:** Drop-in, apart from the theme.

| Feature | Details |
|---|---|
| PREVIEW / LIVE run buttons | Same button stops, the other switches; `\` repeats the last choice |
| Unfocused opacity | 0 = minimize on focus loss, because an invisible topmost window would still eat clicks |
| Click-off | Clicking outside a text field clears its focus |
| Last 5 reads log | Distinct results only; ▶ = key sent, [M]/[T] = learned result |
| Resource meter | CPU / RAM chart, scan time, capture backend, CPU/GPU engine |
| Panel-overlap guard | Refuses to capture while the panel covers the region |

- **Adapt:** colours and header art are constants at the top of `app.py` (`BG`, `PANEL`, `GOLD`…) and in `build()`.

### 3.12 Persistent settings
- **Where:** `settings.Settings(path, section)`; `App.persist(key, value)`.
- **Reuse:** Drop-in.
- **What:** one JSON file with one section per profile, atomic writes, and writes batched 400 ms after the last change; also saved on close. A corrupt file falls back to defaults. Currently persisted: `exclude`.
- **How to persist more:** read the initial value with `self.settings.get('key', default)` when creating the widget, and call `self.persist('key', value)` in its change handler.

### 3.13 GPU runtime switch
- **Where:** `Setup.cmd` options 2/3 (`gpu`/`cpu`), the `data/runtime-gpu.flag` marker (so a repair keeps DirectML), `Detector(gpu=True)`.
- **Reuse:** Drop-in.
- **What:** swaps onnxruntime for onnxruntime-directml; the checkbox is enabled only if `DmlExecutionProvider` is present.
- **Pitfall:** rerunning Setup.cmd reinstalls the CPU runtime.

### 3.14 Reaction-time meter
- **Where:** `engine.ReactionMeter` (`scan(identity, capture_stamp)`, `fired(now, label, scan_ms, source)`, `summary()`); wired in `App.drain`.
- **Reuse:** Drop-in. Pure Python.
- **What:** measures from the capture of the first scan that saw a prompt to the key being sent, or to the decision in preview. Only the first press per sighting counts. Keeps the last 10 for average, best and worst.
- **Use it for:** comparing speed options per game, and regression checks after changes.

### 3.15 Responsive layout and window persistence
- **Where:** `App.layout`, `fit_settings`, `natural_size`, `place_window`, `track_window`, `save_window`, `work_area`, `on_screen`.
- **Reuse:** Drop-in for any tkinter tool.
- **What:**
  - Settings flow into two columns when there is room; otherwise they stack.
  - The scrollbar appears only when content overflows.
  - First launch fits all options on screen.
  - Size, position and maximized state are restored on the next launch, with a monitor check (Win32 `MonitorFromPoint`).
- **Pitfall:** Tk reports `1x1` geometry before the window is mapped. Save the geometry you set, not the one Tk reports at startup.

### 3.16 Start-up robustness: stages, stall detection, safe start ("zero point"), log
- **Where:**
  - `App.worker` (`stage(...)` messages)
  - `App.loading_progress`
  - Safe start logic in `App.__init__` (`ORC_SAFE`, `engine_ok`, `clean_exit` in settings)
  - `Learner(load=, persist=)` and `load_error`
  - `setup_log` / `data/orcpresser.log`
  - `Setup.cmd` option 4 (`safe`)
- **Reuse:** Drop-in.
- **What:**
  - Every slow start-up step reports its name, so a hang shows where it is.
  - A stage over 45 s is flagged.
  - A start that never became ready makes the next start clean: default window, no learned data, options off.
  - Corrupt data is moved aside, not fatal.
- **Rules learned the hard way:**
  - Never import heavy native libraries (DirectX/COM, GPU runtimes) in the UI thread just to test that they are installed. Use `importlib.util.find_spec`.
  - Keep diagnostic UI code in its own try/except so it can never break the main loop.

### 3.17 Key table (names → input codes)
- **Where:** `keys.py` (`resolve`, `canonical`, `dropdown`, `RESERVED_VK`); used by `WinIO.key/event` and the key dropdown.
- **Reuse:** Drop-in.
- **What:**
  - Mouse buttons (incl. X1/X2 via `mouse_event` data) and keyboard keys with the correct *extended* flag.
  - Aliases (`LButton`, `PgUp`, `XButton1`), F1–F24.
  - Reserved keys are refused with a reason.
- **Adapt:** add game-specific names to `_ALIASES`. Change `RESERVED_VK` if you move the hotkeys.

### 3.18 Per-tab visibility
- **Where:** `App.vis` (widget → modes or `callable(mode)`), `show(widget, modes)` in `build()`, `App.apply_visibility()`.
- **Reuse:** Drop-in for tkinter.
- **What:** each tab shows only its widgets. The original pack order is recorded once and re-applied, so hiding and showing never reorders anything. Conditional rows (e.g. duration only when *Timed* is ticked) use a callable.

### 3.19 Precise timing for manual modes
- **Where:**
  - `Controller.next_due(now)`
  - The adaptive `after()` at the end of `App.tick`
  - The anchored schedule in `Controller.tick` (Repeat)
  - `timeBeginPeriod(1)` in `__main__`
- **Reuse:** Drop-in.
- **What:** the UI loop wakes up exactly when the next press or release is due.
  - The repeat schedule is anchored, so late wake-ups don't add up.
  - After a stall longer than one interval, it restarts instead of bursting to catch up.
  - Windows timer resolution is set to 1 ms.

### 3.20 Experimental skill notes (spec before code)
- **Where:** FISHING tab, `src/orcpresser/fishing_notes_default.md` → `data/fishing_notes.md` (auto-saved, atomic).
- **Reuse:** Pattern.
- **What:** before automating a new game activity, write its state machine, the signals it needs and the unknowns into an editable spec that lives in the app. The fishing notes are the template: sources marked [WIKI]/[GUIDE]/[ASSUMPTION], a state machine draft, and a list of signals to capture.

### 3.21 Version updater (core file)
- **Where:** `Update.cmd` (root), `src/orcpresser/updater.py`, `src/orcpresser/version.py`.
- **Reuse:** Drop-in for any project with the same layout. Change the zip name pattern `OrcPresser_*.zip` and `ROOT_FILES`.
- **What:**
  - Finds the newest update zip by the `VERSION` inside it; old 1.x zips without it are ignored.
  - Mirrors the code folders, moving removed files into `data/old_versions/<old>/`, and overwrites the root scripts.
  - Migrates data, reinstalls packages only if `requirements.txt` changed, and archives processed zips.
  - `--force` reinstalls the same version; `--yes` skips the prompt.
- **Rules learned:**
  - Compare versions numerically (2.10 > 2.9), never by file name.
  - Mirror code folders, don't just overwrite them. A leftover module from an old version can shadow a new one, or keep an obsolete test running.
  - A batch file that may overwrite itself must run as one `( ... )` block, because cmd re-reads a script file line by line while running it.

### 3.22 Automated benchmark and suggestions
- **Where:** `bench.py` (`plan`, `CameraPath`, `PhaseStats`, `Benchmark`, `recommend`, `save`/`load_all`); UI in the STATS tab (`start_bench`, `bench_tick`, `finish_bench`, `draw_charts`, `show_suggestions`); `WinIO.move` for the camera.
- **Reuse:** `bench.py` is UI-free and game-free. It needs a scan callback and a relative mouse move.
- **What:** tests configurations of ticked options against a Baseline in two phases:
  - **Static:** the scene stays still.
  - **Camera:** a sinusoidal mouse sweep of whole periods, identical for every configuration, ending exactly at the start. This gives comparable lighting, angles and scenery across configurations.
  - Before each phase, a settle window excludes engine switches from the measurement.
  - Without screen ground truth, results are relative to Baseline: its static majority label is the reference, and its camera label set defines agreement.
  - `recommend()` marks options suggest / avoid / neutral from speed, detection and agreement against Baseline, plus reaction time and flicker for single-scan. It gives nothing if Baseline saw no prompt.
- **Adapt:** for another game, change the phases (e.g. strafe instead of camera sweep) and the metric thresholds in `recommend()`.
- **Pitfalls:**
  - **Order and drift:** configurations run one after another, so in-game lighting or weather can drift during a long run. Keep phases short and repeat runs to confirm.
  - **Learned data:** learned-memory results depend on data learned before and during the run.

---

## 4. Tests to copy

| File | Covers |
|---|---|
| `test_core.py` | Association, confirmation, holds |
| `test_update.py` | UI mode wiring |
| `test_v13.py` | Exclusions, repeat, opacity |
| `test_v14.py` | Run buttons, click-off, read log |
| `test_v15.py` | Learned-shortcut safety |
| `test_v16.py` | Profile derivation, settings persistence |
| `test_v17.py` | Reaction meter, window placement |
| `test_v18.py` | Start-up robustness, stuck-key release |
| `test_v19.py` | Key table, Hold/Timed, repeat scheduling |
| `test_layout.py` | Folder layout and migration |
| `test_updater.py` | Updater: zip versions, mirroring, data untouched, archiving |
| `test_bench.py` | Benchmark: plan, camera path, timing, stats, suggestions |
| `test_cleanup.py` | Clean-up never lists user data |

Run all from the root with `python -m unittest discover -s tests -t .`, or Setup.cmd → 5. None of them need the OCR model. `tests/__init__.py` puts `src/orcpresser` on the import path.

## 5. Base assumptions (what "Animal" expects) and how to break them

| Assumption | If your game differs |
|---|---|
| Prompt = action text left of a bright, neutral, square keycap with one character | Right-hand text: mirror `span`, `text_extent`, `strips`. Coloured caps: custom mask (3.3). Multi-character keys ("Space", "LMB"): change `key_pattern`, `reread_keys` validation, `key_patch` size |
| Latin-script UI text | Swap the RapidOCR recognition model |
| "Hold" is written in the text | Other hold cues (ring icon, progress bar): add an image check in `accept()` |
| Windows, keyboard output | WinIO is Windows-only; the pipeline and engine are portable |
| One prompt focus at a time, highest priority wins | Multi-target games: iterate `prompts` instead of `prompts[0]` in `App.drain` |

## 6. Faster alternative: reading game data

For Unreal Engine games, a UE4SS Lua mod can publish the interaction target directly, so no OCR is needed. The plan and data-collection checklist are in the Google Doc *"Orc Presser — plan: odczyt danych z gry przez UE4SS (opcja 11)"* in the Dragonwilds Drive folder. When implemented, it will be listed here as a feature source with the highest priority, with OCR as the fallback.

---

## Feature log

Every release adds a row here and updates the catalogue above.

| Version | Added / changed (framework-relevant) |
|---|---|
| 1.2 | Base: keycap + OCR association, Controller confirmation and latch, WinIO safety, manual modes |
| 1.3 | Strip OCR + RapidOCR `limit_type=max` fix (~4× faster); exclusions; opacity-0 minimize; configurable auto repeat |
| 1.4 | PREVIEW/LIVE run buttons; click-off focus; last-5 reads log |
| 1.5 | OCR paths (fast detection, recognition only); learned memory and templates with size cap; single-scan confirm; DXGI capture; DirectML GPU; region editor and crop advisor |
| 2.2 | Fewer files: USER_GUIDE folded into README, VALIDATION into CHANGELOG; Setup → 6 clean-up; updater keeps the last 2 updates |
| 2.1 | `Update.cmd` + `updater.py` (core file), `version.py`; STATS tab with automated static/camera benchmark, charts, saved data sets, ★/✕ suggestions in AUTO → 03 |
| 2.0 | Folder layout (root: Setup/Run/README; `src/`, `data/`, `docs/`, `tests/`); `paths.py` with migration; one `Setup.cmd` with menu and arguments |
| 1.9 | Key table and dropdown; Hold + Timed merged (tick); per-tab visibility; OUTPUT live state; precise manual timing (anchored schedule, adaptive tick, 1 ms timer); FISHING notes tab |
| 1.8 | Start-up stages and stall detection; safe start (zero point); corrupt-data fallback; `orcpresser.log`; no heavy imports in the UI thread; `release_all` for stuck keys and mouse buttons |
| 1.7 | Reaction-time meter; responsive two-column settings and auto-hiding scrollbar; window size, position and maximized state persisted |
| 1.6 | **GameProfile base class** (all game-specific data moved to `game_profile.py`, selectable via `ORC_PROFILE`); per-profile persistent settings (exclusions survive restart); this document |
