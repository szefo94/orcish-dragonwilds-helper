# Scout game-internal telemetry

> **Status: experimental research.** Tooling paths and observations here may be build-specific or provisional. Confirm current implementation and validation status before making runtime behavior depend on them.


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

Because `WindowsApps` is package-managed and ACL-protected, the general telemetry installer (Setup option 7 / `Install-TelemetryToolkit.ps1`) does **not** write UE4SS into that directory unless the user explicitly opts in. The dedicated **Setup option 9** recovery path is different: it is specifically for the WinGDK build, requests elevation, installs the current experimental UE4SS layout beside the detected WinGDK executable, and creates a backup/rollback record. For a manual general-installer attempt, run PowerShell as Administrator and pass:

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

UE4SS expects a Lua mod below its `Mods\<ModName>\scripts\main.lua` directory. Copy the supplied `OrcishScout` folder into UE4SS's `Mods` folder and enable:

```text
OrcishScout : 1
```

in `Mods\mods.txt`.

Then edit two things in `main.lua`:

1. `OUTPUT` — an absolute writable path, for example:

```lua
local OUTPUT = [[C:\\Temp\\orcish_scout_ue4ss.jsonl]]
```

2. `HOOKS` — full UFunction names discovered using UE4SS Live Property Viewer / dumps:

```lua
local HOOKS = {
    { label = "fish_bite", fn = "/Game/...:OnFishBite" },
    { label = "reel_available", fn = "/Game/...:OnReelAvailable" },
}
```

The placeholder names in the repository are intentionally disabled; Dragonwilds-specific function names must be discovered on the user's game build. UE4SS `RegisterHook` requires the UFunction to exist in memory when registered.

In Orcish:

1. Open **SCOUT LAB**.
2. Enable **Read external JSONL bridge**.
3. Put exactly the same absolute path in the bridge path field.
4. Enable **Run independent Scout probes alongside Auto / Fishing / Aim** if you want Fishing/Auto controller events in the same session.
5. Start Fishing/Auto/Scout normally.
6. Fish or interact normally and stop the session.
7. Run `scout_analysis.py --latest`.

The bridge opens the file at its current end, so old events from previous sessions are not replayed.

### Generic external event format

Any local producer can use the same bridge. One JSON object per line:

```json
{"provider":"ue4ss","signal":"function_call","value":"fish_bite","function":"/Game/...:OnFishBite"}
{"provider":"custom","signal":"property_change","value":2,"property":"PullDirection","details":{"from":1,"to":2}}
```

Fields `provider`, `signal` and `value` are recommended. `function`, `object`, `property`, `args`, `producer_time` and `producer_seq` are preserved in event details.

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
- Cheat Engine, ReClass.NET and x64dbg remain external discovery tools and are not runtime dependencies.
- Existing read-only memory candidates use only Windows APIs already available to Orcish.

## Notes on current APIs

The Frida script uses the Frida 17+ module API (`Process.findModuleByName(...).base`) and `Interceptor.attach`.

UE4SS bridge hooks use `RegisterHook(fullUFunctionName, callback)`. UE4SS documentation notes that the target UFunction must already exist in memory at registration time.

References:

- https://frida.re/docs/javascript-api/
- https://frida.re/news/2025/05/17/frida-17-0-0-released/
- https://docs.ue4ss.com/lua-api/global-functions/registerhook.html
- https://docs.ue4ss.com/guides/creating-a-lua-mod.html
