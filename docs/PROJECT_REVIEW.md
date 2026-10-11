# Project review — October 2026 (Research POC, branch `experimental`)

> **Status: project review.** Findings and recommendations at the time of writing; verify against current code before acting on an item. Items marked **done** were implemented in the same change set as this document.

Scope: the whole repository as of commit `635d986`, with emphasis on the Fishing bot (`fishing.py`, `fishing_capture.py`, `fishing_ui.py`), the Scout / Cheat Engine research path (`scout.py`, `scout_lab.py`, `ce_table.py`, `pointer_chain.py`, `internal_telemetry.py`, `research_setup.py`, `scout_analysis.py`, `tools/cheat-engine/orcish_scout_ce.lua`) and the user workflow in `docs/RESEARCH_DATA_GUIDE.md`.

Verification used for this review: `python -m unittest discover -s tests -t .` on Windows 10 with the project virtual environment (245 tests pass after the changes), a Tk build of the full UI in `--visual-preview` mode, and reading. No live Dragonwilds or Cheat Engine session was run; everything that touches the game or Cheat Engine is marked *unverified live* below.

## 1. Overall verdict

The architecture is sound and unusually disciplined for a helper of this kind: capture workers only capture, one UI thread owns decisions and input, every input path goes through the `WinIO` guard with F8 / focus-loss / watchdog release, controllers are pure Python with state-machine tests, and research data is recorded immutably with hashes. The Fishing controller is conservative in the right places (two-sample confirmation on distinct stamps, REEL hysteresis, bounded `BITE_PENDING`, re-arm instead of stop in Bot 101). The Scout research path has the right shape (Cheat Engine finds, bridge streams, analyzer correlates, Orcish reads survivors read-only) and the promotion gates are written down.

The weak points were (a) the amount of manual work between "I can fish" and "I have a memory candidate", (b) a few places where documentation and code disagreed, (c) timing quality of the research data (clock resolution and bridge ingest delay), and (d) no code-level seam for the next data sources (process hooks) beyond the JSONL bridge. The change set accompanying this review addresses (a)–(d); the remaining items are listed as recommendations.

## 2. Fishing bot: logic review

What the controller does well:

- Evidence is counted per *distinct* capture stamp (`text_stamp`, `active_stamp`, `pull_stamp`, `reel_stamp`), so cached OCR cannot double-confirm. Tests cover this.
- REEL uses an enter/stay/exit hysteresis band (enter ≥ 0.44 twice, exit ≤ 0.30 twice, in-between keeps the state), which is the correct shape for a noisy prompt at night.
- `BITE_PENDING` is time-bounded and never presses anything on STOP disappearance alone.
- Bot 101 treats alt-tab, stale capture, fight timeouts and results as *re-arm* events; only depleted/bait/F8/STOP end the session. This matches how the game is actually played.
- Blue→red swap is immediate once blue has confirmed the direction; initial red still debounces; sustained red probes the opposite key after `red_probe_seconds`. This avoids both oscillation and holding a wrong key for seconds.

Findings:

