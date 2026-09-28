-- Orcish Scout UE4SS telemetry bridge.
-- Installed by Setup.cmd option 7 (or 9 for the Microsoft Store / Game Pass WinGDK build), which
-- copies this folder to UE4SS/Mods/OrcishScout, enables it in mods.txt and patches OUTPUT below.
--
-- Configuration is NOT edited here: hooks, property polls and scan filters are read at game start
-- from orcish_hooks.txt next to OUTPUT (data\ue4ss\orcish_hooks.txt), which reinstalls never touch.
--
-- The bridge only observes: it logs configured UFunction calls, polls configured properties and,
-- on Ctrl+F10, writes a name scan of live objects. It never changes parameters, return values
-- or properties.

local BRIDGE_VERSION = 2
local OUTPUT = [[C:\\Temp\\orcish_scout_ue4ss.jsonl]]

local DATA_DIR = OUTPUT:match("^(.*)[\\/]") or "."
local HOOKS_FILE = DATA_DIR .. "\\orcish_hooks.txt"
local SCAN_DIR = DATA_DIR .. "\\scans"
local SCAN_LIMIT = 5000
local HOOK_RETRY_MS = 5000
local HOOK_RETRY_MAX = 120   -- about ten minutes: Blueprint classes often load with the world, not the menu

