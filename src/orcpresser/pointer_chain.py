"""Pointer-chain addresses in Cheat Engine bracket notation, for read-only memory watches.

    [[RSDragonwilds-WinGDK-Shipping.exe+0x4A1230]+0x10]+0x88

'[x]' reads the 8-byte pointer stored at x; '+'/'-' add an offset. The base is a module
(name ending in .exe/.dll, optionally in double quotes) or an absolute 0x address. Every
number must be 0x-prefixed hex: Cheat Engine displays offsets in hex, and a bare '10'
would otherwise be silently misread as decimal.

Parsing produces a flat list of ops evaluated left to right:
    ("module", name) | ("abs", n)   set the current address
    ("add", n)                       current += n
    ("deref",)                       current = pointer read at current
Evaluation is pure: the caller supplies module lookup and pointer reads, so Scout's
ReadOnlyMemory stays the only code that touches another process.
"""
from __future__ import annotations
import re

MAX_DEREFS = 12
_TOKEN = re.compile(r'\s*(?:(?P<br>[\[\]])|(?P<op>[+-])|"(?P<qmod>[^"]+)"|(?P<num>0[xX][0-9A-Fa-f]+)'
                    r'|(?P<mod>[A-Za-z0-9_][\w.\-]*?\.(?:exe|dll))(?![\w.])|(?P<bad>\S+?(?=[\[\]+\s]|$)))')


def is_pointer_expr(text):
    return "[" in (text or "")


def _tokens(text):
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip() == "": break
            raise ValueError(f"Cannot read pointer expression near: {text[pos:pos+20]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "bad":
            tok = m.group("bad")
            if re.fullmatch(r"[0-9A-Fa-f]+", tok):
                raise ValueError(f"Offset {tok!r} needs 0x (Cheat Engine shows hex): write 0x{tok}")
            raise ValueError(f"Unknown term {tok!r}: use MODULE.exe/.dll, 0xADDRESS or 0xOFFSET")
        value = m.group(kind)
        out.append(("mod" if kind == "qmod" else kind, value))
    return out


def parse_pointer_expr(text):
    """Return ops for a bracket expression; raises ValueError with a user-facing message."""
    toks = _tokens((text or "").strip()); i = 0

    def expr(depth):
        nonlocal i
        ops = atom(depth)
        while i < len(toks) and toks[i][0] == "op":
            sign = -1 if toks[i][1] == "-" else 1; i += 1
            if i >= len(toks) or toks[i][0] != "num":
                raise ValueError("Expected a 0x offset after '+' or '-'")
            ops.append(("add", sign * int(toks[i][1], 16))); i += 1
        return ops

    def atom(depth):
        nonlocal i
        if i >= len(toks): raise ValueError("Pointer expression ends too early")
        kind, value = toks[i]
        if kind == "br" and value == "[":
            i += 1
            inner = expr(depth + 1)
            if i >= len(toks) or toks[i] != ("br", "]"): raise ValueError("Missing ']'")
            i += 1
            return inner + [("deref",)]
        if depth == 0 and kind != "br":
            raise ValueError("A pointer expression must start with '['")
        if kind == "mod":
            i += 1; return [("module", value.lower())]
        if kind == "num":
            n = int(value, 16)
            if n <= 0: raise ValueError("Absolute base address must be positive")
            i += 1; return [("abs", n)]
        raise ValueError(f"Unexpected {value!r}")

    ops = expr(0)
    if i != len(toks): raise ValueError(f"Unexpected {toks[i][1]!r} after the expression")
    derefs = sum(1 for op in ops if op[0] == "deref")
    if derefs > MAX_DEREFS: raise ValueError(f"At most {MAX_DEREFS} pointer levels are supported")
    return ops


def format_ops(ops):
    """Canonical text for ops (round-trips through parse_pointer_expr)."""
    text = ""
    for op in ops:
        if op[0] == "module": text += op[1]
        elif op[0] == "abs": text += f"0x{op[1]:X}"
        elif op[0] == "add": text += f"{'-' if op[1] < 0 else '+'}0x{abs(op[1]):X}"
        elif op[0] == "deref": text = f"[{text}]"
    return text


def resolve_ops(ops, module_base, read_pointer):
    """Evaluate ops. module_base(name)->int|None, read_pointer(addr)->int|None.

    Returns {"ok": True, "address": final, "trail": [...]} or {"ok": False, "error": ..., "trail": [...]}.
    The trail lists each address a pointer was read from and the pointer found there, so a broken
    chain shows which level failed.
    """
    current = None; trail = []
    for op in ops:
        kind = op[0]
        if kind == "module":
            current = module_base(op[1])
            if not current: return {"ok": False, "error": "module_not_found", "module": op[1], "trail": trail}
        elif kind == "abs":
            current = op[1]
        elif kind == "add":
            current += op[1]
        elif kind == "deref":
            value = read_pointer(current)
            trail.append({"at": current, "pointer": value})
            if value is None: return {"ok": False, "error": "pointer_read_failed", "level": len(trail), "trail": trail}
            if value == 0: return {"ok": False, "error": "null_pointer", "level": len(trail), "trail": trail}
            current = value
    return {"ok": True, "address": current, "trail": trail}
