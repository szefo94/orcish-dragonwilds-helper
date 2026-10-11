"""Research edition data sources: default telemetry files, the Cheat Engine starter table,
and a status check of what each source has actually written.

Usage (Setup.cmd options 7/8/D call this):  research_setup.py prepare | status | doctor | report
- prepare  creates missing research files under data/; never overwrites user content. The
           Cheat Engine table only has its marked loader block refreshed (paths move when the
           folder is re-extracted); your addresses in the table are left untouched.
- status   reports each JSONL source: present, line count, last signal and its age.
- doctor   one-screen check of the whole Fishing + Cheat Engine data path (prepare + status +
           candidates + latest session) with the next step to take.
- report   writes the analyzer report for the latest Scout session (same as SCOUT LAB → ANALYZE).
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
def ce_commands(data=DATA): return Path(data) / "telemetry" / "cheat_engine_commands.tsv"
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
        f"ORCISH_SCOUT_CE_COMMANDS = {_lua_long(str(ce_commands(data)))}",
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


def source_status(path, now=None, quick=False):
    """quick=True skips the full line count (cheap enough to call from the UI every few seconds)."""
    p = Path(path); now = time.time() if now is None else now
    out = {"path": str(p), "exists": p.exists(), "lines": None if quick else 0, "last_signal": None, "last_provider": None,
           "age_s": None, "signals": []}
    if not out["exists"]: return out
    if not quick:
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


def status(root=ROOT, data=DATA, now=None, quick=False):
    return {"cheat_engine": source_status(ce_output(data), now, quick), "ue4ss": source_status(ue4ss_output(data), now, quick),
            "cheat_table": ce_table(data).exists(), "ce_script": ce_script(root).exists()}


def _settings_candidates(data=DATA):
    """Semantic candidates saved by SCOUT LAB, grouped by domain (settings.json is never modified here)."""
    try: raw = json.loads((Path(data) / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}
    out = {}
    for section in (raw or {}).values():
        if not isinstance(section, dict): continue
        for c in section.get("scout_memory_candidates") or []:
            if isinstance(c, dict): out[c.get("domain", "?")] = out.get(c.get("domain", "?"), 0) + 1
    return out


def _latest_session_summary(data=DATA):
    root = Path(data) / "scout_sessions"
    if not root.is_dir(): return None
    dirs = [x for x in root.iterdir() if x.is_dir() and (x / "manifest.json").is_file()]
    if not dirs: return None
    s = max(dirs, key=lambda x: x.stat().st_mtime)
    try: manifest = json.loads((s / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): manifest = {}
    def count(name):
        p = s / name
        if not p.is_file(): return 0
        with open(p, "rb") as f: return sum(1 for _ in f)
    internal = 0
    p = s / "process.jsonl"
    if p.is_file():
        with open(p, "rb") as f: internal = sum(1 for line in f if b'"game_internal"' in line)
    return {"path": str(s), "name": s.name, "domain": manifest.get("domain"), "run": manifest.get("run"),
            "vision": count("vision.jsonl"), "controller": count("controller.jsonl"), "memory": count("memory.jsonl"),
            "game_internal": internal, "age_s": round(max(0.0, time.time() - s.stat().st_mtime), 1)}


def doctor(root=ROOT, data=DATA, now=None):
    """Everything the Fishing + Cheat Engine research path needs, with one suggested next step."""
    prepared = prepare(root, data)
    s = status(root, data, now)
    cands = _settings_candidates(data)
    latest = _latest_session_summary(data)
    steps = []
    ce = s["cheat_engine"]
    if not s["ce_script"]: steps.append("tools\\cheat-engine\\orcish_scout_ce.lua is missing: re-extract the Research POC ZIP.")
    if not ce["exists"]: steps.append("Open data\\cheat-engine\\OrcishScout.CT in Cheat Engine (answer Yes to the Lua script) with Dragonwilds running.")
    elif ce["age_s"] is not None and ce["age_s"] > 120: steps.append("Cheat Engine stream is stale: reopen OrcishScout.CT or check the Lua Engine window.")
    elif ce["signals"] and "property_change" not in ce["signals"] and "scan_result" not in ce["signals"]:
        steps.append("Stream is alive but no record values yet: add addresses to the table, or enable the scan assistant in SCOUT LAB.")
    if not cands: steps.append("No semantic candidates saved yet: save the table in Cheat Engine; Fishing auto-imports it at start (SCOUT LAB).")
    if latest is None: steps.append("No Scout session yet: start Fishing (PREVIEW or LIVE) with the game bound.")
    elif latest["domain"] == "fishing" and not latest["memory"] and not latest["game_internal"]:
        steps.append("Latest Fishing session has no memory or Cheat Engine data: check 'Run independent Scout probes' and 'Read JSONL bridges' in SCOUT LAB.")
    if not steps: steps.append("All sources present. Fish 10-20 rounds, then run 'report' (or SCOUT LAB -> ANALYZE LATEST SESSION).")
    return {"prepared": prepared, "status": s, "candidates": cands, "latest_session": latest, "next_steps": steps}


def report(data=DATA):
    """Analyze the latest session; returns (markdown_path, report) or (None, None)."""
    sys.path.insert(0, str(HERE))
    from scout_analysis import latest_session, write_report
    try: latest = latest_session(str(data))
    except (FileNotFoundError, OSError): return None, None
    _jp, mp, r = write_report(latest, str(data))
    return mp, r


def _print_source(title, s):
    if not s["exists"]:
        print(f"[MISS] {title}: no data yet ({s['path']})"); return
    age = s["age_s"]; fresh = age is not None and age < 120
    tag = "[OK]  " if fresh else "[WARN]"
    print(f"{tag} {title}: {s['lines']} lines, last '{s['last_signal']}' {age:.0f}s ago ({s['path']})")
    if s["signals"]: print(f"       recent signals: {', '.join(s['signals'][:12])}")


def main(argv):
    # Setup.cmd runs this in a cmd.exe console whose code page cannot show every character in a path or
    # signal name; never let a print() crash the check.
    for stream in (sys.stdout, sys.stderr):
        try: stream.reconfigure(errors="replace")
        except (AttributeError, ValueError): pass
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
    if cmd == "doctor":
        d = doctor()
        print("\n=== Research data check ===")
        print(f"[OK]   Cheat Engine table: {d['prepared']['cheat_table']} ({ce_table()})")
        _print_source("Cheat Engine stream", d["status"]["cheat_engine"])
        cands = d["candidates"]
        print(("[OK]   " if cands else "[MISS] ") + "Semantic candidates: " + (", ".join(f"{k}={v}" for k, v in sorted(cands.items())) or "none"))
        latest = d["latest_session"]
        if latest:
            print(f"[OK]   Latest session: {latest['name']} ({latest['domain']}/{latest['run']}, {latest['age_s']:.0f}s ago) "
                  f"vision={latest['vision']} controller={latest['controller']} memory={latest['memory']} cheat_engine={latest['game_internal']}")
        else: print("[MISS] Latest session: none")
        print("\nNext step:")
        for step in d["next_steps"]: print("  - " + step)
        return 0
    if cmd == "report":
        mp, r = report()
        if not mp: print("[MISS] No Scout session to analyze yet."); return 1
        f = (r or {}).get("fishing") or {}
        print(f"[OK]   Report: {mp}")
        if f: print(f"       fishing observations={f.get('observations')} REEL entries={f.get('reel_entries')} transitions={len(f.get('state_transitions') or [])}")
        if (r or {}).get("shadow_agreement"): print(f"       shadow agreement rows={len(r['shadow_agreement'])}")
        return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
