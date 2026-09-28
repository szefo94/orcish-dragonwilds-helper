# Research data guide: Fishing vision + Cheat Engine memory

> **Status: research workflow (Research POC edition).** This is a hands-on procedure for collecting evidence. Nothing collected here changes how the Fishing bot behaves; memory values are recorded and compared only. Promotion into live control follows the gates in [SCOUT_CANDIDATES.md](SCOUT_CANDIDATES.md) and [../roadmap.md](../roadmap.md).

## The idea in one picture

```text
             what you see                         what the game knows
  OCR / vision (Fishing bot, Scout)          memory (Cheat Engine, Orcish reads)
  STOP, BAR red/blue, PULL, REEL, result     phase, pull direction, reel allowed, ...
                 \                                   /
                  +---- same Scout session timeline -+
                                   |
                     scout_analysis.py lines them up:
             "memory value changed 180 ms before vision saw PULL, 14 of 15 times"
```

Vision is the **reference** (it is what the bot already trusts and what the player sees). Memory values are **candidates** until they agree with vision repeatedly. The goal is one or two memory signals for Fishing (first *phase*, then *pull direction*) that later help vision where it is weak, for example REEL at night.

There are four activities. Do them in this order the first time:

| Part | What you do | Manual effort |
|---|---|---|
| [A](#part-a--one-time-setup) | One-time setup | Once |
| [B](#part-b--record-good-vision-sessions) | Record Fishing sessions (vision/OCR reference) | Just fishing |
| [C](#part-c--find-memory-candidates-in-cheat-engine) | Find memory candidates in Cheat Engine | **High**, once per signal and after game updates |
| [D](#part-d--record-memory-next-to-the-bot) | Record memory next to the bot | Low: open a table, or nothing after import |
| [E](#part-e--read-the-results) | Read the analyzer report | A few minutes per session |

---

## Part A — one-time setup

1. **Install Orcish (Research POC).** Extract the Research POC ZIP into its own folder, run `Run.cmd` once (it installs Python packages), then close the app.
2. **Run `Setup.cmd` → 7.** Dragonwilds can be open or closed. This installs/checks the research tools and creates:
   - `data\cheat-engine\OrcishScout.CT`: your Cheat Engine table (created once, never overwritten);
   - `data\telemetry\`: where the Cheat Engine stream is written.
   Cheat Engine itself: if it is missing, the official download page opens; install it normally.
3. **Calibrate Fishing** as described in [FISHING.md](FISHING.md): bind the game, then select **BAR**, **REEL**, **STOP** and ideally **PULL L/R** and **RESULT**. Check them in **PREVIEW** first. Good calibration matters twice here: it drives the bot *and* it produces the landmarks that memory is compared against.
4. **Check SCOUT LAB settings once** (tab SCOUT LAB):
   - **Run independent Scout probes alongside Auto / Fishing / Aim**: on (default). Without it, Fishing records no memory or Cheat Engine data.
   - **Read JSONL bridges (UE4SS + Cheat Engine)**: on (default).
5. **Run `Setup.cmd` → 8** to confirm: the Cheat Engine starter table is `[OK]`; the stream shows `[MISS] no data yet` until Part D.

---

## Part B — record good vision sessions

Every time you start Fishing (PREVIEW, Record manual test or LIVE), Orcish automatically opens a Scout session in `data\scout_sessions\<date>-<id>\`. You do not need to press anything extra.

What a Fishing session contains:

| File / folder | Content |
|---|---|
| `controller.jsonl` | Bot states (`WAIT_CAST`, `WAIT_BITE`, `BITE_PENDING`, `FIGHT`, `REEL`, ...) and decisions, key holds |
| `vision.jsonl` | `fishing_observation` events: STOP, PULL L/R, REEL, BAR scores, OCR text per region, timings |
| `memory.jsonl` | Memory candidates read by Orcish, about 10 times per second, and every value change (`candidate_transition`) |
| `process.jsonl` | Process stats and **game-internal events** (the Cheat Engine stream lands here) |
| `fishing_frames/` | Context screenshots of the calibrated regions and frequent BAR crops |
| `manifest.json`, `summary.json` | Session metadata |

`data\fishing_sessions\` additionally holds the older manual-recording format (Record manual test): JSONL plus about one crop set per second, capped at 5 minutes / ~100 MiB.

**Two ways to fish for data:**

- **PREVIEW + fish manually**: the bot observes and logs what it *would* do but sends no input. Best while you are also clicking around in Cheat Engine.
- **LIVE (Fishing 101)**: the bot fishes; you watch. Best for many clean rounds once memory candidates exist.

**Habits that make sessions useful:**

- Keep the camera and player still during a session; recalibrate after moving (NEW SPOT / REACQUIRE).
- Aim for **10–20 complete rounds** per session, including failures (escaped, startled) as well as catches.
- Vary conditions **across** sessions, not within one: day and night, two or three spots, after a game restart.
- Keep a short personal log next to your data, for example `data\research_log.md` (never committed): date, session folder name, spot, day/night, what you were testing, anything odd.

Check one session right away:

```bat
.\.venv\Scripts\python.exe src\orcpresser\scout_analysis.py --latest
```

The report is written to `data\scout_reports\<session>.md` (and `.json`). If the Fishing state transitions and vision events look sane there, the reference layer is good enough to compare memory against.

---

## Part C — find memory candidates in Cheat Engine

This is the manual, iterative part. You do it once per signal, and again when a game update breaks an address.

### C1. Attach

1. Start Dragonwilds and load into the world near water.
2. Open `data\cheat-engine\OrcishScout.CT` in Cheat Engine. Answer **Yes** when asked to run the table's Lua script. The bridge attaches to the game by itself (`RSDragonwilds-WinGDK-Shipping.exe` for Game Pass, `RSDragonwilds-Win64-Shipping.exe` for Steam). If it does not, use the computer icon → pick the Dragonwilds process. If the process cannot be opened, start Cheat Engine as Administrator.

### C2. Scan for the fishing phase

The phase is most likely a small integer (an enum) that steps through a few values as fishing progresses. You don't know the values, so scan by *change*:

| Step | In game | Cheat Engine |
|---|---|---|
| 1 | Idle, rod equipped, not fishing | Value type **4 Bytes** (try **Byte** later), Scan type **Unknown initial value** → **First Scan** |
| 2 | Still idle | **Unchanged value** → **Next Scan** (repeat 2–3 times over a few seconds) |
| 3 | Cast; waiting for a bite (STOP Fishing visible) | **Changed value** → **Next Scan** |
| 4 | Still waiting | **Unchanged value** → **Next Scan** |
| 5 | Bite / fight starts | **Changed value** → **Next Scan** |
| 6 | Round ends (catch or fail), back to idle | **Changed value** → **Next Scan** |
| 7 | Idle again | **Unchanged value**, a few times |

Repeat steps 3–7 over several rounds. Tips:

- Once candidates drop below a few thousand, add a filter: **Value between 0 and 20**. Enums are small.
- An address that returns to **the same value** every time you are idle, and to another fixed value every time you wait for a bite, is a strong candidate. After a few rounds you can switch to **Exact value** scans using those numbers.
- Addresses that change constantly (timers, animation, positions) fall out through the *Unchanged* scans; keep doing them.
- *Pause the game while scanning* (scan options) keeps values still, but avoid it in multiplayer sessions.

When you are down to a handful of addresses, double-click them to add them to the table. **Name each one descriptively**: the description becomes the name in every report, and a name containing a role (`fishing phase`, `pull direction`, `reel allowed`, `tension`) is mapped to that role on import.

### C3. Other Fishing signals (after phase works)

| Signal | Likely form | How to narrow |
|---|---|---|
| **pull direction** | small int (0/1/2) or signed (-1/0/1) | During the fight: *Changed* when PULL switches side, *Unchanged* while it stays |
| **reel allowed** | 0/1 (byte or 4 bytes) | *Changed* when REEL appears and disappears, *Exact value* 1 while visible |
| **tension / progress** | Float | Value type **Float**, *Increased* / *Decreased value* as the BAR moves |

### C4. Make the address survive a restart (pointer scan)

Game objects such as the fishing component live in memory that moves on every launch, so the raw address you found is only valid for this game run. You need a **pointer chain** from the game module:

1. Right-click the candidate in the table → **Pointer scan for this address**. Defaults are fine to start (max level 5). Save the result file when asked.
2. **Restart the game**, get back to the same fishing state, and find the candidate again with a few quick scans (now you know its values, so *Exact value* is fast).
3. In the pointer scanner window: **Pointerscanner → Rescan memory**, enter the **new** address. Paths that no longer lead to it are removed.
4. Repeat restart + rescan two or three times. Prefer surviving paths with a base of `RSDragonwilds-...exe+offset` and few levels.
5. Double-click a surviving path to add it to the table, give it the same descriptive name, and **save the table** (`File → Save`, keep it in `data\cheat-engine\`).

Records that are Auto Assembler scripts, strings, byte arrays or based on symbols/AOB labels are not imported; plain module- or address-based numeric records with hex offsets are.

---

## Part D — record memory next to the bot

There are two ways; both put memory on the same timeline as Part B.

### D1. With Cheat Engine open (stream)

Use this while candidates are still changing (Part C in progress):

1. Game running, `OrcishScout.CT` open in Cheat Engine with its script running.
2. Start Fishing in Orcish (PREVIEW or LIVE).
3. Every table record's value change is written to `data\telemetry\cheat_engine.jsonl` (checked every 100 ms) and recorded into the Fishing session's `process.jsonl`.
4. Mark moments from Cheat Engine's Lua console (`Table → Show Cheat Table Lua Script` is for the table script; use **Memory View → Tools → Lua Engine** for a console): `OrcishScoutCE.mark("bite looked late")`. Marks land on the same timeline.
5. `Setup.cmd` → 8 shows the stream as `[OK] Cheat Engine stream: N lines, last 'property_change' Xs ago`.

Prefix a record's description with `-` to leave it out of the stream. `OrcishScoutCE.stop()` / `OrcishScoutCE.start()` pause and resume it.

### D2. Imported into Orcish (no Cheat Engine needed)

Use this once a pointer chain survives restarts:

1. SCOUT LAB → in the **Semantic candidate** row set the domain to **fishing** → **IMPORT CE TABLE** → choose your `.CT`.
2. The status line says how many records were imported and which were skipped and why.
3. From now on every Fishing session reads these candidates by itself (about 10 per second) into `memory.jsonl`; Cheat Engine can stay closed.
4. **First time only: check the conversion.** With Cheat Engine still open, fish one round and compare a value Scout recorded (in the report, `values=[...]`) with what Cheat Engine shows for the same record. If they differ, the pointer offset order is wrong. Report it, it is a one-line fix.

You can also enter a chain by hand in the candidate field, in Cheat Engine notation with `0x` on every number:

```text
[[RSDragonwilds-WinGDK-Shipping.exe+0x4A1230]+0x10]+0x88:u32
```

Types: `u8 u16 u32 i32 u64 i64 ptr f32 f64`. See [SCOUT_CANDIDATES.md](SCOUT_CANDIDATES.md#pointer-chains). To list what an import would produce without the UI:

```bat
.\.venv\Scripts\python.exe src\orcpresser\ce_table.py data\cheat-engine\OrcishScout.CT
```

---

## Part E — read the results

```bat
.\.venv\Scripts\python.exe src\orcpresser\scout_analysis.py --latest
.\.venv\Scripts\python.exe src\orcpresser\scout_analysis.py --all
```

`--latest` writes `data\scout_reports\<session>.md`; `--all` also writes `ALL_SESSIONS.md` across sessions. Raw sessions are never modified.

Sections that matter here:

| Report section | Source | What to look at |
|---|---|---|
| **Game-internal telemetry** | Cheat Engine stream (D1) | Counts and values seen per signal (`property_change`, `record_added`, ...). **Internal event ↔ landmark matches**: which vision/state landmark each record's value changes sit next to |
| **Semantic memory candidates** | Imported candidates (D2) | `success` % (reads that worked), `transitions`, `values`. **Candidate ↔ transition matches** |
| **Independent Scout sidecar** | Orcish memory reads | `memory_success_pct`: near 0 means reads fail (see troubleshooting) |

**How to read a match line** (format roughly like this):

```text
fishing phase ↔ state:FIGHT · matches=14 · median Δ=-180 ms · p95 |Δ|=240 ms
```

- **matches**: how many value changes landed near that landmark. A change may lead a landmark by up to 500 ms or lag it by up to 150 ms to count.
- **median Δ**: negative means **memory changed before** vision/state saw it. That is the valuable case: memory can warn the bot early.
- **p95 |Δ|**: small and stable means consistent timing.

**What a good candidate looks like**, over several sessions:

- Its value changes line up with the same landmark each time (for example → `state:FIGHT`, → `vision:reel`), with a similar median Δ.
- Each value means one thing: for example `2` only ever appears while waiting for a bite.
- `success` stays near 100% while fishing. Failures outside fishing (`null_pointer`, `pointer_read_failed`) are normal because the fishing object does not exist then.
- It still works after restarting the game, at night, and at another spot.

Write the value → meaning table into your research log as soon as it looks stable; the next development stage (agreement report, then shadow mode) builds on exactly that.

---

## Validation checklist before a signal is used by the bot

A candidate is not wired into live control until all of these hold (see [SCOUT_CANDIDATES.md](SCOUT_CANDIDATES.md) and [../roadmap.md](../roadmap.md)):

- [ ] Same value → state meaning in at least 5 sessions
- [ ] Survives at least 3 game restarts (pointer chain resolves each time)
- [ ] Holds at day and night and at 2+ spots
- [ ] Still resolves after a Dragonwilds update, or has been re-found and re-validated
- [ ] Reads succeed while fishing (`success` ≈ 100%)
- [ ] Known behaviour when it fails (object missing → vision only)

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Setup 8: `Cheat Engine stream: no data yet` | Table script not running, or not attached | Reopen `OrcishScout.CT`, answer Yes; check the Lua Engine window for `[OrcishScout] Cheat Engine bridge writing to ...` |
| Stream has `wrong_process` | Cheat Engine is attached to another process | Attach to Dragonwilds; the bridge resumes automatically |
| Stream has only `heartbeat`, no `property_change` | Table empty, or all records skipped | Add addresses; remove a leading `-` from descriptions |
| No memory data in Fishing sessions | **Run independent Scout probes** off, or candidates imported under another domain | Turn it on; re-import with domain **fishing** |
| Report shows `backend_error` / `memory_success_pct` 0 | Orcish cannot open the game process for reading | Update: builds before 28 September 2026 could not read memory at all (`SIZE_T` bug); if it still says `OpenProcess failed`, try running Orcish as Administrator |
| Candidate always `module_not_found` | Module name in the chain differs from the running build | Game Pass is `rsdragonwilds-wingdk-shipping.exe`, Steam is `rsdragonwilds-win64-shipping.exe` |
| Candidate always `null_pointer` / `pointer_read_failed` | Chain broken (restart or update), or you are not fishing | Check while fishing; redo C4 |
| Import skipped a record | Script, string, byte array or symbol/AOB-based | Convert to a pointer path (C4) or add the address manually |
| Values differ between Scout and Cheat Engine | Pointer offset order | Report it (see D2 step 4) |

---

## Data hygiene

- Everything above lives under `data\`, which is git-ignored. **Never commit sessions, tables, screenshots or logs.**
- A `.CT` file contains addresses for your game build only; it is personal research data.
- To get help with a session, share the report (`data\scout_reports\<session>.md`) first; share raw session folders only when needed, they can contain screenshots.
