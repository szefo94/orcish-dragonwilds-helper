"""Game profiles: everything game-specific lives here; the rest of Orc Presser is generic.

GameProfile is the base ("Animal"): a game whose interaction prompts show action text next to a
bright keycap containing a key letter. Derive one class per game ("Dog") and override only what
differs. See FRAMEWORK.md for the full derivation guide.
"""
import os, re


class GameProfile:
    name = 'Generic'
    # Substrings (lower-case) matched against the window title + process name. Empty = any window.
    window_match = ()
    # (action name, regex on normalized lower-case text). Checked in order: put longer phrases
    # first so 'collect water' wins over 'collect'.
    actions = ()
    default_allowed = ()      # ticked on first start
    opt_in = ()               # shown with '(opt in)'; never ticked by default
    requires_hold = ()        # actions only valid when a hold marker was read (never degrade to tap)
    hold_pattern = r'\bhold\b'
    key_pattern = r'(?:^|\s)([A-Za-z0-9])\s*$'   # the single key character inside the keycap
    # Keycap detector: neutral (low-saturation) bright outlines of roughly square shape.
    keycap_min_bright = 160   # darkest channel must exceed this
    keycap_max_spread = 94    # max-min channel difference must stay below this (low saturation)
    keycap_size = (16, 110)   # px, width and height
    keycap_aspect = (.72, 1.35)
    data_dir = 'learned'      # learned OCR shortcuts (memory/templates) are stored per profile

    @property
    def action_names(self):
        return tuple(a for a, _ in self.actions)

    def normalize(self, text):
        return re.sub(r'\s+', ' ', text.lower()).strip()

    def classify(self, text):
        t = self.normalize(text)
        for name, pattern in self.actions:
            if re.match(pattern, t): return name
        return None

    def is_hold(self, text):
        return bool(re.search(self.hold_pattern, text, re.I))

    def accept(self, action, hold):
        """Final veto on a read prompt. Default: required holds must really read as holds."""
        return not (action in self.requires_hold and not hold)

    def matches_window(self, title, process):
        s = (title + ' ' + process).lower()
        return not self.window_match or any(m in s for m in self.window_match)


class Dragonwilds(GameProfile):
    name = 'Dragonwilds'
    window_match = ('dragonwilds',)
    actions = (
        ('Fill Watering Can', r'^fill watering can\b'),
        ('Fill Compost Bucket', r'^fill compost bucket\b'),
        ('Collect Water', r'^collect water\b'),
        ('Collect', r'^collect\b'),
        ('Siphon', r'^siphon\b'),
        ('Harvest', r'^harvest\b'),
        ('Uproot', r'^uproot\b'),
    )
    default_allowed = ('Collect', 'Siphon', 'Harvest')
    opt_in = ('Uproot',)
    requires_hold = ('Siphon',)
    # Display/priority order in the UI (top = highest priority).
    ui_order = ('Siphon', 'Fill Watering Can', 'Fill Compost Bucket', 'Collect Water', 'Harvest', 'Collect', 'Uproot')


def load(name=None):
    """Pick a profile by its name: argument, else ORC_PROFILE environment variable, else Dragonwilds.
    Profiles must be defined (or imported) in this module to be found."""
    name = (name or os.environ.get('ORC_PROFILE') or 'Dragonwilds').lower()
    todo, seen = [GameProfile], []
    while todo:
        c = todo.pop(); seen.append(c); todo += c.__subclasses__()
    for c in seen:
        if c.name.lower() == name: return c()
    raise SystemExit(f'Unknown game profile {name!r}. Known: ' + ', '.join(c.name for c in seen))


PROFILE = load()
