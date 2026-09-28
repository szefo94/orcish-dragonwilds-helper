"""Convert Cheat Engine table (.CT) records into Scout read-only watch specs.

Usage:  ce_table.py <table.CT>      prints one 'name<TAB>spec' line per convertible record

A record's <Address> is Cheat Engine text: '"module.exe"+04A1230', 'module.exe+4A1230' or an
absolute hex address, always hex without 0x. Pointer records add <Offsets>; Cheat Engine stores
them with the offset applied LAST first (index 0 is the one closest to the value), so the chain
is built from the end of the list. Script, string, byte-array and symbol-based records are
reported as skipped rather than guessed.
"""
from __future__ import annotations
import re, sys
import xml.etree.ElementTree as ET

from pointer_chain import format_ops

_TYPES = {"byte": "u8", "2 bytes": "u16", "4 bytes": "u32", "8 bytes": "u64", "float": "f32", "double": "f64"}
_SIGNED = {"u32": "i32", "u64": "i64"}
_MODULE_ADDR = re.compile(r'^\s*(?:"([^"]+)"|([\w.\-]+?\.(?:exe|dll)))\s*\+\s*([0-9A-Fa-f]+)\s*$', re.I)
_ABS_ADDR = re.compile(r'^\s*([0-9A-Fa-f]+)\s*$')


def _text(node, tag):
    child = node.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def record_spec(address, offsets, variable_type, signed=False):
    """Build a Scout spec from Cheat Engine record fields; raises ValueError when unsupported."""
    typ = _TYPES.get((variable_type or "").strip().lower())
    if not typ: raise ValueError(f"unsupported type {variable_type or '?'}")
    if signed: typ = _SIGNED.get(typ, typ)
    m = _MODULE_ADDR.match(address or "")
    if m:
        base = [("module", (m.group(1) or m.group(2)).lower()), ("add", int(m.group(3), 16))]
    elif _ABS_ADDR.match(address or ""):
        base = [("abs", int(address.strip(), 16))]
    else:
        raise ValueError(f"unsupported address {address!r} (symbols/AOB labels are not resolved)")
    if not offsets:
        if base[0][0] == "module": return f"{base[0][1]}+0x{base[1][1]:X}:{typ}"
        return f"0x{base[0][1]:X}:{typ}"
    ops = base + [("deref",)]
    for off in reversed(offsets):          # index 0 is applied last
        ops += [("add", int(off, 16)), ("deref",)]
    ops = ops[:-1]                          # the final offset addresses the value itself
    return f"{format_ops(ops)}:{typ}"


def parse_cheat_table(xml_text):
    """Return (records, skipped): records [{"name","spec"}], skipped [{"name","reason"}]."""
    root = ET.fromstring(xml_text)
    records, skipped = [], []
    for entry in root.iter("CheatEntry"):
        name = _text(entry, "Description").strip('"') or f"record {_text(entry, 'ID')}"
        if _text(entry, "GroupHeader") == "1" and not _text(entry, "Address"): continue
        vtype = _text(entry, "VariableType")
        if vtype.lower() == "auto assembler script":
            skipped.append({"name": name, "reason": "script entry"}); continue
        offsets_node = entry.find("Offsets")
        offsets = [(o.text or "").strip() for o in offsets_node.findall("Offset")] if offsets_node is not None else []
        try:
            if any(not re.fullmatch(r"[0-9A-Fa-f]+", o) for o in offsets):
                raise ValueError("symbolic pointer offset")
            spec = record_spec(_text(entry, "Address"), offsets, vtype, _text(entry, "ShowAsSigned") == "1")
        except ValueError as e:
            skipped.append({"name": name, "reason": str(e)}); continue
        records.append({"name": name, "spec": spec})
    return records, skipped


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        records, skipped = parse_cheat_table(f.read())
    for r in records: print(f"{r['name']}\t{r['spec']}")
    for s in skipped: print(f"# skipped {s['name']}: {s['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
