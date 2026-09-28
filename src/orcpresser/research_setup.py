"""Research edition data sources: default telemetry files, the Cheat Engine starter table,
and a status check of what each source has actually written.

Usage (Setup.cmd option 7/8 call this):  research_setup.py prepare | status
- prepare  creates missing research files under data/; never overwrites user content. The
           Cheat Engine table only has its marked loader block refreshed (paths move when the
           folder is re-extracted); your addresses in the table are left untouched.
- status   reports each JSONL source: present, line count, last signal and its age.
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
def ce_output(data=DATA): return Path(data) / "telemetry" / "cheat_engine.jsonl"
def ce_table(data=DATA): return Path(data) / "cheat-engine" / "OrcishScout.CT"
def ce_script(root=ROOT): return Path(root) / "tools" / "cheat-engine" / "orcish_scout_ce.lua"


def default_bridge_paths(data=DATA):
    """JSONL files Scout reads when the user has not configured bridge paths."""
    return [str(ce_output(data)), str(ue4ss_output(data))]


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
    ce_output(data).parent.mkdir(parents=True, exist_ok=True)
    return {"cheat_table": ensure_cheat_table(root, data)}


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
    return {"cheat_engine": source_status(ce_output(data), now), "ue4ss": source_status(ue4ss_output(data), now),
            "cheat_table": ce_table(data).exists(), "ce_script": ce_script(root).exists()}


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
        if r["cheat_table"] == "unmanaged":
            print(f"[WARN] {ce_table()} has no Orcish loader block; left unchanged.")
        else:
            print(f"[OK]   Cheat Engine starter table: {r['cheat_table']} ({ce_table()})")
        print(f"[OK]   Scout reads: {'; '.join(default_bridge_paths())}")
        return 0
    if cmd == "status":
        s = status()
        print("\n=== Research data sources ===")
        _print_source("Cheat Engine stream", s["cheat_engine"])
        print(("[OK]   " if s["cheat_table"] else "[MISS] ") + f"Cheat Engine starter table: {ce_table()}")
        if not s["ce_script"]: print(f"[MISS] Cheat Engine bridge script: {ce_script()}")
        _print_source("UE4SS stream (parked; see docs/INTERNAL_TELEMETRY.md)", s["ue4ss"])
        return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
