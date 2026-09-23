# Orcish Dragonwilds Helper

**A Windows companion for RuneScape: Dragonwilds with local OCR interaction automation, repeat and hold controls, performance diagnostics, and experimental fishing assistance.**

Version **2.4** · Previously **OrcPresser** · Python 3.12 · Windows 10/11

Orcish Dragonwilds Helper reduces repetitive keyboard and mouse input. It can read an interaction prompt such as **Collect [E]**, check whether the action is allowed, and press the displayed key. You control where your character stands and looks. Repeat and Hold modes also work as configurable key and mouse-button controls.

The interface uses an Orcish-inspired theme, mode buttons, capture previews, detection feedback, and CPU/RAM charts. Recognition runs locally; the application does not send gameplay frames to a cloud service or use an LLM during play.

> **Fishing is experimental.** Version 2.3 adds recording, calibration, and a supervised single-round controller. Its Windows overlay and live-game recognition still need gameplay validation. Automated tests do not establish in-game reliability.

## Contents

- [Features and modes](#features-and-modes)
- [Requirements and installation](#requirements-and-installation)
- [Controls and window behavior](#controls-and-window-behavior)
- [Auto Presser guide](#auto-presser-guide)
- [Experimental fishing](#experimental-fishing)
- [Performance and diagnostics](#performance-and-diagnostics)
- [Updates](#updates)
- [Local data and privacy](#local-data-and-privacy)
- [Troubleshooting](#troubleshooting)
- [Development and contributions](#development-and-contributions)
- [Project status and licensing](#project-status-and-licensing)

## Features and modes

| Mode | Purpose | Current behavior |
|---|---|---|
| **Repeat** | Repeated key or mouse-button presses | Configurable interval and press duration, in milliseconds. |
| **Hold** | Sustained input | Hold until stopped, or enable a timed hold for automatic release. |
| **Auto Presser** | React to recognized resource interactions | Reads action text and the displayed key; supports allowlists, exclusions, hold prompts, Preview, and Live execution. |
| **Fishing · EXP** | Develop and test fishing assistance | Select capture regions, record a manual run, calibrate cast duration, and supervise one fight/reel cycle. |
| **Stats** | Compare recognition settings on your PC | Benchmarks configurations, displays charts and a comparison table, and suggests options based on measured results. |

Existing OrcPresser installation data and internal `src/orcpresser` paths are retained for compatibility.

## Requirements and installation

- **Windows 10 or 11.** Live capture, input output, and overlay integration are Windows-specific.
- **Python 3.12, 64-bit**, with the Python launcher and Tcl/Tk selected during installation.
- RuneScape: Dragonwilds, preferably in **borderless or windowed mode**, with **English interaction prompts**.
- Internet access to install Python packages. An optional DirectML configuration can accelerate supported recognition workloads; a dedicated GPU is not required for the normal CPU setup.

### Install from GitHub

1. Download **Code → Download ZIP** and extract it, or clone the repository:

   ```sh
   git clone https://github.com/szefo94/orcish-dragonwilds-helper.git
   ```

2. Open the extracted or cloned project folder.
3. Run **Setup.cmd** and choose **1** to install or repair dependencies in the local `.venv`.
4. Run **Run.cmd** to open the helper.

Keep the entire project folder together. You do not need to copy individual Python modules or install packages globally.

### Setup menu

| Option | Purpose |
|---|---|
| **1** | Install or repair the application environment. |
| **2** | Enable the optional GPU/DirectML environment. |
| **3** | Return to the CPU environment. |
| **4** | Safe start with default window settings and without loading learned recognition data. |
| **5** | Run automated self-tests. |
| **6** | Review and clean old backups, archives, and caches. |

## Controls and window behavior

| Control | Behavior |
|---|---|
| **`\`** | Start/stop the selected mode. |
| **F8** | Emergency stop and release held inputs. |
| **Preview** | Observe and display proposed actions without sending gameplay keys. Available for Auto Presser and Fishing. |
| **Live** | Arm actual input execution; switch back to the bound game to run. |
| **Bind Game** | Start a three-second countdown during which you switch to the game window. |

Input is restricted to the bound foreground target. Moving focus away stops active output. Hovering over the helper alone does not count as focusing it; clicking it can change focus and stop the run.

The **unfocused opacity** slider controls how visible the panel remains when it is not focused. At **0**, the panel minimizes when it loses focus instead of remaining as an invisible window. Keep the panel outside capture regions: even a translucent panel can obscure the pixels being analyzed.

## Auto Presser guide

### First run

1. Choose **Auto Presser**, click **Bind Game**, and switch to Dragonwilds during the countdown.
2. Use **Select Region** to frame the interaction text and its keycap. Include the resource name above the action if you intend to use exclusions.
3. Move the helper outside that region, place it on another monitor, or minimize it.
4. Select the actions you want to allow.
5. Start **Preview** and inspect the recognized text, capture image, and intended key.
6. Once the output matches what you see, select **Live** and return to the game.

The capture region tracks the game window. Different display scaling, resolution, UI layout, or camera framing may require adjusting it.

### Supported interactions

| Action | Enabled by default | Output |
|---|---|---|
| Collect | Yes | Tap the displayed key. |
| Harvest | Yes | Tap, or hold when the prompt includes Hold. |
| Siphon | Yes | Hold only when a Hold marker is recognized; existing Auto hold limit is 15 seconds. |
| Collect Water | No | Tap, or hold when indicated. |
| Fill Watering Can | No | Tap, or hold when indicated. |
| Fill Compost Bucket | No | Tap, or hold when indicated. |
| Uproot | No; explicit opt-in | Activate the shown interaction, which can remove a plant. |

When multiple allowed prompts are visible, priority is:

**Siphon → Fill Watering Can → Fill Compost Bucket → Collect Water → Harvest → Collect → Uproot.**

### Exclusions

Enter comma-separated resource names or text fragments, for example:

```text
Stone,Cabbage
```

The detector checks recognized surrounding text to suppress matching interactions. The relevant resource name must be inside the capture area and readable. Exclusions are OCR-based, so verify them in Preview before relying on them. Editing exclusions stops the current run so the new rules can take effect.

### Repeated prompts and hold behavior

By default, a tap is latched to a recognized prompt to avoid repeatedly activating the same interaction. **Repeat persistent tap prompts** enables repeated taps using the configured interval and tap length while the prompt remains recently confirmed.

Two neighboring objects with identical labels can look like one continuous prompt. Look away briefly between them if a new interaction does not trigger. Auto Presser does not walk, navigate to resources, or aim your character.

### Recognition timing

Auto Presser starts scans no more often than every **120 ms**, with **one scan in flight**. That is a scheduling ceiling of approximately **8.3 scans per second**, not a guaranteed OCR rate. Capture, OCR runtime, and UI scheduling determine the actual rate.

The default controller requires **two matching scans** before acting. The optional **Single-scan confirm** setting reduces confirmation latency at the cost of less evidence. Tap duration, repeat interval, and confirmation also affect perceived reaction speed; there is no single fixed capture-to-action latency.

## Experimental fishing

Fishing combines fast color observations with slower OCR in a separate controller. It is intended for supervised experiments and collecting evidence for the next iteration.

### Current fishing implementation

- Explicit **Fishing Bot 101** and **Advanced · EXP** modes.
- User-selected **BAR** and **REEL** capture regions (REEL is stored internally as the prompt region for backward compatibility), plus optional **RESULT** and **SPOT** regions.
- A click-through, non-activating overlay for selected regions and controller state. The overlay is disabled if Windows capture exclusion is unavailable.
- **Preview** that simulates decisions without sending inputs.
- Manual test recording of selected image crops, detection timestamps, and physical **A/D/LMB** states.
- Timed trial casts and manual **short / long / hit** feedback to refine cast duration.
- A supervised fight loop that tries **A/D** on red, reacts to blue, and holds **LMB** when **Reel (Hold)** is confirmed.
- Release/stop handling for uncertain indicators, stale capture, focus loss, F8, timeouts, and recognized results.

### Suggested first session

1. Equip a rod, stand near the fishing area, and keep the player position and camera fixed.
2. Bind the game in the Fishing tab.
3. Select **BAR** tightly around the red/blue indicator and **REEL** around the area where `Reel (Hold)` appears. Add RESULT for result/error messages if needed.
4. Enable **Record manual test**, start **Preview**, and fish manually.
5. Review the recording before trying **Live** assistance.

### Fishing Bot 101 controls

Select **Fishing Bot 101** for the minimal supervised mode. Its minimum setup is **BAR + REEL**. You can also calibrate **ACTIVE** around the `Stop Fishing` indicator shown while a fishing round is active. The **Show calibration overlay** checkbox can display the currently saved BAR/REEL/ACTIVE/RESULT/SPOT rectangles over the game even while the bot is idle, so regions can be adjusted visually; the preference is saved. BAR is the red/blue tension indicator; REEL is the screen area where **Reel (Hold)** appears. The player still casts, positions the character, and moves between ponds manually. RESULT is recommended so the bot can stop on messages such as **No fish here** or **depleted**. SPOT is not required by Bot 101.

For cast calibration, **USE SHORT** tries the current lower hold-time bound, **USE LONG** the upper bound, and **USE MID** the midpoint. After the bobber lands, **WAS SHORT** means it fell short of the target, **WAS LONG** means it went beyond it, and **WAS HIT** means the cast landed correctly and that duration should be saved. Moving the player or changing the camera invalidates this position-dependent timing; use **NEW SPOT / REACQUIRE** and recalibrate if automatic casting is used.

During a fight, the controller holds one direction continuously. When red becomes blue it keeps that same A/D key held; it does **not** pulse or alternate on a timer. Brief `unknown` detector frames also keep the current direction held, so scanning cannot create A/D key-up pulses. Only sustained uncertainty beyond the safety grace releases the direction. When blue becomes red again it swaps A↔D once and holds the new direction. **Reel (Hold)** overrides either direction immediately: A/D is released and LMB is held. When red returns, the direction cycle resumes.

With **Recurring rounds** enabled, a normal catch or recoverable failure releases all input but keeps the bot armed. If ACTIVE is calibrated, the old `Stop Fishing` signal must disappear first, then reappear twice before the next round is armed; without ACTIVE, the bot falls back to the BAR disappearing and then returning. **No fish here**, **depleted**, and bait-required messages remain hard stops requiring manual intervention. Move the character manually to the next spot, press **F7** or click **NEW SPOT / REACQUIRE**, verify BAR/REEL in Preview, then resume.

Color sampling targets **20 Hz**. Prompt OCR is queued approximately every **400 ms**, subject to processing time, and requires two distinct OCR observations for confirmed text actions.

### Advanced · EXP mode

Advanced mode exposes automatic cast timing/calibration and the optional SPOT diagnostic. **USE SHORT**, **USE MID**, and **USE LONG** choose the lower bound, midpoint, or upper bound of the current cast-time bracket. After a trial, **WAS SHORT** raises the lower bound, **WAS LONG** lowers the upper bound, and **WAS HIT** stores the successful duration. This calibration is tied to player/camera geometry and is reset by New spot / Reacquire.

Advanced mode does **not** yet walk the player, steer the camera to ponds, or run unattended multi-spot fishing. Those capabilities remain staged work in `roadmap.md`. Core operation is local and does not require an online LLM.

### Not implemented yet

Automatic positioning, walking, reliable pond-distance measurement, fish-direction tracking, screen-based stamina measurement, bait inventory management, and unattended repeated fishing cycles are not implemented. The SPOT contour is a visual diagnostic rather than proof of a valid cast. Catch and failure phrases remain provisional until verified against real gameplay.

See the [complete fishing guide](docs/FISHING.md) for timing, calibration limits, recording details, and next steps. The old editable Fishing notes textbox has been removed; runtime guidance is shown directly in the Fishing controls.

## Performance and diagnostics

The interface displays CPU and RAM history, scan duration, input counts, and capture/recognition status. Auto Presser offers optional faster detection, recognition-only processing, learned memory, templates, single-scan confirmation, DXGI capture, and DirectML acceleration. Some shortcuts are restricted when exclusions require surrounding text.

The **Stats** tab compares a Baseline with every speed option available on your setup — automatically ticking them off in section 03 for you — both while standing still and during a controlled camera sweep. Each configuration is labelled by the letters of the options it has on (e.g. `FRLTSDG` = all seven on, `-` = Baseline); the plan and the running test both show pending time as M:SS. Charts and recommendations help identify settings that work on your machine.

**Stats does not execute recognized interaction keys, but it does move the mouse for its camera-sweep test.** Keep the game foreground, leave the controls alone during the benchmark, and use F8 to abort. Recommendations are based on that test scene, not a guarantee for every resource or location.

When **Unfocused opacity = 0**, the main helper minimizes on focus loss and a click-through **four-corner status HUD** becomes the primary runtime view over the bound game. Overlay windows are explicitly revived/reasserted as topmost after tab-out/tab-in and after feature stop/start, rather than relying only on the original Tk window mapping. It also appears when the helper is manually minimized. The HUD is available for Repeat, Hold, Auto Presser, Fishing, Aim Lab, Scout Lab and Stats. The corners use distinct high-contrast colours and show mode/state, live recognition or detector output, performance/Scout telemetry, and in-game controls or configuration. Bottom and right panels are clamped to the game client dimensions so they do not extend beyond the visible game area, including on ultrawide displays. If something genuinely requires returning to the full application — for example binding a target, selecting a calibration region, reacquiring a fishing spot, or handling an error — a small amber/red **↩ APP** badge appears near the top centre rather than covering the screen. The HUD is excluded from capture when Windows display-affinity exclusion is available.

## Updates

### Existing OrcPresser 2.2 installation

1. Close the application.
2. Put a prepared **`OrcPresser_2.3.zip`** update archive in the existing installation folder without extracting it.
3. Run **Update.cmd** and confirm.
4. Start **Run.cmd**.

The legacy archive name is intentional: the 2.2 updater recognizes it. User settings, learned data, fishing notes, and the virtual environment remain in place. A full reinstall is normally unnecessary.

The updater accepts packaged `OrcPresser_*.zip` / `OrcishDragonwildsHelper_*.zip` files **and GitHub's `orcish-dragonwilds-helper-main.zip` Download ZIP directly**. Put the downloaded ZIP beside `Update.cmd` and run it without extracting. For a GitHub main snapshot, a same public version is still applied because `main` can contain newer commits between version bumps. Older-version archives are rejected unless `--force` is explicitly used.

To build a versioned package from a checkout instead, run:

```sh
python scripts/package.py
```

The package is written to `dist/OrcPresser_<version>.zip` (the version in `src/orcpresser/version.py`, currently 2.4) and excludes user data and virtual environments. Only use update archives from a source you trust; archives are not signed and updates are not transactional.

### Git checkout

Close the app, commit or stash your development changes, then run `git pull`. Run Setup.cmd option 1 if dependencies changed. Do not apply ZIP updates over a checkout with uncommitted source changes.

For installations older than 2.1, copy the new source over the old installation and run Setup.cmd option 1; the migration code handles the legacy flat data layout. Back up your folder first if it contains local code changes.

## Local data and privacy

| Location | Contents |
|---|---|
| `data/settings.json` | Saved settings and capture-region configuration. |
| `data/learned/` | Learned recognition shortcuts. |
| `data/fishing_notes.md` | User-edited fishing notes. |
| `data/fishing_sessions/` | Optional cropped recordings and observation/input logs. |
| `data/orcpresser.log` | Startup and error diagnostics. |
| `data/old_versions/` | Update archives and backed-up files. |
| `.venv/` | Locally installed Python dependencies. |

Runtime data is excluded from Git and source packages. Manual fishing recording is opt-in and limited to approximately five minutes / 100 MiB per session; detection may continue afterward. Recording samples A/D/LMB states while the bound game is foreground. Review screen crops and logs before sharing them in an issue.

Installation downloads dependencies. Gameplay recognition and recording remain local; cloud accounts, API keys, and an LLM subscription are not required to run the app.

## Troubleshooting

| Symptom | Check |
|---|---|
| Recognition is slow | Tighten the capture area, inspect scan duration, and compare options in Stats. Two-scan confirmation adds latency. |
| A resource is not excluded | Include its name above the interaction in the capture region; verify the OCR text in Preview. |
| Nothing happens in Live | Check the bound window, foreground focus, allowed action, capture region, and that recognition is ready. |
| The helper overlaps the capture | Move it aside or use unfocused opacity 0 to minimize it. |
| Capture is black or distorted | Try borderless/windowed mode; check HDR and optional DXGI capture. |
| Startup hangs or learned recognition behaves oddly | Use Setup.cmd option 4 for a safe start. |
| A key seems held | Press F8; physically press/release the affected key if needed. |
| Inputs fail with an elevated game | A privilege mismatch may prevent input delivery. |
| Fishing does not progress | Recheck BAR/PROMPT regions, inspect Preview, and record a manual session. The controller is experimental. |
| More detail is needed | Inspect `data/orcpresser.log` and run Setup.cmd option 5. Share only reviewed diagnostics. |

## Development and contributions

The project separates perception, control, and UI so work on one feature can be reviewed in a focused pull request.

| Path | Responsibility |
|---|---|
| `src/orcpresser/app.py` | Tkinter application, window binding, guarded Windows input, and UI integration. |
| `src/orcpresser/vision.py` | Auto Presser OCR and prompt recognition. |
| `src/orcpresser/engine.py` | Existing repeat, hold, and automatic interaction control. |
| `src/orcpresser/game_profile.py` | Game-specific action definitions and recognition rules. |
| `src/orcpresser/capture.py` | MSS capture and optional DXGI backend. |
| `src/orcpresser/fishing.py` | Fishing state machine and cast calibration. |
| `src/orcpresser/fishing_capture.py` | Fishing color detection, OCR workers, and local recording. |
| `src/orcpresser/fishing_ui.py` / `fishing_overlay.py` | Fishing controls and overlay. |
| `src/orcpresser/scout.py` / `scout_lab.py` | Immutable Scout recording plus supervised visual/process/read-only-memory research probes. |
| `src/orcpresser/aim_lab.py` | Experimental visual target tracking, head-candidate/crosshair geometry, impact evidence and overlay. |
| `src/orcpresser/scout_analysis.py` | Per-session and cross-session Scout analysis across Auto Picker, Fishing, Aim and Scout Lab. |
| `tests/` | Regression and synthetic evidence tests. |
| `.github/` | CI workflow and issue/PR templates. |
| `docs/` | Fishing instructions, architecture, history, and review notes. |

Install `src/requirements.txt` in a Python 3.12 virtual environment, then run:

```sh
python -m unittest discover -s tests -t . -v
python -m compileall -q src tests
```

Before the initial publication, **110 automated tests passed on Linux**, and an isolated upgrade through the original 2.2 updater preserved user notes. Windows/Linux CI is included; check the repository's Actions tab for current results. Live input and overlay behavior require separate Windows gameplay tests.

For work with multiple developers or coding assistants, use **one feature branch and PR per change**. Give each task a clear scope, keep input guards intact, and avoid simultaneous unrelated edits to `app.py`. Do not commit runtime data, credentials, recordings, or model caches.

- [Contribution guide](CONTRIBUTING.md)
- [Instructions for coding agents](AGENTS.md)
- [Architecture and reusable game profiles](docs/FRAMEWORK.md)
- [Changelog](docs/CHANGELOG.md)
- [Publication review](docs/PUBLICATION_REVIEW.md)
- [Roadmap](roadmap.md)
- [Security reporting](SECURITY.md)

## Project status and licensing

This is an unofficial community helper, not affiliated with Jagex or Blizzard. The theme uses programmatic styling and system fonts; no game artwork is bundled.

No general open-source license has been selected. See [RIGHTS.md](RIGHTS.md) for the current licensing status and [third-party notes](docs/THIRD_PARTY.md) for dependency information.


## Scout research

Research/design for parallel visual + process/Unreal telemetry across Auto Picker and Fishing is documented in [docs/SCOUT_RESEARCH.md](docs/SCOUT_RESEARCH.md). Scout sessions are recorded under data/scout_sessions/ and are treated as immutable raw evidence.

Analyze the newest session with:

    python src/orcpresser/scout_analysis.py --latest

Analyze every Auto Picker, Fishing, and Scout Lab session and build a combined summary with:

    python src/orcpresser/scout_analysis.py --all

`--all` refreshes the individual per-session reports and additionally writes `data/scout_reports/ALL_SESSIONS.json` and `ALL_SESSIONS.md`, with cross-session timing and per-domain summaries. The analyzer never edits, truncates, moves, or deletes the original Scout session files; every per-session report includes SHA-256 hashes of the raw files used.

The **SCOUT LAB** tab is an observational research workspace. After binding the game, it can record cursor and screen-center/crosshair visual probes, OS process telemetry, optional 96×64 cursor crops, and explicitly configured **read-only** memory watches. A watch uses `MODULE+0xOFFSET:type` (preferred across ASLR) or an absolute `0xADDRESS:type`, where type is `u8`, `u16`, `u32`, `i32`, `f32`, or `f64`. Enable **Run independent Scout probes alongside Auto / Fishing / Aim** to put those probes in the same session/timeline as the active feature. With **LMB sample burst** enabled, each left-click in the bound game saves a short screenshot burst at approximately 0/250/600/1000/1500 ms plus a user-editable `labels.csv`; this is the preferred way to label `target`, `head`, `item_pickup`, `hit`, `crit`, `miss`, `inventory`, or other observations after the session without leaving the game. Aim sessions always capture around the screen-centre crosshair. Standalone/other Scout sessions use the free cursor only when it has moved recently away from centre; otherwise they fall back to the crosshair, which avoids stale hidden-cursor coordinates. At t+0, `sample_context/` now gets a downscaled copy of the **original full game screen** with the exact saved 640×360 probe area outlined in yellow and the focus point marked. This replaces the earlier top-right/bottom-left collage, which was a misunderstanding of the intended diagnostic. Memory watches continue sampling during the burst. The Lab does not write game memory or move/aim the mouse.

### Semantic memory candidates for Fishing / Auto Picker

Scout Lab can now save **named read-only memory candidates** instead of only anonymous address watches. Each candidate has a name, domain, semantic role and address/type specification. Fishing roles include phase, hooked, reel-allowed, pull-direction, tension/progress, spot state and individual widget states. Auto Picker roles include focused actor, interaction action, can-interact, distance/range, prompt state and item/inventory candidates.

When the independent Scout sidecar runs with Fishing or Auto Picker, only candidates for that domain (plus general candidates) are sampled. Value changes are logged separately as candidate transitions. The standard analyzer correlates those transitions with nearby Fishing state/vision changes or Auto Picker prompt transitions using the existing causal window (candidate may lead by 500 ms or lag by 150 ms).

See `docs/SCOUT_CANDIDATES.md` for the recommended candidate names/roles and validation workflow.
### Scout Review · analyze first, ask the user second

Captured samples can be processed by the separate offline reviewer:

    .venv\Scripts\python.exe src\orcpresser\scout_review.py --latest

It reads only rows in `labels.csv` whose `analysis_status` is still empty, proposes a label/reason from timing, visual change and residual motion, and then opens a local review queue asking **What do you see?**. Automatic analysis and human confirmation are separate: `analysis_status` tracks whether the program proposed something, while `review_status` tracks `confirmed` / `skipped`. Existing analyzed rows are not recalculated unless `--reanalyze` is used. `--analyze-only` performs the automatic pass without opening the UI. Raw screenshots and Scout JSONL logs are never changed; only the deliberately user-editable `labels.csv` gains review columns.

Captured gameplay shows another useful Dragonwilds signal: **nearby enemies that are actually under the crosshair expose a target HUD with name, level diamond and HP bar**, while farther/background enemies can remain visible without that HUD. Aim Lab now treats the green HP-bar geometry as strong `target_hud` evidence and draws it in magenta with an explanation. This is a confirmation signal, not a body box: distant targets still depend on motion/tracking/learned visual detection. Scout Review uses the same evidence to propose `close_aimed_target` for human refinement (for example `deer_head` or `goblin_body`).

The **AIM LAB · EXP** tab is a research tracker rather than an automatic aimer. Start tracking and press **F6 while still in the game** to seed a visible target at the screen-centre crosshair; you no longer need to click back into the helper to acquire it. The tracker now rejects weak/HUD-edge template matches instead of drawing drifting rectangles. For motion proposals it first estimates dominant camera pan/rotation with sparse optical flow and an affine transform, subtracts that global motion, then draws dashed cyan rectangles only around residual localized motion. This allows moderate view rotation/panning to be analyzed instead of requiring the camera to be almost perfectly still; top/bottom HUD areas remain excluded. Every rectangle has a small reason caption under it (for example template confidence or localized-motion evidence). Manual mark buttons remain optional, but the preferred training workflow is the synchronized LMB screenshot burst + `labels.csv`, because labels can be added after gameplay. Transient center-region visual changes are logged as impact candidates for later damage/critical-indicator classification. See [`docs/AIM_RESEARCH.md`](docs/AIM_RESEARCH.md).
