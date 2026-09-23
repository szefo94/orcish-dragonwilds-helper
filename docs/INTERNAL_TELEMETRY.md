# Scout game-internal telemetry

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
