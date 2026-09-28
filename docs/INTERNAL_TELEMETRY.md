# Scout game-internal telemetry

> **Status: experimental research.** Tooling paths and observations here may be build-specific or provisional. Confirm current implementation and validation status before making runtime behavior depend on them.

## Quick start (Research POC)

```text
Setup.cmd -> 1   install Orcish (first time only; Run.cmd also does this)
Setup.cmd -> 7   install the toolkit and create the research files (Dragonwilds closed)
Run.cmd          bind the game -> SCOUT LAB -> START (or Fishing with Scout probes on)
Setup.cmd -> 8   check which sources are actually writing data
```

Option 7 installs Frida, UE4SS + the OrcishScout mod (on the Microsoft Store / Game Pass WinGDK build it runs the option 9 installer, with an Administrator prompt), x64dbg, ReClass.NET, Cheat Engine (opens the official download page if missing) and the Windows Performance Toolkit. It also creates, without overwriting anything you edited:

| File | Used by |
|---|---|
| `data\ue4ss\orcish_hooks.txt` | UE4SS mod: which UFunctions to log, which properties to poll, scan filters |
| `data\ue4ss\orcish_scout_ue4ss.jsonl` | written by the UE4SS mod, read by Scout |
| `data\cheat-engine\OrcishScout.CT` | starter Cheat Engine table that loads the Orcish bridge |
| `data\telemetry\cheat_engine.jsonl` | written by the Cheat Engine bridge, read by Scout |

Scout Lab reads both JSONL files by default (**Read JSONL bridges** is on; the path field takes several paths separated by `;`). Every source lands on the same session timeline as vision and controller events, and `scout_analysis.py --latest` correlates them with Fishing/Auto landmarks.

| Source | How to get data |
|---|---|
| **UE4SS** | Start the game. In game, **Ctrl+F10** scans live object/function names matching the `scan` filters into `data\ue4ss\scans\`. `Setup.cmd scans` prints them as ready-to-paste `function` lines for `orcish_hooks.txt`; restart the game to apply. |
| **Cheat Engine** | Open `OrcishScout.CT`, allow its Lua script. It attaches to Dragonwilds and streams every address in the table (add them by scanning as usual); each value change becomes a `property_change` event. |
| **Frida** | Native functions found with x64dbg/ReClass.NET → SCOUT LAB → Frida hook `label=MODULE+0xOFFSET`. |
| **Read-only memory watches** | SCOUT LAB → memory watch / semantic candidate (`MODULE+0xOFFSET:type`). |
| **Windows Performance Recorder** | `Setup.cmd` → **10** records an ETW trace to `data\traces\` for WPA. |

**Current blocker on the WinGDK build:** a UE4SS runtime that fails its startup scan (`PS scan timed out` or repeated `Failed to find GUObjectArray … Scan failed` in `UE4SS.log`) never loads any mod, so the UE4SS source stays empty until a UE4SS build supports this game build. Cheat Engine, Frida and memory watches do not depend on UE4SS.


## Microsoft Store / Xbox App (WinGDK) builds

### Current Dragonwilds WinGDK recovery path

The current goal is not "install more tools"; it is to get one reliable internal-data path working:

```text
Dragonwilds -> UE4SS starts -> OrcishScout Lua runs -> data\ue4ss\orcish_scout_ue4ss.jsonl
```

On the tested Microsoft Store/Xbox WinGDK build, the older UE4SS v3.0.1 runtime loaded its proxy DLL and created `UE4SS.log`, but its pattern scan repeatedly failed to locate core Unreal structures and ended with `Fatal Error: PS scan timed out`. That happens before the OrcishScout Lua mod can execute, so an empty JSONL folder is a downstream symptom rather than the root problem.

For that specific recovery case, `Setup.cmd` now provides:

- **9 · Recover UE4SS for WinGDK** — downloads the current official `experimental-latest` zDEV UE4SS build, backs up the existing UE4SS files, installs the current `ue4ss\` subfolder layout, installs OrcishScout, patches the JSONL path, and automatically restores the backup if installation fails.
- **8 · Telemetry toolkit status** — after one game launch, checks both old and new UE4SS log locations and reports whether the PS scan timed out or the OrcishScout startup heartbeat appeared.

Dragonwilds must be closed before option 9 runs. The script requests Administrator elevation automatically because the WinGDK build lives under `WindowsApps`. It does not take ownership of the WindowsApps tree.

The recovery installer keeps a timestamped backup beside the game executable and records what it installed in:

```text
data\ue4ss\ue4ss_experimental_install.json
```

After option 9 completes, the intended test is deliberately short:

```text
start Dragonwilds
-> wait for menu/world
-> close Dragonwilds
-> Setup.cmd -> 8
```

Success is defined narrowly: UE4SS no longer ends in `PS scan timed out`, and the OrcishScout bridge reaches `bridge_start` / `bridge_ready`. Only after that should Fishing UFunction discovery continue.

Dragonwilds may run as:

```text
RSDragonwilds-WinGDK-Shipping.exe
```

from a package path under:

```text
C:\Program Files\WindowsApps\JagexLimited.Dominion_*\RSDragonwilds\Binaries\WinGDK\
```

The toolkit now auto-detects this executable as a valid Dragonwilds target. This is distinct from the Steam-style `RSDragonwilds-Win64-Shipping.exe`.

Because `WindowsApps` is package-managed and ACL-protected, the general telemetry installer (Setup option 7 / `Install-TelemetryToolkit.ps1`) does **not** extract UE4SS into that directory itself. For the WinGDK executable it hands over to the option 9 installer instead (skipped when the current runtime and an up-to-date OrcishScout pointing at this folder are already installed, refused while the game is running). The dedicated **Setup option 9** recovery path is different: it is specifically for the WinGDK build, requests elevation, installs the current experimental UE4SS layout beside the detected WinGDK executable, and creates a backup/rollback record. For a manual general-installer attempt, run PowerShell as Administrator and pass:

```powershell
-AllowWindowsAppsInstall
```

For example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-TelemetryToolkit.ps1 -Install -All -AllowWindowsAppsInstall
```