| # | Finding | Evidence | Recommendation |
|---|---|---|---|
| F1 | **Docs and UI said PULL L/R drives A/D; Bot 101 ignores PULL direction.** `fishing_ui.py` sets `use_pull_direction = mode != '101'`; the controller then uses BAR feedback only, and PULL captions are presence evidence. `FISHING.md` said both things in different sections, and the panel caption claimed PULL drives A/D in every mode. | `fishing_ui.start()`, `FishingController.observe()`, `test_101_can_treat_pull_labels_as_presence_only` | **Done:** `FISHING.md` and the panel caption now state the per-mode behavior. |
| F2 | Detector thresholds are split across modules: REEL presence 0.42 in `fishing_capture.py`, REEL hysteresis 0.44 / 0.30 and PULL confidence 0.55 in `fishing.py`, PULL resolver 0.42 / 0.14 / 1.28 in `fishing_capture.py`. Tuning one without the other is easy to get wrong. | grep for the literals | Collect them in one `FishingThresholds` dataclass on `FishingConfig`, and write the values into the session manifest so a recording can be replayed with the thresholds that produced it. |
| F3 | `stable_color` / `previous_stable_color` are created in `start()` and `_rearm()`, not in `__init__`; `observe()` uses `getattr(self,'stable_color','unknown')` to cope. | `fishing.py` | Initialize them in `__init__` and drop the `getattr`. Cosmetic, but it is the kind of thing that hides a bug later. |
| F4 | The 1.5 s `BITE_PENDING` expiry and the 1.5 s "fight signal disappeared" window are literals inside `tick()` / `observe()` while similar values live on `FishingConfig`. | `fishing.py` | Move them to `FishingConfig` with validation like the others. |
| F5 | `observe()` is ~200 lines and mixes evidence bookkeeping with per-state transitions. Tests are good, but adding a signal (for shadow mode) will touch many lines. | `fishing.py` | Split into `_update_evidence(o, now) -> Evidence` and one `_step_<STATE>(evidence, now)` per state. Pure refactor; the existing tests are the safety net. |
| F6 | **Timestamps have 15.6 ms resolution on the shipped runtime.** `Setup.cmd` installs Python 3.12, where `time.monotonic()` is `GetTickCount64()` on Windows (verified: `time.get_clock_info('monotonic').resolution == 0.015625`). The capture loop targets 50 ms and OCR latency is 30–100 ms, so `fresh_ms`, `latency_ms` and every correlation Δ are quantized to 15.6 ms steps. Python 3.13+ switched to `QueryPerformanceCounter`. | measured on this machine | One focused change: a `clock.py` with `now = time.perf_counter` used by *all* producers (app, fishing capture, Scout recorder, Scout Lab, bridges), so the timeline stays on one clock. Do not mix the two clocks. |
| F7 | `FishingCapture` grabs each region separately: BAR every 50 ms, REEL/PULL L/PULL R every 100 ms, STOP every 150 ms, OCR crops every 400 ms, a context image every 500 ms, each as its own `mss` BitBlt. | `fishing_capture.capture()` | Measure before changing: add a small fishing capture micro-benchmark (`bench.py` only covers Auto Presser). If the union rectangle of the calibrated regions is less than ~2× the summed area, one grab per tick plus slicing is cheaper; otherwise keep per-region grabs. |
| F8 | Each `FishingCapture` creates its own `RapidOCR` instance (model load of a few seconds). Bot 101 restarts the capture after a worker error, which reloads the models during a live session. | `FishingCapture.read_text()`, `fishing_ui.tick()` error path | Keep one lazily-created OCR engine per process (only one fishing OCR worker exists at a time) so restarts are instant. |
| F9 | Dead code: `_longest_run()` in `fishing_capture.py` is unused; `spot_candidate()` is documented as legacy and only kept for research. | grep | Delete `_longest_run`; keep `spot_candidate` only while the SPOT research is still referenced. |

Verdict: no logic defects found that would send a wrong input; the recommendations are about maintainability and measurement quality.

## 3. Data gathering (Cheat Engine, Scout, analyzer): strategy review

The strategy is right: vision is the reference, memory values are candidates until they agree repeatedly, pointer chains make survivors restart-proof, and promotion is a manual gate. The concrete pipeline (Lua bridge polls the table every 100 ms and writes diffs → `JsonlBridgeProvider` tails the file → Scout records on one timeline → `scout_analysis.py` correlates with STOP/PULL/REEL/state landmarks) works and is tested at every Python seam.

Findings:

