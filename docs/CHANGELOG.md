# 2.4 — Orcish Dragonwilds Helper

- **STATS tab now tests the whole option matrix itself.** RUN TEST no longer needs the speed options ticked
  in AUTO → 03 beforehand: it ticks off every option available on this setup (GPU/DXGI only if actually
  usable) and tests Baseline, each option alone, then all of them together.
- **Letter codes replace the old 4-letter abbreviations.** Each configuration is named by the first letter
  of every option it has on — Fast detection/Recognition only/Learned memory/Templates/Single-scan
  confirm/DXGI capture/GPU → F/R/L/T/S/D/G — so all seven on reads `FRLTSDG` and Baseline (all off) reads
  `-`. Used in the pending-test list, the results table and the chart axis labels (`bench.code`).
- **Default phase length is 5 s** (was 15 s), still adjustable 5–60 s per phase; testing the full matrix by
  default stays quick (Baseline + 7 alone + all ≈ 9 configurations).
- **Pending/remaining time is shown as M:SS** (`bench.fmt_time`) both before starting (total pending time
  for the whole plan) and while a test runs (time still pending).
- Verified with 2 new pure-logic tests (letter-code plan naming in canonical option order, `fmt_time`
  rounding/negative-clamping); all 11 `tests/test_bench.py` cases pass. The Tk UI changes in `app.py`
  (auto-ticking options, updated labels/instructions) were reasoned through and compiled but not exercised —
  this environment has no `tkinter`/`cv2`. Not tested on Windows or against the live game.

# 2.3 — Orcish Dragonwilds Helper

- Broader display/repository name; legacy module/data paths retained.
- Experimental fishing capture, no-input preview, manual recording, cast bracketing and supervised single-round fight/reel controller. See FISHING.md for limits.
- Public repository scaffolding and source-only packaging.
- Hardened local ZIP update validation and backups of replaced code.
- 110 automated regression and synthetic checks passed; original 2.2 updater compatibility checked with user notes preserved. No live Windows/gameplay test in this release preparation.

# Changelog

## Version 2.3 — public repository and experimental fishing

- Broader display/repository name; legacy module/data paths retained.
- Experimental fishing capture, no-input preview, manual recording, cast bracketing and supervised single-round fight/reel controller. See FISHING.md for limits.
- Public repository scaffolding and source-only packaging.
- Hardened local ZIP update validation and backups of replaced code.
- 110 automated regression and synthetic checks passed; original 2.2 updater compatibility checked with user notes preserved. No live Windows/gameplay test in this release preparation.

## Version 2.2 — fewer files

- **Docs:** `docs/USER_GUIDE.md` removed. Its still-valid parts (first session, supported actions, troubleshooting) are in the README; its outdated 1.x notes are gone. `docs/VALIDATION.md` is merged into this file as the *Verification log* at the end.
- **Setup.cmd → 6 · Clean up old files** lists sizes and asks before deleting. Candidates:
  - 1.x backups (`data/old_version_backup`)
  - Update backups older than the last 2
  - Update zips left in the main folder
  - The rotated log, a set-aside unreadable learned file, and Python caches
  - Never touched: settings, learned data, notes, test results.
- **Update.cmd prunes** `data/old_versions/` to the last 2 updates after each update.
- **Code:** removed one unused import, one unused constant and one unused field (found with a dead-code scan).


## Version 2.1 — updater and STATS tab

- **Update.cmd + `src/orcpresser/updater.py`:** apply `OrcPresser_<version>.zip` from the root folder.
  - Uses the newest version by the version *inside* the zip (`src/orcpresser/version.py`).
  - Mirrors `src/`, `docs/`, `tests/`: removed files go to `data/old_versions/<old>/`, so no stale module can shadow a new one.
  - Overwrites the root scripts, never touches `data/` or `.venv/`.
  - Runs Setup only when `requirements.txt` changed.
  - Archives the zip. The batch file runs as one parenthesized block, so it can replace itself safely.
