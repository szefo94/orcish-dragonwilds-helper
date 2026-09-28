"""Research edition data sources: default telemetry files, the Cheat Engine starter table,
the UE4SS hooks file, and a status check of what each source has actually written.

Usage (Setup.cmd calls this):  research_setup.py prepare | status | scans
- prepare  creates missing research files under data/; never overwrites user content. The
           Cheat Engine table only has its marked loader block refreshed (paths move when the
           folder is re-extracted); your addresses in the table are left untouched.
- status   reports each JSONL source: present, line count, last signal and its age.
- scans    lists UFunction names from the newest UE4SS object scan as ready-to-paste hook lines.
"""
from __future__ import annotations
from pathlib import Path
from xml.sax.saxutils import escape
import json, re, sys, time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paths import ROOT, DATA   # noqa: E402

LOADER_BEGIN = "-- ORCISH-SCOUT-LOADER BEGIN (managed by Orcish Setup; your own Lua goes below the END line)"
LOADER_END = "-- ORCISH-SCOUT-LOADER END"
_LOADER_RE = re.compile(re.escape("-- ORCISH-SCOUT-LOADER BEGIN") + r".*?" + re.escape(LOADER_END), re.S)


def ue4ss_output(data=DATA): return Path(data) / "ue4ss" / "orcish_scout_ue4ss.jsonl"
def ue4ss_hooks(data=DATA): return Path(data) / "ue4ss" / "orcish_hooks.txt"
def ue4ss_scans(data=DATA): return Path(data) / "ue4ss" / "scans"
def ce_output(data=DATA): return Path(data) / "telemetry" / "cheat_engine.jsonl"
def ce_table(data=DATA): return Path(data) / "cheat-engine" / "OrcishScout.CT"
def ce_script(root=ROOT): return Path(root) / "tools" / "cheat-engine" / "orcish_scout_ce.lua"


def default_bridge_paths(data=DATA):
    """JSONL files Scout reads when the user has not configured bridge paths."""
    return [str(ue4ss_output(data)), str(ce_output(data))]


HOOKS_TEMPLATE = """\
# Orcish Scout UE4SS hooks. Read by the OrcishScout UE4SS mod when the game starts.
# This file lives in data/ and is never overwritten by Setup or updates.
#
# function <label> = <full UFunction path>   log every call of that UFunction
# property <label> = <Class>.<Property>       poll a property of the first live instance; log changes
# scan <text>                                 name filter for the Ctrl+F10 object scan
# poll_ms <milliseconds>                      property poll interval (default 250)
#
# Find names with Ctrl+F10 in game (writes data/ue4ss/scans/), then run:
#   Setup.cmd scans
# Placeholder examples (remove the leading '#' only after you confirm the names exist):
# function fish_bite = /Game/Path/BP_Fishing.BP_Fishing_C:OnFishBite
# property fishing_state = BP_FishingComponent_C.FishingState

scan Fish
scan Reel
scan Bait
scan Rod
"""


def ensure_hooks_file(data=DATA):
    p = ue4ss_hooks(data)
    if p.exists(): return "exists"
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(HOOKS_TEMPLATE, encoding="utf-8")
    return "created"


def _lua_long(s):
    """Lua long-bracket string literal that cannot be closed early by the path contents."""
    level = 1
    while ("]" + "=" * level + "]") in s: level += 1
    eq = "=" * level
    return f"[{eq}[{s}]{eq}]"


def loader_block(root=ROOT, data=DATA):
    return "\n".join([
        LOADER_BEGIN,
        f"ORCISH_SCOUT_CE_OUTPUT = {_lua_long(str(ce_output(data)))}",
        f"dofile({_lua_long(str(ce_script(root)))})",
        LOADER_END,
    ])


def render_cheat_table(root=ROOT, data=DATA):
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<CheatTable CheatEngineTableVersion="42">\n'
            '  <CheatEntries>\n'
            '  </CheatEntries>\n'
            '  <UserdefinedSymbols/>\n'
            f'  <LuaScript>{escape(loader_block(root, data))}\n</LuaScript>\n'
            '</CheatTable>\n')


def ensure_cheat_table(root=ROOT, data=DATA):
    """Create the starter table, or refresh only its loader block. Returns what happened."""
    p = ce_table(data)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(render_cheat_table(root, data), encoding="utf-8")
        return "created"
    text = p.read_text(encoding="utf-8", errors="replace")
    # The markers contain no XML-special characters, so they match the escaped form in the file.
    if not _LOADER_RE.search(text): return "unmanaged"
    new = _LOADER_RE.sub(lambda _m: escape(loader_block(root, data)), text, count=1)
    if new == text: return "unchanged"
    p.write_text(new, encoding="utf-8")
    return "refreshed"


