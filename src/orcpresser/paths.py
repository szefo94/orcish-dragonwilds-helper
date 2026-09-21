"""Where things live. Program code: src/orcpresser. User data (created at runtime): data/.

    <root>/Setup.cmd, Run.cmd, README.md      what a user touches
    <root>/data/                              settings.json, learned/, fishing_notes.md, orcpresser.log
    <root>/src/orcpresser/                    code (replaced on update)
    <root>/docs/, <root>/tests/               developer material
Updating = replace src/, docs/, tests/ and the root scripts; data/ is never shipped, so it survives.
"""
import shutil
from pathlib import Path

CODE = Path(__file__).resolve().parent
ROOT = CODE.parents[1]
DATA = ROOT / 'data'

# Data files the flat layout (<= 1.9) kept next to app.py in the root.
_OLD_DATA = ('settings.json', 'learned', 'fishing_notes.md', 'orcpresser.log', 'orcpresser.log.1')
# Program files of the flat layout; after migration they are stale copies.
_OLD_CODE = ('app.py', 'capture.py', 'engine.py', 'game_profile.py', 'keys.py', 'learn.py', 'settings.py',
             'vision.py', 'profile.py', 'fishing_notes_default.md', 'FRAMEWORK.md', 'VALIDATION.md',
             'requirements.txt', 'SafeStart.cmd', 'SetupCPU.cmd', 'SetupGPU.cmd')


def ensure_data(data=None):
    d = Path(data or DATA); d.mkdir(exist_ok=True)
    return d


def migrate_data(root=None, data=None):
    """Move user data from the old flat layout into data/. Never overwrites existing data.
    Returns the names moved. Safe to call on every start."""
    root = Path(root or ROOT); data = ensure_data(data); moved = []
    for name in _OLD_DATA:
        src, dst = root / name, data / name
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst)); moved.append(name)
    return moved


def cleanup_old_code(root=None, data=None):
    """Move stale program files of the flat layout into data/old_version_backup/ (kept, not deleted,
    in case something was edited by hand) and remove the root __pycache__."""
    root = Path(root or ROOT); data = ensure_data(data); backup = data / 'old_version_backup'; moved = []
    for p in [root / n for n in _OLD_CODE] + sorted(root.glob('test_*.py')):
        if p.is_file():
            backup.mkdir(parents=True, exist_ok=True)
            target = backup / p.name
            if target.exists(): target.unlink()
            shutil.move(str(p), str(target)); moved.append(p.name)
    cache = root / '__pycache__'
    if cache.is_dir(): shutil.rmtree(cache, ignore_errors=True); moved.append('__pycache__')
    return moved