local function json_value(v)
    local t = type(v)
    if t == "number" then
        if v ~= v or v == math.huge or v == -math.huge then return '"' .. tostring(v) .. '"' end
        return tostring(v)
    elseif t == "boolean" then return tostring(v)
    elseif v == nil then return "null"
    elseif t == "table" then
        local parts = {}
        for k, x in pairs(v) do parts[#parts + 1] = json_value(tostring(k)) .. ":" .. json_value(x) end
        return "{" .. table.concat(parts, ",") .. "}"
    end
    local s = tostring(v)
    s = s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t")
    s = s:gsub("[\0-\31]", function(c) return string.format("\\u%04x", c:byte()) end)
    return '"' .. s .. '"'
end

local function append(path, fields)
    local f = io.open(path, "a")
    if not f then
        print("[OrcishScout] Cannot open " .. path .. "\n")
        return false
    end
    local parts = {}
    for _, kv in ipairs(fields) do parts[#parts + 1] = json_value(kv[1]) .. ":" .. json_value(kv[2]) end
    f:write("{" .. table.concat(parts, ",") .. "}\n")
    f:close()
    return true
end

local function emit(signal, value, extra)
    local fields = { { "provider", "ue4ss" }, { "signal", signal }, { "value", value } }
    for k, v in pairs(extra or {}) do fields[#fields + 1] = { k, v } end
    fields[#fields + 1] = { "producer_time", os.time() }
    append(OUTPUT, fields)
end

local function trim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end

local function load_config()
    local cfg = { functions = {}, properties = {}, scan = {}, poll_ms = 250 }
    local f = io.open(HOOKS_FILE, "r")
    if not f then return cfg, false end
    for raw in f:lines() do
        local line = trim(raw)
        if line ~= "" and line:sub(1, 1) ~= "#" then
            local kw, rest = line:match("^(%S+)%s+(.+)$")
            kw = kw and kw:lower()
            if kw == "function" or kw == "property" then
                local label, spec = rest:match("^([^=]-)%s*=%s*(.+)$")
                if label and spec then
                    label, spec = trim(label), trim(spec)
                    if kw == "function" then
                        cfg.functions[#cfg.functions + 1] = { label = label, fn = spec }
                    else
                        local class, prop = spec:match("^(.-)%.([^%.]+)$")
                        if class and prop then
                            cfg.properties[#cfg.properties + 1] = { label = label, class = class, prop = prop, spec = spec }
                        end
                    end
                end
            elseif kw == "scan" then
                cfg.scan[#cfg.scan + 1] = trim(rest):lower()
            elseif kw == "poll_ms" then
                cfg.poll_ms = math.max(50, tonumber(rest) or 250)
            end
        end
    end
    f:close()
    return cfg, true
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

-- Plain values for JSON. FString/FName/FText expose ToString; UObjects are logged by full name.
local function plain(v)
    local t = type(v)
    if t == "number" or t == "boolean" or t == "string" or v == nil then return v end
    local ok, s = pcall(function() return v:ToString() end)
    if ok and s ~= nil then return tostring(s) end
    ok, s = pcall(function() if v:IsValid() then return v:GetFullName() end return "<invalid>" end)
    if ok and s ~= nil then return s end
    return tostring(v)
end

local function register_hook(h)
    local ok, err = pcall(function()
        RegisterHook(h.fn, function(Context, ...)
            emit("function_call", h.label, { ["function"] = h.fn, object = object_name(Context) })
        end)
    end)
    return ok, err
end

local function start_hooks(functions)
    local pending = {}
    for _, h in ipairs(functions) do
        local ok, err = register_hook(h)
        if ok then
            print(string.format("[OrcishScout] hooked %s (%s)\n", h.label, h.fn))
            emit("hook_ready", h.label, { ["function"] = h.fn })
        else
            pending[#pending + 1] = h
            emit("hook_pending", h.label, { ["function"] = h.fn, error = tostring(err) })
        end
    end
    if #pending == 0 then return end
    local attempts = 0
    LoopAsync(HOOK_RETRY_MS, function()
        attempts = attempts + 1
        ExecuteInGameThread(function()
            local still = {}
            for _, h in ipairs(pending) do
                local ok, err = register_hook(h)
                if ok then
                    print(string.format("[OrcishScout] hooked %s (%s) after retry\n", h.label, h.fn))
                    emit("hook_ready", h.label, { ["function"] = h.fn, attempts = attempts })
                elseif attempts >= HOOK_RETRY_MAX then
                    emit("hook_error", h.label, { ["function"] = h.fn, error = tostring(err) })
                else
                    still[#still + 1] = h
                end
            end
            pending = still
        end)
        return #pending == 0 or attempts >= HOOK_RETRY_MAX
    end)
end

local function start_property_polls(properties, poll_ms)
    if #properties == 0 then return end
    local last = {}
    LoopAsync(poll_ms, function()
        ExecuteInGameThread(function()
            for _, p in ipairs(properties) do
                local ok, value = pcall(function()
                    local obj = FindFirstOf(p.class)
                    if not obj or not obj:IsValid() then return "<no instance>" end
                    return plain(obj[p.prop])
                end)
                if not ok then value = "<error> " .. tostring(value) end
                local key = tostring(value)
                if last[p.label] ~= key then
                    local previous = last[p.label]
                    last[p.label] = key
                    emit("property_change", value, { property = p.spec, label = p.label, details = { from = previous, to = key } })
                end
            end
        end)
        return false
    end)
end

local function run_scan(filters)
    if #filters == 0 then filters = { "fish" } end
    local path = string.format("%s\\scan_%d.jsonl", SCAN_DIR, os.time())
    local f = io.open(path, "a")
    if not f then
        emit("object_scan_error", path, { error = "cannot open scan file (run Setup.cmd option 7 to create data\\ue4ss\\scans)" })
        return
    end
    local count, truncated = 0, false
    ForEachUObject(function(Object)
        if count >= SCAN_LIMIT then truncated = true; return end
        local ok, full = pcall(function() return Object:GetFullName() end)
        if not ok or not full then return end
        local lower = full:lower()
        for _, needle in ipairs(filters) do
            if lower:find(needle, 1, true) then
                local class, path_name = full:match("^(%S+)%s+(.+)$")
                local kind = (class == "Function") and "function" or "object"
                f:write("{" .. table.concat({
                    '"kind":' .. json_value(kind),
                    '"class":' .. json_value(class or ""),
                    '"full_name":' .. json_value(full),
                    '"hook_name":' .. json_value(kind == "function" and path_name or nil),
                }, ",") .. "}\n")
                count = count + 1
                break
            end
        end
    end)
    f:close()
    print(string.format("[OrcishScout] object scan wrote %d entries to %s\n", count, path))
    emit("object_scan_done", count, { path = path, filters = table.concat(filters, ","), truncated = truncated })
end

print("[OrcishScout] UE4SS bridge loading\n")
emit("bridge_start", "OrcishScout", { version = BRIDGE_VERSION })

local cfg, has_config = load_config()
if not has_config then
    emit("config_missing", HOOKS_FILE)
    print("[OrcishScout] no hooks file at " .. HOOKS_FILE .. " (run Setup.cmd option 7)\n")
end
start_hooks(cfg.functions)
start_property_polls(cfg.properties, cfg.poll_ms)

local scan_ok, scan_err = pcall(function()
    RegisterKeyBind(Key.F10, { ModifierKey.CONTROL }, function()
        -- The game may pause for a few seconds while every live object name is checked.
        ExecuteInGameThread(function() run_scan(cfg.scan) end)
    end)
end)
if not scan_ok then emit("keybind_error", "Ctrl+F10", { error = tostring(scan_err) }) end

emit("bridge_ready", "OrcishScout", {
    version = BRIDGE_VERSION, functions = #cfg.functions, properties = #cfg.properties,
    scan_filters = table.concat(cfg.scan, ","),
})
print("[OrcishScout] UE4SS bridge ready\n")