If Windows denies writes or the package is restored by an update/repair, do not change ownership of the entire `WindowsApps` tree. Use a supported mod/injection method for the WinGDK build instead. UE4SS's own installation model still requires its DLL to be loaded by the target process and its working directory to be resolvable. The basic/developer install normally places UE4SS in the actual game executable directory.

## Installer repair notes

The toolkit installer now accepts only the two explicit Dragonwilds executable names:

```text
RSDragonwilds-Win64-Shipping.exe
RSDragonwilds-WinGDK-Shipping.exe
```

It no longer accepts arbitrary `*-Win64-Shipping.exe` processes. This prevents Epic Online Services' `EOSOverlayRenderer-Win64-Shipping.exe` from being mistaken for Dragonwilds while still supporting both Steam-style Win64 and Microsoft Store/Xbox WinGDK builds.

If an older installer run placed `OrcishScout` / UE4SS under an Epic Online Services `managedArtifacts` directory, option **8 · Telemetry toolkit status** reports the mistaken path explicitly. Treat that installation as invalid and inspect the adjacent `orcish_ue4ss_backup_*` folder before removing/restoring those files.

The installer also now:

- prefers an already-downloaded `zDEV-UE4SS_v*.zip` or `UE4SS_v*.zip` in the Orcish root before downloading again;
- understands that the official ReClass.NET release asset is `ReClass.NET.rar`; it uses the local archive when present and installs 7-Zip through WinGet if needed;
- checks Cheat Engine through Windows uninstall registry entries and common install folders before doing anything;
- no longer expects a Cheat Engine installer asset from GitHub, because the official 7.5 GitHub release has no binary assets; if Cheat Engine is absent it opens the official download page instead;
- skips x64dbg installation when the executable is already present;
- continues with the remaining tools when one optional component fails, instead of aborting the whole toolkit pass.

## Guided Windows toolkit installer

The repository includes:

```text
scripts\Install-TelemetryToolkit.ps1
```

