-- Orcish Scout UE4SS telemetry bridge.
-- Copy this folder to UE4SS/Mods/OrcishScout and enable "OrcishScout : 1" in Mods/mods.txt.
-- Edit OUTPUT and HOOKS for your local installation / discovered Dragonwilds UFunctions.
--
-- This bridge only observes configured UFunction calls and appends one JSON object per line.
-- It does not change parameters or return values.

local OUTPUT = [[C:\\Temp\\orcish_scout_ue4ss.jsonl]]

-- Add full UFunction names discovered with UE4SS Live Property Viewer / dumps.
-- Examples below are deliberately disabled placeholders.
local HOOKS = {
    -- { label = "fish_bite", fn = "/Game/...:OnFishBite" },
    -- { label = "reel_state", fn = "/Game/...:OnReelAvailable" },
}

local function escape_json(s)
    s = tostring(s or "")
    s = s:gsub("\\", "\\\\")
    s = s:gsub('"', '\\"')
    s = s:gsub("\n", "\\n")
    s = s:gsub("\r", "\\r")
    s = s:gsub("\t", "\\t")
    return s
end

local function emit(signal, label, fn, object_name)
    local f = io.open(OUTPUT, "a")
    if not f then
        print("[OrcishScout] Cannot open telemetry output: " .. OUTPUT .. "\n")
        return
    end
    local line = string.format(
        '{"provider":"ue4ss","signal":"%s","value":"%s","function":"%s","object":"%s","producer_time":%.6f}',
        escape_json(signal), escape_json(label), escape_json(fn), escape_json(object_name), os.clock()
    )
    f:write(line .. "\n")
    f:flush()
    f:close()
end

local function object_name(Context)
    if not Context then return "" end
    local ok, value = pcall(function()
        local obj = Context:get()
        if obj and obj:IsValid() then return obj:GetFullName() end
        return ""
    end)
    if ok then return value or "" end
    return ""
end

print("[OrcishScout] UE4SS bridge loading\n")
emit("bridge_start", "OrcishScout", "", "")
for _, h in ipairs(HOOKS) do
    local ok, pre, post = pcall(function()
        return RegisterHook(h.fn, function(Context, ...)
            emit("function_call", h.label, h.fn, object_name(Context))
        end)
    end)
    if ok then
        print(string.format("[OrcishScout] hooked %s (%s)\n", h.label, h.fn))
    else
        print(string.format("[OrcishScout] failed %s (%s): %s\n", h.label, h.fn, tostring(pre)))
        emit("hook_error", h.label, h.fn, tostring(pre))
    end
end
emit("bridge_ready", "OrcishScout", "", "")
print("[OrcishScout] UE4SS bridge ready\n")