| # | Finding | Evidence | Recommendation |
|---|---|---|---|
| D1 | **Bridge events were timed at ingest, not at the producer.** Cheat Engine flushes every 100 ms and Orcish polls the file every 50 ms, so a value change could appear up to ~150 ms late. The Lua bridge already writes `producer_time`; the analyzer ignored it, biasing every median Δ toward "lags vision". | `JsonlBridgeProvider._emit()`, `_internal_summary()` | **Done:** `align_producer_clock()` estimates the constant clock offset per provider (least-delayed ingest) and matches on producer time; the report shows the offset and the maximum ingest delay. |
| D2 | **The manual part (Cheat Engine value scanning) was the whole cost.** Part C of the guide is a 7-step table the user must drive by hand per round, while Orcish already knows the phase from vision. | `RESEARCH_DATA_GUIDE.md` Part C2 | **Done (experimental, unverified live):** scan assistant. `scan_assistant.ScanPlanner` turns the controller's state timeline into a bounded plan (`first` unknown value once a phase settles, `next changed` after the phase changes, `next unchanged` twice per stable visit, `dump` when ≤ 64 survive), writes it to `data\telemetry\cheat_engine_commands.tsv`, and the Lua bridge executes it with a private `memscan`, replying `scan_result` / `scan_dump` on the stream. Survivors are added to the table so the bridge streams them from then on. Opt-in checkbox in SCOUT LAB. |
| D3 | Importing a table into Orcish was a separate manual step with a file dialog, and candidates imported under the wrong domain were silently not sampled. | `ScoutLabPanel.import_ce_table()`, `ScoutLabSession` domain filter | **Done:** auto-import of `data\cheat-engine\OrcishScout.CT` at session start under the active domain (default on, opt-out), plus a **RELOAD OrcishScout.CT** button; `Setup.cmd → D` explains missing candidates. |
| D4 | `Setup.cmd → 7` installs five tools (Frida, UE4SS, x64dbg, ReClass.NET, Windows Performance Toolkit); only Cheat Engine matters for the current focus and UE4SS is parked. New users read this as required. | `Install-TelemetryToolkit.ps1` | **Done:** `Setup.cmd → D` (research data check: creates the table, checks stream, candidates and latest session, prints the next step; no downloads) and `→ R` (analyze the latest session). Consider making option 7 default to `-SkipUE4SS -SkipX64dbg -SkipReClass -SkipWPT` in a later change. |
| D5 | When `OpenProcess` failed, `backend_error` was written to `memory.jsonl` on every 100 ms tick until the 20 MiB session cap. | old `ScoutLabSession._memory()` | **Done:** `MemoryCandidateSource` opens the backend lazily, logs one error per distinct failure, retries every 5 s. |
| D6 | **The 20 MiB session cap is shared by all streams and ends recording silently.** A Fishing 101 vision event is ~600 B every 50 ms (≈12 KB/s) plus memory candidates at 10 Hz; a LIVE session hits the cap after roughly 25–30 minutes, after which `ScoutRecorder.event()` returns `False` and nothing else is written, including the end-of-session summary. | `scout.py` `MAX_BYTES`, `fishing_ui.tick()` event sizes | Raise the cap to a per-stream budget (vision the largest), rotate `vision.jsonl` into numbered parts, and show "Scout recording stopped: cap reached" in the HUD rail. Until then, keep research sessions under ~25 minutes. |
| D7 | Promotion gates are stated in three documents with slightly different numbers (20+ transitions / 3+ launches in `SCOUT_CANDIDATES.md`; 5 sessions / 3 restarts / day+night / 2 spots in `RESEARCH_DATA_GUIDE.md`; roadmap). | the three files | Keep the checklist in `RESEARCH_DATA_GUIDE.md` as the single list and link to it from the other two. |
| D8 | `ce_table.py` reverses Cheat Engine's offset order (index 0 applied last). This matches the `.CT` format, but it has never been confirmed against a live table with a 2+ level chain. | `test_ce_table.py` only | The guide's D2 step 4 ("compare one value with Cheat Engine") remains the required first-time check. |
| D9 | There was no agreement view: the analyzer correlated *transitions* with landmarks, but could not say "value 2 only ever appears in WAIT_BITE". | `scout_analysis.py` | **Done:** every `fishing_decision` now carries the latest signals (`details.signals`), and the report has a **Shadow agreement** section with per-state value counts and a purity score. |