It can check or install the research-side prerequisites without changing normal Orcish runtime requirements.

Check only:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-TelemetryToolkit.ps1 -CheckOnly
```

Install the supported toolkit:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-TelemetryToolkit.ps1 -Install -All
```

The same operations are available through `Setup.cmd`:

- **7 · Install telemetry toolkit**
- **8 · Telemetry toolkit status**
- **9 · Recover UE4SS for WinGDK**

The installer currently:

- installs/repairs the optional Frida Python package in Orcish's `.venv`;
- auto-detects a running `RSDragonwilds-Win64-Shipping.exe` or `RSDragonwilds-WinGDK-Shipping.exe`, searches Steam libraries, and checks the Microsoft Store/Xbox `WindowsApps` package location;
- checks a local `RE-UE4SS-main.zip` placed in the repository root;
- rejects that ZIP as an install source when it contains source code rather than runtime DLLs, then downloads the latest stable **zDEV** UE4SS binary release from the official `UE4SS-RE/RE-UE4SS` GitHub releases;
- backs up existing UE4SS files before extraction;
- copies the OrcishScout Lua bridge into the detected UE4SS `Mods` directory and configures its JSONL output under `data\ue4ss`;
- installs x64dbg through WinGet;
- downloads the latest ReClass.NET release from its official GitHub repository as a portable tool under `tools\external`;
- detects an existing Cheat Engine installation from uninstall metadata/common folders; if it is absent, the toolkit directs the user to the official download path rather than assuming a GitHub binary asset exists;
- installs the Windows ADK request for the Windows Performance Toolkit through WinGet.

For a non-standard Steam/game location, pass the executable explicitly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-TelemetryToolkit.ps1 -Install -All -GameExe "D:\Games\Dragonwilds\...\Dragonwilds-Win64-Shipping.exe"
```

For an actual UE4SS binary archive you downloaded yourself:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-TelemetryToolkit.ps1 -Install -All -UE4SSZip "C:\Downloads\zDEV-UE4SS_v3.0.1.zip"
```

A GitHub **Code → Download ZIP** named `RE-UE4SS-main.zip` is source code, not a ready-to-run UE4SS installation. The script detects this by inspecting the archive for the UE4SS runtime DLLs and falls back to the official release asset.

Scout now has two optional adapters for events that are not derived from pixels:

1. **External JSONL bridge** — consumes newline-delimited events produced by UE4SS or another local research tool.
2. **Frida function-entry provider** — attaches to the bound game process and records calls to explicitly configured module-relative native functions.

Neither adapter is required for normal Auto Picker, Fishing, Aim or Scout use. Ordinary `ReadProcessMemory` watches remain the lowest-impact game-memory path.

## What gets recorded

Internal events use the same Scout recorder and monotonic clock as vision and controller telemetry:

```json
{
  "source": "game_internal",
  "signal": "function_call",
  "value": "reel_available",
  "mono": 12345.678,
  "details": {
    "provider": "ue4ss",
    "function": "/Game/...:OnReelAvailable"
  }
}
```

They are stored in the session's `process.jsonl`. The analyzer groups them by provider/signal and matches them to nearby Fishing or Auto Picker landmarks. A negative delta means the internal event was received before the visible/controller landmark.

Run:

```bat
.\.venv\Scripts\python.exe src\orcpresser\scout_analysis.py --latest
```

and inspect **Game-internal telemetry** in the generated report.

## A. UE4SS bridge

This is the preferred first experiment for named Unreal `UFunction` events because it preserves semantic names.

The included template is:

```text
tools\ue4ss\OrcishScout\scripts\main.lua
```

Setup option 7 (or 9 on WinGDK) copies the `OrcishScout` folder into UE4SS's `Mods` folder, enables `OrcishScout : 1` in `Mods\mods.txt` and patches `OUTPUT` in `main.lua` to this folder's `data\ue4ss\orcish_scout_ue4ss.jsonl`. `main.lua` is not edited by hand: the mod reads its configuration at game start from `orcish_hooks.txt` next to `OUTPUT`, which reinstalls and updates never touch.