- **STATS tab: automated tests.**
  - Configurations: Baseline (all speed options off), each option ticked in AUTO → 03 on its own, and all ticked together.
  - Each configuration runs a **static** phase (stand still facing a prompt, e.g. in water) and a **camera** phase. In the camera phase the app sweeps the camera with an identical sinusoidal mouse path every time and returns it exactly to the start.
  - 2 s settle time before each phase (engine switch). PREVIEW only; every action is recognised during a test.
  - Aborts on F8, focus loss, STOP, or when the panel covers the capture region.
- **Metrics per phase:** scan time (mean, p95), detection %, agreement with Baseline, time to decision, label changes/min, CPU %, share answered by learned data. Saved to `data/benchmarks/bench_*.json`; every saved run can be selected in DATA SETS.
- **Charts:** six bar charts, static (solid) vs camera (outlined). Green/red = better/worse than Baseline by more than 10 %.
- **Suggestions:** from the newest complete run. ★ suggested / ✕ worse, highlighted in AUTO → 03. APPLY SUGGESTED sets them. No suggestions if Baseline saw no prompt.
- `version.py` is the single source of the version number (window title, updater).


## Version 2.0 — folder layout

- **Root holds only what you use:** `Setup.cmd`, `Run.cmd`, `README.md`. Code is in `src/orcpresser/`, documentation in `docs/`, tests in `tests/`, and your data in `data/`.
- **One setup script with a menu** (or arguments): install/repair/update, GPU on/off, safe start, self-tests. It replaces `SetupGPU.cmd`, `SetupCPU.cmd` and `SafeStart.cmd`.
- **Updates are clean:** your data lives in `data/`, which the zip never contains, so copying a new version over the folder can't touch it.
- **Automatic migration:** on first start (and in Setup → 1), `settings.json`, `learned/`, `fishing_notes.md` and the log move from the root into `data/`. Old program files from the flat layout go to `data/old_version_backup/` (safe to delete).
- **The GPU choice survives repairs:** Setup → 1 reinstalls DirectML if you had enabled it (before, it silently went back to the CPU runtime).
- No behaviour changes in the app itself.

## Version 1.9 — tabs, keys, Hold merge, fishing notes