def prepare(root=ROOT, data=DATA):
    for d in (ue4ss_output(data).parent, ce_output(data).parent, ue4ss_scans(data)):
        d.mkdir(parents=True, exist_ok=True)
    return {"hooks_file": ensure_hooks_file(data), "cheat_table": ensure_cheat_table(root, data)}


def _tail_lines(path, max_bytes=65536):
    with open(path, "rb") as f:
        f.seek(0, 2); size = f.tell(); f.seek(max(0, size - max_bytes))
        chunk = f.read().decode("utf-8", errors="replace")
    lines = chunk.splitlines()
    return lines[1:] if size > max_bytes and lines else lines


def source_status(path, now=None):
    p = Path(path); now = time.time() if now is None else now
    out = {"path": str(p), "exists": p.exists(), "lines": 0, "last_signal": None, "last_provider": None,
           "age_s": None, "signals": []}
    if not out["exists"]: return out
    with open(p, "rb") as f: out["lines"] = sum(1 for _ in f)
    out["age_s"] = round(max(0.0, now - p.stat().st_mtime), 1)
    seen = []
    for line in _tail_lines(p):
        try: obj = json.loads(line)
        except Exception: continue
        sig = obj.get("signal")
        if sig and sig not in seen: seen.append(sig)
        out["last_signal"] = sig; out["last_provider"] = obj.get("provider")
    out["signals"] = seen
    return out


def status(root=ROOT, data=DATA, now=None):
    return {"ue4ss": source_status(ue4ss_output(data), now), "cheat_engine": source_status(ce_output(data), now),
            "hooks_file": ue4ss_hooks(data).exists(), "cheat_table": ce_table(data).exists(),
            "ce_script": ce_script(root).exists(), "latest_scan": str(latest_scan(data) or "") or None}


def latest_scan(data=DATA):
    d = ue4ss_scans(data)
    files = sorted(d.glob("scan_*.jsonl"), key=lambda p: p.stat().st_mtime) if d.exists() else []
    return files[-1] if files else None


def hook_suggestions(scan_path, limit=200):
    """Unique UFunction hook names from one scan file, as 'function <label> = <path>' lines."""
    out, seen = [], set()
    with open(scan_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try: obj = json.loads(line)
            except Exception: continue
            name = obj.get("hook_name")
            if obj.get("kind") != "function" or not name or name in seen: continue
            seen.add(name)
            label = re.sub(r"[^a-z0-9]+", "_", name.rsplit(":", 1)[-1].lower()).strip("_") or "fn"
            out.append(f"function {label} = {name}")
            if len(out) >= limit: break
    return out


def _print_source(title, s):
    if not s["exists"]:
        print(f"[MISS] {title}: no data yet ({s['path']})"); return
    age = s["age_s"]; fresh = age is not None and age < 120
    tag = "[OK]  " if fresh else "[WARN]"
    print(f"{tag} {title}: {s['lines']} lines, last '{s['last_signal']}' {age:.0f}s ago ({s['path']})")
    if s["signals"]: print(f"       recent signals: {', '.join(s['signals'][:12])}")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "prepare":
        r = prepare()
        print(f"[OK]   UE4SS hooks file: {r['hooks_file']} ({ue4ss_hooks()})")
        if r["cheat_table"] == "unmanaged":
            print(f"[WARN] {ce_table()} has no Orcish loader block; left unchanged.")
        else:
            print(f"[OK]   Cheat Engine starter table: {r['cheat_table']} ({ce_table()})")
        print(f"[OK]   Scout reads: {'; '.join(default_bridge_paths())}")
        return 0
    if cmd == "status":
        s = status()
        print("\n=== Research data sources ===")
        _print_source("UE4SS stream", s["ue4ss"])
        if s["ue4ss"]["exists"] and "bridge_ready" not in s["ue4ss"]["signals"] and s["ue4ss"]["lines"] < 200:
            print("       no bridge_ready in recent lines: check the UE4SS log section above.")
        _print_source("Cheat Engine stream", s["cheat_engine"])
        print(("[OK]   " if s["hooks_file"] else "[MISS] ") + f"UE4SS hooks file: {ue4ss_hooks()}")
        print(("[OK]   " if s["cheat_table"] else "[MISS] ") + f"Cheat Engine starter table: {ce_table()}")
        if not s["ce_script"]: print(f"[MISS] Cheat Engine bridge script: {ce_script()}")
        if s["latest_scan"]: print(f"[OK]   Latest UE4SS object scan: {s['latest_scan']}")
        return 0
    if cmd == "scans":
        scan = latest_scan()
        if not scan:
            print("No UE4SS object scan yet. In game press Ctrl+F10 (OrcishScout mod), then run this again."); return 1
        lines = hook_suggestions(scan)
        print(f"# {len(lines)} UFunction(s) from {scan}")
        print("# Copy the lines you want into " + str(ue4ss_hooks()) + " and restart the game.")
        for x in lines: print(x)
        return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