```text
# data\ue4ss\orcish_hooks.txt
function fish_bite = /Game/Path/BP_Fishing.BP_Fishing_C:OnFishBite   # log each call (function_call)
property fishing_state = BP_FishingComponent_C.FishingState          # poll first live instance, log changes (property_change)
scan Fish                                                            # Ctrl+F10 scan name filter (case-insensitive)
poll_ms 250                                                          # property poll interval
```

Names are build-specific and must be discovered on your game build; the file ships only commented placeholders plus `scan` filters. Discovery loop:

1. In game press **Ctrl+F10**. The mod writes every live object/UFunction whose full name contains a `scan` filter to `data\ue4ss\scans\scan_<time>.jsonl` (up to 5000 entries) and logs `object_scan_done`. The game can pause for a few seconds while it checks every object.
2. Run `Setup.cmd scans` to print the UFunctions from the newest scan as `function <label> = <path>` lines.
3. Paste the ones you want into `orcish_hooks.txt` and restart the game.

UE4SS `RegisterHook` requires the UFunction to exist in memory when registered. Blueprint classes often load with the world rather than the menu, so hooks that fail at startup are logged as `hook_pending` and retried every 5 s for about ten minutes (`hook_ready` on success, `hook_error` when giving up).

Property polling runs `FindFirstOf(<Class>)` on the game thread each interval and reads the property; values are logged only when they change (`<no instance>` while no object of that class exists). It reads only.

Events the mod writes: `bridge_start`, `bridge_ready` (with counts of configured hooks/properties), `config_missing`, `hook_ready`, `hook_pending`, `hook_error`, `function_call`, `property_change`, `object_scan_done`, `object_scan_error`, `keybind_error`. `Setup.cmd` option 8 reports the installed mod version and warns when it writes to a different Orcish folder than the one you are checking from.

In Orcish, SCOUT LAB reads this file by default. Enable **Run independent Scout probes alongside Auto / Fishing / Aim** to get Fishing/Auto controller events in the same session, record, then run `scout_analysis.py --latest`.

The bridge opens an existing file at its current end, so old events from previous sessions are not replayed; a file created during a recording is read from its first line.

### Generic external event format

Any local producer can use the same bridge. One JSON object per line:

```json
{"provider":"ue4ss","signal":"function_call","value":"fish_bite","function":"/Game/...:OnFishBite"}
{"provider":"custom","signal":"property_change","value":2,"property":"PullDirection","details":{"from":1,"to":2}}
```

Fields `provider`, `signal` and `value` are recommended. Every other top-level field (for example `function`, `object`, `property`, `label`, `args`, `error`, `producer_time`) is kept in event details, merged with `details`. When a line has no `provider`, the bridge file name (without extension) is used.

## B. Frida native function telemetry

Frida is optional and deliberately not part of `src/requirements.txt`.

Install it only for research:

```bat
.\.venv\Scripts\python.exe -m pip install -r src\requirements-telemetry.txt
```

Restart Orcish. Scout Lab should then show **Frida: installed**.

Frida needs a known native function address. Discover it first using a debugger/scanner/disassembly workflow, then store it as a module-relative hook:

```text
pull_update=Dragonwilds-Win64-Shipping.exe+0x123456
reel_update=Dragonwilds-Win64-Shipping.exe+0xABCDEF
```

In Scout Lab:

1. enter one hook;
2. press **ADD FUNCTION HOOK**;
3. enable **Observe native function entry with Frida**;
4. restart the Scout/Fishing session so the provider attaches.

For every configured function entry Scout records:

- label;
- module and offset;
- resolved address;
- thread ID;
- first four raw argument pointer values;
- receipt timestamp.

The provider does not intentionally modify function arguments or return values. However, Frida `Interceptor` is **invasive instrumentation** inside the target process; it is not equivalent to a read-only `ReadProcessMemory` watch. Keep it optional and use it only in an environment where you are comfortable attaching a debugger/instrumentation tool.

## C. Cheat Engine bridge

Cheat Engine is the practical way to find addresses by value scanning and to follow pointer chains; the bridge puts what you find on the Scout timeline without re-entering it in Orcish.