- **Tabs:** REPEAT · HOLD · AUTO PRESSER · FISHING (EXP). Each tab shows only what it uses. Repeat: key, interval, press length. Hold: key, timed tick, duration (only when timed). Auto: everything recognition-related. Fishing: notes only.
- **HOLD merges Hold and Timed Hold.** Tick **Timed hold** to release after *Hold duration*; untick to hold until stopped (`\`, F8, or switching windows).
- **OUTPUT panel** (Repeat/Hold) shows the live state: `● HOLDING <key>`, elapsed / target seconds, press count for this run, and `Done — held 1.50 s` when a timed hold ends.
- **Key dropdown** (Repeat/Hold): LMB, RMB, MMB, Mouse 4/5, Space, Enter, Tab, Esc, Backspace, Shift/Ctrl/Alt (left and right), Caps Lock, arrows, Insert/Delete/Home/End/Page Up/Page Down, F1–F24 (except F8), numpad. You can also type a letter or digit, or an alias (`LButton`, `PgUp`, `XButton1`…). Arrow and navigation keys are sent with the "extended" flag games expect. The chosen key and the timed tick are remembered.
- **Timing precision:** manual modes now wake up exactly when the next press/release is due (was a fixed 25 ms tick). Repeat schedules no longer drift, and on Windows the timer resolution is set to 1 ms while the app runs. Measured in the test loop: timed 1500 ms → released after 1.503 s; repeat 100/50 ms → 100 ms average spacing, 53 ms presses.
- **FISHING (experimental):** a notes box with how RS:DW fishing works (net + rod minigame), written as a spec for a future bot. It lists the signals that still need screenshots. Edits are saved to `fishing_notes.md`; `fishing_notes_default.md` is the original.

## Version 1.8 — start-up and stuck-key fixes

- **No DirectX/COM work in the UI thread at start-up.** Since 1.5 the app imported `dxcam` (and `onnxruntime`) in the UI thread just to check they were installed; importing dxcam creates DirectX devices and initializes COM there. It is now checked without importing; GPU support is reported by the engine thread after loading.
- **Visible start-up progress.** The status line shows the current stage (`importing OCR libraries`, `loading OCR models`, `loading learned data`, `starting screen capture`) with seconds elapsed. If one stage takes over 45 s, the app says which one.
- **Zero point / safe start.** If the previous start never reached a ready engine, or you run **SafeStart.cmd**, the app starts clean: default window, speed options off, learned data neither loaded nor saved (the file is kept). The next normal start is automatic.
- **Unreadable learned data** is moved to `learned/learned.bad.npz` and the app starts with empty data instead of failing.
- **Stuck keys/buttons.** F8, closing the app, and exit now send key-up for every key used in the session **plus all mouse buttons**. If the previous run ended without closing properly (crash, console window closed), the next start sends those key-ups first.
- **`orcpresser.log`** (next to app.py, max 2 × 256 KB) records start-up stages, errors and warnings. Send it if something hangs.

## Version 1.7

- **Action timing** (under Last 5 reads): for each action, time from the capture of the first scan that saw the prompt to the moment the key was sent (LIVE) or the press decision was reached (PREVIEW, marked `prev`). Shows scans needed, scan time and source (OCR / memory / template), plus average, best and worst of the last 10. Repeat taps are not counted. Time before the first scan that saw the prompt cannot be measured.
- **Window size**: first launch opens at the size that shows every option (settings in two columns), placed at the right edge of the screen and clamped to the work area. Wide or maximized windows use two columns and hide the scrollbar; narrow windows stack the settings and show a scrollbar (mouse wheel works). **Last size, position and maximized state are restored** on the next launch (reset to the default if that position is on a disconnected monitor).
- Note: a maximized panel on the game's monitor covers the capture region, and scanning refuses to run while the panel overlaps it. Use a second monitor, or opacity 0 (minimize on focus loss).

## Version 1.6

- **Exclusions are remembered** after closing the app (`settings.json` next to the app, one section per game profile; saved 0.4 s after typing stops and on close).
- **GameProfile**: everything Dragonwilds-specific (actions, text patterns, hold rules, keycap thresholds, window match) now lives in `game_profile.py`. Other games derive from `GameProfile`; select with the `ORC_PROFILE` environment variable. Behaviour for Dragonwilds is unchanged.
- **FRAMEWORK.md**: catalogue of reusable features and a step-by-step guide for deriving other games. Updated with every release.

## Version 1.5 — speed & learning (section 03)

All options are **off by default**; enable them one at a time in PREVIEW and watch the Last 5 reads list and the Scan ms value. Timings below are from synthetic prompts on a 1-core Linux test container (full OCR there: ~220 ms); your PC will differ.

| Option | What it does | Synthetic result |
|---|---|---|
| Fast detection (extra, not from the list) | Text finding at native size, reading from a 2× upscale; key letter re-read separately | 190/192, ~105 ms |
| Recognition only | Finds the text by bright-pixel columns and skips the text-finding model; falls back to it when that fails. Not used while exclusions are set | 192/192, ~107 ms |
| Learned memory | Nearest-neighbour memory of prompt images labelled by OCR. Recalled prompts skip OCR entirely. Exclusions work (each sample keeps the name that was above it) | recall ~3 ms |
| Templates | Action wording and key letters learned separately, so they combine (Harvest + F). Not used while exclusions are set | ~12 ms |
| Single-scan confirm | 1 matching scan instead of 2 before the first press | halves reaction time; more exposure to one-frame glitches |
| DXGI capture | Desktop Duplication via dxcam; any problem falls back to mss for that scan. Status line shows `dxgi`/`mss` | not testable here |
| GPU · DirectML | Runs OCR on the GPU. Run **SetupGPU.cmd** first (swaps the ONNX runtime; **SetupCPU.cmd** reverts; rerunning Setup.cmd reinstalls the CPU runtime). Status line shows `GPU`/`CPU` | not testable here |

**Learned data** (`learned/learned.npz`, no pickle): a label is stored only after OCR read the same prompt twice, and learned paths only ever return labels OCR produced. Unknown or ambiguous images fall back to OCR. The **limit (MB)** caps storage (≈13 KB per memory sample; oldest samples of the most frequent prompt are evicted first, max 30 per prompt; near-duplicates are skipped). **CLEAR LEARNED** wipes it. If a UI scale/resolution change makes the learned paths miss, they simply fall back to OCR; clear and relearn.

**Crop advisor:** after 3+ recognized prompts, **SUGGEST CROP** proposes a capture box (union of recent prompts, including the name line when exclusions are set) and a text span, then opens the region editor: drag edges to widen/narrow, inside to move, outside for a new box; ENTER or double-click applies, ESC cancels. **SELECT REGION** uses the same editor. **Text span** (keycap widths left of the keycap, default 20) limits how far left the text is searched.

Preview colours: green = OCR, blue = learned, red = excluded. `[M]`/`[T]` in the reads mark memory/template results.

Option 11 (game data via a UE4SS mod) is a separate plan document in the Dragonwilds Google Drive folder.

## Version 1.4

- **PREVIEW / LIVE** buttons replace START and the *Preview only* checkbox. Pick one to start: PREVIEW detects without pressing, LIVE sends keys. Clicking the active button stops; clicking the other one switches. `\` starts/stops with the last one you picked (manual modes always run LIVE; PREVIEW is Auto-only and dimmed there).
- *Repeat persistent tap prompts* sits directly under Hold duration, and is disabled outside Auto.
- **Click-off**: clicking anywhere in the panel outside a text field removes keyboard focus from it; Enter or Escape in the Exclude field does the same.
- **Last 5 reads** above Resource consumption: timestamp and reading for the last five *distinct* results (consecutive repeats only refresh the time). `▶` marks a scan that sent a key. Cost is a few string operations per scan and a label update only on change.

## Version 1.3

- **Faster scans.** OCR now runs only on strips around detected keycaps instead of the whole region, the unused text-angle classifier is off, and RapidOCR no longer inflates every input to a 736 px short side. The keycap mask uses OpenCV channel ops. A missed keycap letter gets a second, direct read of the keycap interior. In the Linux test container (1 CPU core) average scan time on synthetic prompts fell from ~700 ms to ~200 ms with equal or better recognition; your PC will differ.
- **Scan gap** lowered from 300 ms to 120 ms (`SCAN_GAP` in app.py). Still one scan in flight.
- **Exclude** box: comma-separated terms, e.g. `Stone,Cabbage`. A prompt is skipped if a term appears (case-insensitive, at a word start: `stone` matches `Stones`, not `Limestone`) in its row or in text up to ~4 keycap heights above it, where an object name is expected. Excluded prompts show a red box and an "Excluded" line in the preview. Other eligible prompts in the same view still work.
- **Opacity 0** minimizes the panel when it loses focus (a 0 % topmost window would still block clicks). Restore it from the taskbar.
- **Auto mode uses ORDERS timings.** Hold duration = tap length (20–1000 ms); Repeat interval = start-to-start spacing between automatic taps (≥ 50 ms, ≥ hold + 10 ms). With *Repeat persistent tap prompts* on, a confirmed tap prompt repeats at that interval, driven by the clock rather than scan arrival, but only while the prompt was confirmed within the last 0.5 s. Prompts marked Hold still hold (up to 15 s) and never repeat.


## Versions 1.1–1.2

Version 1.1 removes the pointer-hover stop condition. Hovering an unfocused panel keeps output running and retains the selected unfocused opacity. Clicking/focusing the panel takes focus away from the game, which stops output and releases held input. F8, stop, changed settings and the other detection checks continue to work. Mouse automation can itself click the panel if the pointer is over it, giving the panel focus; this also stops output. The separate capture-overlap check still requires the panel to stay outside the selected OCR region.

Harvest is now available and enabled by default. It taps the displayed key, or holds if the recognized row includes Hold. Settings have a scrollbar so the extra action does not hide the opacity control.

Version 1.2 adds **Fill Compost Bucket** to the allowed actions. Enable its checkbox to use it (off by default, like Fill Watering Can). It reads the displayed key and taps it, or holds when the recognized row includes Hold. No dependency changes.


---

# Verification log

What was tested for each version, and how. Newest at the bottom.

- Python syntax compilation: passed for app.py, engine.py, vision.py.
- Automated controller and detection association checks: 14 passed, including unfocused hover continuity, panel-focus release, and Harvest allowlist/key/hold association.
- Actual RapidOCR inference on five synthetic UI samples: Collect/E, Collect Water/E, Fill Watering Can/F, Uproot/E, Siphon [Hold]/E all recognized with the expected tap/hold classification.
- Windows GUI, global input, focus behavior and Dragonwilds capture: not runtime-tested in this Linux environment.
- The gameplay screenshots shown in the conversation were used to define prompt vocabulary; synthetic tests do not establish recognition accuracy on their scenery.
- UI styling is implemented in native Tk canvases. A rendered UI check was unavailable because no display server was available.

Use the built-in Preview only option for the first live session.

## Version 1.1

Synthetic RapidOCR samples for Harvest/E and Harvest [Hold]/E were recognized with the expected tap/hold behavior. The focus regression uses mocked window APIs; actual Windows focus and GUI rendering remain untested here. No dependency changes.

## Version 1.2

Added Fill Compost Bucket association checks for mixed case, tap/hold handling, detected F key and disabled-action rejection. All 14 tests pass. Capture/OCR scheduling remains at a minimum 300 ms between job starts, with only one job in flight. No Windows or real compost prompt runtime test was performed.

## Version 1.3

- 22 unit tests pass (Linux, mocked Windows APIs): exclusion parsing/word-start matching, name-line context, auto repeat at the configured interval and tap length, repeat stop on missing/stale prompts, holds never repeat, non-overlapping OCR strips, opacity-0 minimize once per focus loss.
- Real RapidOCR on 48 synthetic prompts (8 labels × keys E/F/R × 2 noisy backgrounds): 1.2 pipeline 47/48, avg ~700 ms; 1.3 pipeline 48/48, avg ~200 ms (1-core container). Exclusion of a name line above the prompt verified on synthetic frames.
- UI rendered with --visual-preview under Xvfb. Windows focus/minimize, input and real Dragonwilds captures: not tested here.

## Version 1.4

- 27 unit tests pass: PREVIEW/LIVE start/stop/switch, PREVIEW rejected in manual modes, `\` uses last choice, click-off focus handling (overlay excluded), last-5 reads dedupe/cap/▶ marker. Detection code unchanged from 1.3.
- UI rendered with --visual-preview under Xvfb at 920×840; chart and preview box reduced to fit the reads list. Windows rendering not checked.

## Version 1.5

- 38 unit tests pass (no OCR model needed): memory recall on new backgrounds, no guessing of unseen prompts (Collect F, Collect Water, Harvest [Hold], Uproot) by memory or templates, template composition, exclusions via stored names, allowlist, size-limit eviction, persistence roundtrip, glyph filter, single-scan confirm.
- Real RapidOCR, 192 synthetic prompts (8 labels × E/F/R × backgrounds × font sizes): full 192/192 ~220 ms; fast detection 190/192 ~105 ms; recognition only 192/192 ~107 ms.
- Learned paths with an adversarial learning order (Collect/Harvest/Siphon/Uproot learned first), 192 prompts: templates 191/192 (~12 ms), memory 191/192 (~3 ms), both 191/192. The single miss in each is an OCR "no result" on a very bright background; no wrong action was produced in any sweep.
- Worker integration test with a fake capture: OCR → learning after two agreeing reads → memory recall; clear; data saved on shutdown.
- Tried and rejected: int8 dynamic quantization (full: recognition broke, 0/48; MatMul-only: ~5 % faster).
- Not testable here: DXGI capture (dxcam), DirectML GPU, Windows region editor, real Dragonwilds prompts.

## Version 1.6

- 44 unit tests pass, incl. Dragonwilds classification/hold/window rules unchanged after moving them into `Dragonwilds(GameProfile)`, a derived test profile, profile loading by name, per-profile settings roundtrip, corrupt settings file → defaults, persist batching.
- Real UI (visual preview under Xvfb): exclusions typed, app closed, app reopened → `Stone,Cabbage` restored.
- OCR sweep after the refactor: full 192/192, fast detection 190/192 (same as 1.5).

## Version 1.7

- 53 unit tests pass: reaction meter (first-seen→press, repeats not recounted, reset per sighting, history cap), window placement (restore saved, off-screen/bogus → fit, clamp to small work area, maximized state saved with the normal geometry).
- Visual preview under Xvfb (1920×1080): first launch 1392×858, two columns, no scrollbar; resized to 1000×700 → stacked with scrollbar; 1920×1030 → two columns, no scrollbar; close/reopen restores geometry.
- Not checked on Windows: DPI scaling of the natural size, `zoomed` restore, work-area query.

## Version 1.8

- 60 unit tests pass (new: dxcam not imported by the availability check, corrupt learned data → empty + reported, safe-mode learner never writes, stall flagged once, progress display cannot break tick, release_all covers used keys + mouse buttons).
- Real app loop under Xvfb with a fake Windows layer: normal start ready in ~0.4 s engine time; corrupt `learned.npz` → moved to `learned.bad.npz`, engine ready; simulated 120 s stall in model loading → progress shown, stall message at 45 s naming the stage; next start → SAFE START, engine ready.
- Not reproduced here: the original Windows hang and the stuck left mouse button (Linux cannot run the Windows parts). The fixes target the most likely causes; the log will pin down the actual one if it recurs.

## Version 1.9

- 69 unit tests pass (new: key aliases/extended flags/F-keys/reserved F8, every dropdown entry resolves, constant vs timed hold, repeat schedule without drift under irregular 13.7 ms wake-ups, no catch-up burst after a stall, per-run press counter).
- Real app loop under Xvfb with a fake input layer timestamping every key event:
  - Tabs: Repeat → key, interval, press length, target, output; Hold → key, (duration only when timed), target, output; Auto → recognition sections only; Fishing → notes only.
  - Timed hold 1500 ms → released after 1.503 s; 300 ms → 0.302 s. Constant hold → held until stopped (2.0 s).
  - Repeat 250/60 ms → spacing 248–255 ms, presses 64 ms. Repeat 100/50 ms → 95–102 ms spacing (100 ms average), 53 ms presses. Before the fix: 265 ms / 80 ms.
  - F8 chosen as key → refused (reserved).
- Not checked on Windows: real SendInput of mouse X buttons and extended keys, timeBeginPeriod effect, ttk dropdown look.

## Version 2.0

- Unit tests via `python -m unittest discover -s tests -t .` (also Setup.cmd → 5): all pass, incl. new layout tests. Migration moves `settings.json`, `learned/`, notes and log into `data/` without overwriting newer data and is idempotent. Old flat-layout program files go to `data/old_version_backup/`; `Run.cmd`, `README.md` and user data are never touched.
- The app runs from `src/orcpresser/` under Xvfb (visual preview); the data folder is created at the root.
- `Setup.cmd` / `Run.cmd` are Windows batch files and were not executed here (Linux). The menu and argument logic was checked by reading only.

## Version 2.1

- 94 unit tests pass (new: updater zip versions/mirroring/requirements detection/archiving; benchmark plan, identical and net-zero camera path, phase timing, measured-window only, recommendations incl. wrong-label → avoid and no-prompt → no suggestions, abort returns camera, save/load).
- End-to-end in the real app loop with real OCR, a fake input layer and a simulated game whose view follows the app's mouse moves (the prompt slides and leaves the view as the camera turns). Test 4 configs × (8 s static + 8 s camera): finished in 80 s; 1153 camera moves, max ±300 px, final offset 0 px; no key was sent. Results: Baseline 232 ms static scans / 506 ms time-to-decision while moving; Fast detection 105 / 234 ms; Learned memory 3.7 / 141 ms; detection and agreement 100 % static. → ★ Fast detection, ★ Learned memory, highlighted in AUTO → 03.
- Found and fixed during that test: a run where the panel covered the capture region measured nothing (now aborts with a message); tests used the Auto allowlist (now all actions); suggestions were given when Baseline saw no prompt (now none).
- Not tested here: real Dragonwilds camera response to `mouse_event` moves (sensitivity, raw input), Update.cmd self-replacement on Windows.

## Version 2.2

- All unit tests pass (new: clean-up candidates never include settings, learned data, notes, test results or the current log; the updater keeps exactly the last 2 updates).
- Dead-code scan (vulture, ≥ 60 % confidence) is clean apart from false positives: a Tk hook attribute, a profile class found by name, the main-block variable.
