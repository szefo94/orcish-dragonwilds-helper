-- Orcish Scout Cheat Engine bridge.
-- Loaded by data\cheat-engine\OrcishScout.CT (created by Setup.cmd option 7). Open that table in
-- Cheat Engine and allow its Lua script to run; the table sets ORCISH_SCOUT_CE_OUTPUT first.
--
-- Every INTERVAL ms the bridge reads the current value of each address in the open cheat table
-- (the same read Cheat Engine does to display it) and appends value changes as JSON lines that
-- Orcish Scout records on its timeline. It never writes game memory, never enables scripts and
-- never freezes values. Prefix a record's description with '-' to leave it out.
--
-- Lua console helpers: OrcishScoutCE.stop(), OrcishScoutCE.start(), OrcishScoutCE.mark("text")

local OUTPUT = ORCISH_SCOUT_CE_OUTPUT or [[C:\Temp\cheat_engine.jsonl]]
local INTERVAL = tonumber(ORCISH_SCOUT_CE_INTERVAL) or 100
local HEARTBEAT_MS = 5000
local ATTACH_RETRY_MS = 2000
local MAX_RECORDS = 500
local TARGETS = { "RSDragonwilds-WinGDK-Shipping.exe", "RSDragonwilds-Win64-Shipping.exe" }

if OrcishScoutCE and OrcishScoutCE.stop then pcall(OrcishScoutCE.stop) end

local TYPE_NAMES = {}
for _, n in ipairs({ "vtByte", "vtWord", "vtDword", "vtQword", "vtSingle", "vtDouble", "vtString",
                     "vtUnicodeString", "vtByteArray", "vtBinary", "vtAutoAssembler", "vtPointer",
                     "vtCustom", "vtGrouped" }) do
    if _G[n] ~= nil then TYPE_NAMES[_G[n]] = n:sub(3):lower() end
end

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

local pending = {}

local function emit(signal, value, extra)
    local parts = { '"provider":"cheat_engine"', '"signal":' .. json_value(signal), '"value":' .. json_value(value) }
    for k, v in pairs(extra or {}) do parts[#parts + 1] = json_value(k) .. ":" .. json_value(v) end
    parts[#parts + 1] = '"producer_time":' .. json_value(getTickCount() / 1000.0)
    pending[#pending + 1] = "{" .. table.concat(parts, ",") .. "}"
end

local function flush()
    if #pending == 0 then return end
    local f = io.open(OUTPUT, "a")
    if not f then
        print("[OrcishScout] Cannot open " .. OUTPUT)
        pending = {}
        return
    end
    f:write(table.concat(pending, "\n") .. "\n")
    f:close()
    pending = {}
end

local function is_target(name)
    if not name then return false end
    local lower = tostring(name):lower()
    for _, t in ipairs(TARGETS) do if lower == t:lower() then return true end end
    return false
end

-- Returns the attached Dragonwilds process name, attaching when Cheat Engine has no live target.
local last_attach_try = -ATTACH_RETRY_MS
local reported_wrong = nil
local function ensure_attached()
    local pid = getOpenedProcessID() or 0
    local name = process
    if pid ~= 0 and is_target(name) and getProcessIDFromProcessName(name) == pid then return name end
    if pid ~= 0 and name and not is_target(name) and getProcessIDFromProcessName(name) == pid then
        if reported_wrong ~= name then
            emit("wrong_process", name, { expected = table.concat(TARGETS, "|") })
            reported_wrong = name
        end
        return nil
    end
    local now = getTickCount()
    if now - last_attach_try < ATTACH_RETRY_MS then return nil end
    last_attach_try = now
    for _, t in ipairs(TARGETS) do
        if getProcessIDFromProcessName(t) then
            if openProcess(t) then
                emit("attached", t, { pid = getOpenedProcessID() })
                reported_wrong = nil
                return t
            end
        end
    end
    return nil
end

local function typed(text)
    if text == nil or text == "??" then return nil end
    local n = tonumber(text)
    if n ~= nil then return n end
    return text
end

local last_values = {}
local known = {}
local last_heartbeat = 0
local attached_name = nil

local function tick()
    local name = ensure_attached()
    if name ~= attached_name then
        if attached_name and not name then emit("detached", attached_name) end
        attached_name = name
        last_values = {}
    end
    if not name then flush(); return end

    local al = getAddressList()
    local count = math.min(al.Count, MAX_RECORDS)
    local streamed = 0
    for i = 0, count - 1 do
        local mr = al.MemoryRecord[i]
        local ok_skip, skip = pcall(function()
            return mr.IsGroupHeader or mr.Type == vtAutoAssembler or (mr.Description or ""):sub(1, 1) == "-"
                or (mr.Address or "") == ""
        end)
        if ok_skip and not skip then
            streamed = streamed + 1
            local id = mr.ID
            local desc = mr.Description or ("record " .. tostring(id))
            local type_name = TYPE_NAMES[mr.Type] or tostring(mr.Type)
            if not known[id] then
                known[id] = true
                emit("record_added", desc, { property = desc, details = { id = id, address = mr.Address, type = type_name } })
            end
            local ok, text = pcall(function() return mr.Value end)
            local value = ok and typed(text) or nil
            local key = ok and tostring(text) or "<error>"
            local previous = last_values[id]
            if previous ~= key then
                last_values[id] = key
                emit("property_change", value, {
                    property = desc,
                    details = { id = id, address = mr.Address, resolved = string.format("0x%X", mr.CurrentAddress or 0),
                                type = type_name, from = previous, to = key, readable = value ~= nil },
                })
            end
        end
    end

    local now = getTickCount()
    if now - last_heartbeat >= HEARTBEAT_MS then
        last_heartbeat = now
        emit("heartbeat", streamed, { process = name, records = al.Count })
    end
    flush()
end

local timer = nil

OrcishScoutCE = {}

function OrcishScoutCE.stop()
    if timer then timer.Enabled = false; timer.destroy(); timer = nil end
    emit("bridge_stop", "OrcishScoutCE"); flush()
end

function OrcishScoutCE.start()
    if timer then return end
    emit("bridge_start", "OrcishScoutCE", { interval_ms = INTERVAL, output = OUTPUT }); flush()
    timer = createTimer(getMainForm(), false)
    timer.Interval = INTERVAL
    timer.OnTimer = function()
        local ok, err = pcall(tick)
        if not ok then emit("bridge_error", tostring(err)); flush() end
    end
    timer.Enabled = true
    print("[OrcishScout] Cheat Engine bridge writing to " .. OUTPUT)
end

function OrcishScoutCE.mark(text)
    emit("mark", tostring(text or "mark")); flush()
end

OrcishScoutCE.start()