## 4. Optimization points elsewhere

| # | Area | Observation | Recommendation |
|---|---|---|---|
| O1 | `app.py` (1,337 lines) | Mixes `WinIO`, the Tk shell, the Auto Presser worker, Stats, overlays and Scout plumbing. Fishing, Aim and Scout already live in their own modules. | Extract `WinIO` and the Auto Presser worker/drain pair into modules; keep `app.py` as the shell. Do it as its own PR (AGENTS.md asks for no unrelated `app.py` churn). |
| O2 | Scout recorder | `event()` does `json.dumps` + `write` + `flush` per event under a lock, from several threads. Fine at current rates, but `flush()` per line is the expensive part. | Flush on a 250 ms timer or every N lines; keep the lock. |
| O3 | Tests | 245 tests in ~2.5 s; the UI is covered only by string-contract tests. | Add one Tk smoke test that builds `App(root, visual=True)` and ticks the panels once (Windows CI runner has Tk). The review used exactly that as a manual check. |
| O4 | Install | A `.venv` per extracted folder; the Research POC and Standard editions cannot share one. | Already on the roadmap (self-contained build). No action now. |
| O5 | `tools/ue4ss` and Frida | Both parked, but their UI checkboxes remain visible in SCOUT LAB. | Collapse them under an "advanced / parked" expander so the Cheat Engine path is the only visible one for new users. |

## 5. Documentation mismatches found

- `FISHING.md`: PULL L/R described as the preferred A/D source *and* as presence-only (see F1). **Fixed.**
- `roadmap.md` listed "pointer-chain memory watches" as the *next* step although `pointer_chain.py` and the Cheat Engine import are implemented. **Fixed:** the next step is now shadow mode.
- `README.md` Setup menu did not know options D / R. **Fixed.**
- `docs/README.md` map: **added** `GAME_SIGNALS.md` and this review.

## 6. What this change set adds (summary)

- `src/orcpresser/game_signals.py`: `SignalSample`, `SignalSource`, `MemoryCandidateSource`, `CallbackHookSource`, `SignalHub`, `infer_role()`. `ScoutLabSession` now routes memory candidates and bridge events through one hub and exposes `snapshot()`. Event formats on disk are unchanged.
- `src/orcpresser/scan_assistant.py` + Lua bridge commands: Fishing-state-driven Cheat Engine scans (opt-in; Lua side unverified live).
- SCOUT LAB: auto-import / reload of `OrcishScout.CT`, data-source status line, ANALYZE LATEST SESSION, OPEN REPORTS, scan-assistant controls.
- `research_setup.py doctor` / `report`, `Setup.cmd → D / R`.
- Analyzer: producer-clock alignment, shadow agreement, scan-assistant section.
- Cheat Engine bridge: F9 writes a `mark` on the stream (no Lua console needed).
- Docs: `GAME_SIGNALS.md`, guide/README/roadmap/changelog updates, `FISHING.md` fix.
- Tests: 28 new tests (signals, scan planner/assistant, analyzer sections, research doctor).

## 7. Suggested order of the next steps

1. Run one real session with the scan assistant on (Cheat Engine open, Fishing PREVIEW) and confirm the Lua side: `scan_result` replies appear in `Setup.cmd → D`, survivors land in the table. Fix the Lua API details if Cheat Engine disagrees; everything on the Python side is tested.
2. Record 5+ sessions with a saved table; read the **Shadow agreement** and **Candidate ↔ landmark** sections; write the value → meaning table into the research log.
3. Implement shadow mode in the controller (`GAME_SIGNALS.md` §"From signal to control", step 3) behind a config flag, logging disagreements only.
4. Clock change (F6), threshold consolidation (F2), session-cap handling (D6).
5. Only then: promote one signal (phase) with vision fallback and invalidation tests.
