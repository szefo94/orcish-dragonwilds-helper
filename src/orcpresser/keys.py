"""Key names -> Windows input codes. Used by the key dropdown (Repeat / Hold) and by WinIO.

A Key is either a mouse button (mouse_event flags) or a keyboard key (virtual-key code plus the
'extended' flag that arrows, navigation keys, right-side modifiers and some numpad keys need).
Any name from the dropdown, common aliases ('LMB', 'LButton', 'Mouse 4', 'PgUp'...), a single
letter/digit, or F1-F24 resolves to the same Key.
"""
import re
from collections import namedtuple

Key = namedtuple('Key', 'name kind vk down up data extended')   # kind: 'mouse' | 'key'

RESERVED_VK = {0x77: 'F8 (panic stop)', 0xDC: 'backslash (start/stop hotkey)'}

_MOUSE = {
    'LMB': (0x0002, 0x0004, 0), 'RMB': (0x0008, 0x0010, 0), 'MMB': (0x0020, 0x0040, 0),
    'Mouse 4': (0x0080, 0x0100, 1), 'Mouse 5': (0x0080, 0x0100, 2),   # XBUTTON1 / XBUTTON2
}
_VK = {
    'Space': (0x20, 0), 'Enter': (0x0D, 0), 'Tab': (0x09, 0), 'Esc': (0x1B, 0), 'Backspace': (0x08, 0),
    'Shift': (0xA0, 0), 'Ctrl': (0xA2, 0), 'Alt': (0xA4, 0),
    'Right Shift': (0xA1, 0), 'Right Ctrl': (0xA3, 1), 'Right Alt': (0xA5, 1), 'Caps Lock': (0x14, 0),
    'Up': (0x26, 1), 'Down': (0x28, 1), 'Left': (0x25, 1), 'Right': (0x27, 1),
    'Insert': (0x2D, 1), 'Delete': (0x2E, 1), 'Home': (0x24, 1), 'End': (0x23, 1),
    'Page Up': (0x21, 1), 'Page Down': (0x22, 1),
    'Numpad 0': (0x60, 0), 'Numpad 1': (0x61, 0), 'Numpad 2': (0x62, 0), 'Numpad 3': (0x63, 0),
    'Numpad 4': (0x64, 0), 'Numpad 5': (0x65, 0), 'Numpad 6': (0x66, 0), 'Numpad 7': (0x67, 0),
    'Numpad 8': (0x68, 0), 'Numpad 9': (0x69, 0), 'Numpad +': (0x6B, 0), 'Numpad -': (0x6D, 0),
    'Numpad *': (0x6A, 0), 'Numpad /': (0x6F, 1), 'Numpad .': (0x6E, 0),
    '`': (0xC0, 0), '-': (0xBD, 0), '=': (0xBB, 0), '[': (0xDB, 0), ']': (0xDD, 0),
    ';': (0xBA, 0), "'": (0xDE, 0), ',': (0xBC, 0), '.': (0xBE, 0), '/': (0xBF, 0),
}
_ALIASES = {
    'LBUTTON': 'LMB', 'LEFT MOUSE': 'LMB', 'LEFT CLICK': 'LMB', 'MOUSE1': 'LMB', 'MOUSE 1': 'LMB',
    'RBUTTON': 'RMB', 'RIGHT MOUSE': 'RMB', 'RIGHT CLICK': 'RMB', 'MOUSE2': 'RMB', 'MOUSE 2': 'RMB',
    'MBUTTON': 'MMB', 'MIDDLE MOUSE': 'MMB', 'WHEEL CLICK': 'MMB', 'MOUSE3': 'MMB', 'MOUSE 3': 'MMB',
    'MOUSE4': 'Mouse 4', 'XBUTTON1': 'Mouse 4', 'MOUSE BACK': 'Mouse 4', 'BACK': 'Mouse 4',
    'MOUSE5': 'Mouse 5', 'XBUTTON2': 'Mouse 5', 'MOUSE FORWARD': 'Mouse 5', 'FORWARD': 'Mouse 5',
    'SPACEBAR': 'Space', 'RETURN': 'Enter', 'ESCAPE': 'Esc', 'BKSP': 'Backspace',
    'LSHIFT': 'Shift', 'LEFT SHIFT': 'Shift', 'RSHIFT': 'Right Shift', 'CONTROL': 'Ctrl', 'LCTRL': 'Ctrl',
    'LEFT CTRL': 'Ctrl', 'RCTRL': 'Right Ctrl', 'LALT': 'Alt', 'LEFT ALT': 'Alt', 'RALT': 'Right Alt',
    'ALTGR': 'Right Alt', 'CAPSLOCK': 'Caps Lock', 'CAPS': 'Caps Lock',
    'ARROW UP': 'Up', 'UP ARROW': 'Up', 'ARROW DOWN': 'Down', 'DOWN ARROW': 'Down',
    'ARROW LEFT': 'Left', 'LEFT ARROW': 'Left', 'ARROW RIGHT': 'Right', 'RIGHT ARROW': 'Right',
    'INS': 'Insert', 'DEL': 'Delete', 'PGUP': 'Page Up', 'PAGEUP': 'Page Up', 'PGDN': 'Page Down',
    'PAGEDOWN': 'Page Down', 'PAGE DN': 'Page Down', 'TILDE': '`', 'GRAVE': '`',
}
for n in range(10): _ALIASES[f'NUM{n}'] = _ALIASES[f'NUMPAD{n}'] = _ALIASES[f'NUM {n}'] = f'Numpad {n}'


def dropdown():
    """Names offered in the key dropdown (letters/digits can simply be typed)."""
    mouse = list(_MOUSE)
    common = ['Space', 'Enter', 'Tab', 'Esc', 'Backspace', 'Shift', 'Ctrl', 'Alt', 'Caps Lock',
              'Up', 'Down', 'Left', 'Right', 'Insert', 'Delete', 'Home', 'End', 'Page Up', 'Page Down']
    fkeys = [f'F{i}' for i in range(1, 25) if i != 8]
    numpad = [k for k in _VK if k.startswith('Numpad')]
    extra = ['Right Shift', 'Right Ctrl', 'Right Alt']
    return mouse + common + fkeys + numpad + extra


def canonical(name):
    """Normalize user text to a dropdown name, or a single upper-case letter/digit."""
    s = re.sub(r'\s+', ' ', (name or '').strip())
    s = re.split(r'\s+[—–]\s+', s)[0]          # tolerate 'LMB — left mouse' style labels
    u = s.upper()
    for k in list(_MOUSE) + list(_VK):
        if u == k.upper(): return k
    if u in _ALIASES: return _ALIASES[u]
    if re.fullmatch(r'F([1-9]|1\d|2[0-4])', u): return u
    if len(s) == 1 and s.isascii() and s.isalnum(): return u
    if s in _VK: return s                        # punctuation keys
    raise ValueError(f'Unknown key {name!r}. Pick one from the list, or type a letter, digit or F1-F24.')


def resolve(name):
    """Name -> Key. Raises ValueError for unknown or reserved keys."""
    n = canonical(name)
    if n in _MOUSE:
        d, u, data = _MOUSE[n]
        return Key(n, 'mouse', 0, d, u, data, 0)
    if n in _VK: vk, ext = _VK[n]
    elif re.fullmatch(r'F\d+', n): vk, ext = 0x6F + int(n[1:]), 0
    else: vk, ext = ord(n), 0
    if vk in RESERVED_VK: raise ValueError(f'{n} is reserved: {RESERVED_VK[vk]}.')
    return Key(n, 'key', vk, 0, 0, 0, ext)