Files:

```text
tools\cheat-engine\orcish_scout_ce.lua   bridge script (updated with Orcish)
data\cheat-engine\OrcishScout.CT         your table; created once by Setup option 7
data\telemetry\cheat_engine.jsonl        output read by Scout
```

The table's Lua script contains only a marked loader block that sets the output path and runs the bridge script. Setup option 7 refreshes that block (paths change when the folder is re-extracted) and leaves your addresses and any Lua you add below the block untouched. A table without the block is never modified.

Use:

1. Open `OrcishScout.CT` in Cheat Engine and answer **Yes** when it asks to execute the table's Lua script.
2. The bridge attaches to `RSDragonwilds-WinGDK-Shipping.exe` or `RSDragonwilds-Win64-Shipping.exe` when Cheat Engine has no live target, and re-attaches after the game restarts. If Cheat Engine is attached to another process it logs `wrong_process` and waits.
3. Find addresses as usual (value scans, pointer scans) and add them to the table. Name them descriptively; the description becomes the event's `property`, so `fishing phase` is easier to correlate than `No description`.
4. Every 100 ms the bridge reads the displayed value of each record and writes `property_change` when it changes (`value` is a number when it parses as one, `null` when unreadable; `details` has address, resolved address, type, from/to). New records produce `record_added`; a `heartbeat` every 5 s shows it is alive.
5. Save the table in Cheat Engine as usual.

Records whose description starts with `-`, group headers and Auto Assembler script entries are skipped. The bridge never writes memory, activates scripts or freezes values; it reads what Cheat Engine already shows. In the Lua console, `OrcishScoutCE.stop()`, `OrcishScoutCE.start()` and `OrcishScoutCE.mark("text")` control it.

Once a Cheat Engine address proves stable across restarts as a module-relative offset, it can move to a SCOUT LAB semantic candidate (`MODULE+0xOFFSET:type`), which Orcish reads by itself without Cheat Engine. Pointer chains stay in Cheat Engine.

## D. Windows Performance Recorder

`Setup.cmd` option **10** runs `scripts\Record-PerformanceTrace.ps1`: it asks for Administrator access, starts WPR with the `GeneralProfile` and `CPU` profiles, waits for Enter and saves `data\traces\orcish_<time>.etl` for Windows Performance Analyzer. A trace that fails to stop is cancelled so no kernel session is left running.

## Recommended Fishing discovery workflow

Use the visible/controller session as the reference timeline, then search for internal events corresponding to:

```text
STOP visible
STOP disappears
BITE_PENDING
PULL A / PULL D
FIGHT
REEL
catch/failure
```

Prioritize internal concepts such as:

```text
FishingState
Hooked
PullDirection
CanReel
Tension
CatchProgress
Result
```

A useful candidate should repeatedly precede or tightly coincide with the same visible/controller transition across several launches.

Do not promote one address/function into live control after one successful recording. Validate it across restarts and game updates and keep the visual path as a fallback.

## Dependency model

Normal Orcish remains unchanged: no Frida or UE4SS dependency.

- UE4SS runs externally and writes a local JSONL file.
- Frida is an optional Python package loaded lazily only when enabled.
- Cheat Engine, ReClass.NET and x64dbg remain external discovery tools and are not runtime dependencies. The Cheat Engine bridge runs inside Cheat Engine and only writes a local JSONL file.
- Existing read-only memory candidates use only Windows APIs already available to Orcish.

## Notes on current APIs

The Frida script uses the Frida 17+ module API (`Process.findModuleByName(...).base`) and `Interceptor.attach`.

UE4SS bridge hooks use `RegisterHook(fullUFunctionName, callback)`. UE4SS documentation notes that the target UFunction must already exist in memory at registration time.

References:

- https://frida.re/docs/javascript-api/
- https://frida.re/news/2025/05/17/frida-17-0-0-released/
- https://docs.ue4ss.com/lua-api/global-functions/registerhook.html
- https://docs.ue4ss.com/guides/creating-a-lua-mod.html
