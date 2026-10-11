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
-- F9 while the table is open also writes a mark ("hotkey") so moments can be flagged without the console.
--
-- Scan assistant (experimental, see docs/RESEARCH_DATA_GUIDE.md): when Orcish's SCOUT LAB option
-- "Let Fishing states drive Cheat Engine scans" is on, Orcish appends one command per line to
-- ORCISH_SCOUT_CE_COMMANDS (tab separated: seq, cmd, arg, var_type, state, phase). The bridge runs
-- them with a private memscan (your own scan tab is untouched) and replies on the stream with
-- scan_result (survivor count), scan_error or scan_dump (addresses + values). Survivors of a dump
-- are also added to the table under "Orcish scan hits", so the bridge streams their values from then on.

local OUTPUT = ORCISH_SCOUT_CE_OUTPUT or [[C:\Temp\cheat_engine.jsonl]]
local COMMANDS = ORCISH_SCOUT_CE_COMMANDS   -- nil disables the scan assistant
local INTERVAL = tonumber(ORCISH_SCOUT_CE_INTERVAL) or 100
local DUMP_ADD_LIMIT = 16                    -- add survivors to the table only when this few remain
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

-- ---------------------------------------------------------------------------------------------
-- Scan assistant: commands from Orcish -> Cheat Engine memscan -> replies on the stream.
-- ---------------------------------------------------------------------------------------------
local VAR_TYPES = { ["4 Bytes"] = vtDword, ["Byte"] = vtByte, ["2 Bytes"] = vtWord, ["Float"] = vtSingle }
local scan = nil
local scan_var_type = nil
local scan_count = nil
local commands_offset = nil

local function reply(signal, value, seq, extra)
    local e = extra or {}
    e.seq = seq
    emit(signal, value, e)
    flush()
end

local function count_results()
    local fl = createFoundList(scan)
    fl.initialize()
    local n = fl.Count
    fl.deinitialize()
    return n
end

local function run_first(seq, var_type)
    local vt = VAR_TYPES[var_type]
    if not vt then reply("scan_error", "unknown value type " .. tostring(var_type), seq); return end
    if scan then pcall(function() scan.destroy() end) end
    scan = createMemScan()
    scan_var_type = vt
    scan_count = nil
    -- Unknown initial value over writable, non copy-on-write memory, aligned to the value size.
    local align = ({ ["Byte"] = "1", ["2 Bytes"] = "2" })[var_type] or "4"
    scan.firstScan(soUnknownValue, vt, rtRounded, "", "", 0, 0x7fffffffffffffff, "*X+W-C", fsmAligned,
                   align, false, false, false, false)
    scan.waitTillDone()
    reply("scan_result", nil, seq, { cmd = "first", var_type = var_type })
end

local function run_next(seq, how)
    if not scan then reply("scan_error", "no first scan yet", seq); return end
    local option = (how == "changed") and soChanged or (how == "unchanged") and soUnchanged or nil
    if not option then reply("scan_error", "unknown next-scan mode " .. tostring(how), seq); return end
    scan.nextScan(option, rtRounded, "", "", false, false, false, false, false)
    scan.waitTillDone()
    scan_count = count_results()
    reply("scan_result", scan_count, seq, { cmd = "next", arg = how })
end

local function run_dump(seq, limit)
    if not scan then reply("scan_error", "no scan to dump", seq); return end
    limit = tonumber(limit) or 64
    local fl = createFoundList(scan)
    fl.initialize()
    local n = fl.Count
    local hits = {}
    for i = 0, math.min(n, limit) - 1 do
        hits[#hits + 1] = { address = fl.Address[i], value = typed(fl.Value[i]) }
    end
    fl.deinitialize()
    reply("scan_dump", n, seq, { cmd = "dump", hits = hits })
    if n > 0 and n <= DUMP_ADD_LIMIT then
        local al = getAddressList()
        local group = al.createMemoryRecord()
        group.Description = "Orcish scan hits (" .. os.date("%H:%M:%S") .. ")"
        group.IsGroupHeader = true
        for i, h in ipairs(hits) do
            local mr = al.createMemoryRecord()
            mr.Description = string.format("scan hit %d @ %s", i, h.address)
            mr.Address = h.address
            mr.Type = scan_var_type or vtDword
            mr.appendToEntry(group)
        end
    end
end

local function handle_command(line)
    local fields = {}
    for field in (line .. "\t"):gmatch("([^\t]*)\t") do fields[#fields + 1] = field end
    local seq, cmd, arg, var_type = tonumber(fields[1]), fields[2], fields[3], fields[4]
    if not seq or not cmd then return end
    local ok, err = pcall(function()
        if cmd == "first" then run_first(seq, var_type)
        elseif cmd == "next" then run_next(seq, arg)
        elseif cmd == "dump" then run_dump(seq, arg)
        elseif cmd == "reset" then
            if scan then pcall(function() scan.destroy() end) end
            scan = nil; scan_count = nil
            reply("scan_result", nil, seq, { cmd = "reset" })
        else reply("scan_error", "unknown command " .. tostring(cmd), seq) end
    end)
    if not ok then reply("scan_error", tostring(err), seq, { cmd = cmd }) end
end

local function poll_commands()
    if not COMMANDS then return end
    local f = io.open(COMMANDS, "rb")
    if not f then
        -- No file yet: whatever Orcish writes later is new, read it from the start.
        if commands_offset == nil then commands_offset = 0 end
        return
    end
    if commands_offset == nil then
        -- Commands written before this bridge started belong to an earlier session.
        f:seek("end"); commands_offset = f:seek("cur"); f:close(); return
    end
    local size = f:seek("end")
    if size < commands_offset then commands_offset = 0 end   -- file was recreated
    f:seek("set", commands_offset)
    local data = f:read("*a") or ""
    commands_offset = f:seek("cur")
    f:close()
    for line in data:gmatch("[^\r\n]+") do handle_command(line) end
end

local timer = nil
local hotkey = nil

OrcishScoutCE = {}

function OrcishScoutCE.stop()
    if timer then timer.Enabled = false; timer.destroy(); timer = nil end
    if hotkey then pcall(function() hotkey.destroy() end); hotkey = nil end
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
        local ok2, err2 = pcall(poll_commands)
        if not ok2 then emit("bridge_error", "commands: " .. tostring(err2)); flush() end
    end
    timer.Enabled = true
    if not hotkey then
        pcall(function()
            hotkey = createHotkey(function() OrcishScoutCE.mark("hotkey") end, VK_F9)
        end)
    end
    print("[OrcishScout] Cheat Engine bridge writing to " .. OUTPUT)
    if COMMANDS then print("[OrcishScout] scan assistant listening on " .. COMMANDS) end
end

function OrcishScoutCE.mark(text)
    emit("mark", tostring(text or "mark")); flush()
end

OrcishScoutCE.start()
