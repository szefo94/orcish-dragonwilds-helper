"""Small persistent settings store: one JSON file, one section per game profile.
Atomic writes (temp file + replace); a missing or corrupt file just means defaults."""
import json, os
from pathlib import Path


class Settings:
    def __init__(self, path, section='default'):
        self.path = Path(path); self.section = section
        try: self.all = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError): self.all = {}
        if not isinstance(self.all, dict): self.all = {}
        self.data = self.all.setdefault(section, {})
        if not isinstance(self.data, dict): self.data = self.all[section] = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        try:
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.all, indent=2, ensure_ascii=False), encoding='utf-8')
            os.replace(tmp, self.path)
        except OSError:
            pass
