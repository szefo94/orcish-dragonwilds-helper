"""Version updater: apply an OrcPresser_*.zip placed in the root folder.

Usage (Update.cmd calls this):  updater.py [zip-path] [--force] [--yes]
- Picks the NEWEST zip by the version stored inside it (src/orcpresser/version.py), not by file name.
- Mirrors src/, docs/, tests/ (files removed in the new version are moved to data/old_versions/<old>/),
  overwrites the root scripts, never touches data/ or .venv/.
- Reinstalls Python packages only if src/requirements.txt changed (keeps the GPU runtime choice).
- Migrates user data, then moves the applied zip (and older ones) to data/old_versions/ and keeps
  only the last 2 updates there (rollback material).
"""
import os, re, sys, shutil, zipfile, tempfile, filecmp, subprocess, stat
from pathlib import PurePosixPath
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paths import ROOT, DATA, ensure_data, migrate_data, cleanup_old_code   # noqa: E402

MIRRORED = ('src', 'docs', 'tests', '.github', 'scripts')
ROOT_FILES = ('Setup.cmd', 'Run.cmd', 'Update.cmd', 'README.md', '.gitignore', '.gitattributes', '.editorconfig', 'CONTRIBUTING.md', 'SECURITY.md', 'RIGHTS.md', 'AGENTS.md')
_VER = re.compile(r"""VERSION\s*=\s*['"]([\d.]+)['"]""")


def vtuple(v):
    return tuple(int(x) for x in v.split('.')) if v else (0,)


def current_version(root=ROOT):
    f = Path(root) / 'src' / 'orcpresser' / 'version.py'
    m = _VER.search(f.read_text(encoding='utf-8')) if f.exists() else None
    return m[1] if m else '2.0' if (Path(root) / 'src' / 'orcpresser' / 'app.py').exists() else '1.x'


def zip_version(path):
    """Version inside an update zip, or None if it is not a 2.x layout zip."""
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.endswith('src/orcpresser/version.py')]
            if len(names)!=1 or z.getinfo(names[0]).file_size>16384: return None
            m = _VER.search(z.read(names[0]).decode('utf-8', 'replace'))
            return m[1] if m else None
    except (zipfile.BadZipFile, OSError):
        return None


def find_zips(root=ROOT):
    found = [(zip_version(p), p) for p in sorted(set(Path(root).glob('OrcPresser_*.zip')) | set(Path(root).glob('OrcishDragonwildsHelper_*.zip')))]
    return sorted([(v, p) for v, p in found if v], key=lambda vp: vtuple(vp[0]))


def _package_root(extracted):
    """Folder inside the extracted zip that contains src/orcpresser (usually OrcPresser/)."""
    for p in [extracted] + [d for d in Path(extracted).iterdir() if d.is_dir()]:
        if (p / 'src' / 'orcpresser' / 'app.py').exists(): return p
    raise RuntimeError('zip does not contain the OrcPresser 2.x layout')


def validate_archive(z):
    """Reject unsafe Windows paths, symlinks, duplicate names, and oversized packages."""
    total=0;seen=set()
    for entry in z.infolist():
        name=entry.filename
        parts=PurePosixPath(name).parts
        if (not parts or name.startswith('/') or '\\' in name or ':' in name or
            any(p in ('.','..') or p.endswith((' ','.')) for p in parts) or
            any(p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))} for p in parts) or
            stat.S_ISLNK(entry.external_attr >> 16)):
            raise ValueError('Unsafe path in update archive')
        key=name.rstrip('/').casefold()
        if key in seen:raise ValueError('Duplicate archive path')
        seen.add(key);total+=entry.file_size
        if entry.file_size>20*1024*1024 or total>100*1024*1024:
            raise ValueError('Update archive exceeds source-package size limit')


def apply(zip_path, root=ROOT, data=None, log=print):
    root = Path(root); data = ensure_data(data or root / 'data')
    if not zip_version(zip_path): raise ValueError('Not a recognized update archive')
    old = current_version(root); new = zip_version(zip_path)
    backup = data / 'old_versions' / old
    old_req = (root / 'src' / 'requirements.txt').read_text(encoding='utf-8') if (root / 'src' / 'requirements.txt').exists() else ''
    with tempfile.TemporaryDirectory(prefix='orcpresser_update_') as tmp:
        with zipfile.ZipFile(zip_path) as z:
            validate_archive(z)
            z.extractall(tmp)
        pkg = _package_root(Path(tmp))
        removed = replaced = 0
        for d in MIRRORED:
            src, dst = pkg / d, root / d
            if not src.exists(): continue
            new_files = {p.relative_to(src) for p in src.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
            if dst.exists():                    # stale files would shadow modules or confuse tests
                for p in [p for p in dst.rglob('*') if p.is_file()]:
                    rel = p.relative_to(dst)
                    if '__pycache__' in rel.parts: continue
                    if rel not in new_files:
                        target = backup / d / rel; target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(p), str(target)); removed += 1
            for rel in sorted(new_files):
                s, t = src / rel, dst / rel
                if t.exists() and filecmp.cmp(s, t, shallow=False): continue
                if t.exists():
                    saved = backup / d / rel; saved.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(t, saved)
                t.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(s, t); replaced += 1
            for cache in dst.rglob('__pycache__'): shutil.rmtree(cache, ignore_errors=True)
        for name in ROOT_FILES:
            if (pkg / name).exists():
                if (root / name).exists():
                    backup.mkdir(parents=True, exist_ok=True); shutil.copy2(root / name, backup / name)
                shutil.copy2(pkg / name, root / name); replaced += 1
    log(f'Updated {old} -> {new}: {replaced} files written, {removed} obsolete files moved to {backup.relative_to(root)}')
    moved = migrate_data(root, data) + cleanup_old_code(root, data)
    if moved: log('Old layout cleaned up: ' + ', '.join(moved))
    new_req = (root / 'src' / 'requirements.txt').read_text(encoding='utf-8') if (root / 'src' / 'requirements.txt').exists() else ''
    return old, new, new_req.strip() != old_req.strip()


def archive_zips(root=ROOT, data=None, upto=None):
    root = Path(root); dest = ensure_data(data or root / 'data') / 'old_versions'; dest.mkdir(exist_ok=True)
    for v, p in find_zips(root):
        if upto is None or vtuple(v) <= vtuple(upto): shutil.move(str(p), str(dest / p.name))


def prune_old_versions(data=None, keep=2):
    """Keep the backups and zips of the last `keep` updates in data/old_versions/, delete older ones."""
    old = ensure_data(data) / 'old_versions'
    if not old.is_dir(): return []
    entries = sorted(old.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[keep * 2:]
    for p in entries: shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    return [p.name for p in entries]


def main(argv):
    force, yes = '--force' in argv, '--yes' in argv
    args = [a for a in argv if not a.startswith('--')]
    cur = current_version()
    if args:
        zp = Path(args[0]); v = zip_version(zp)
        if not v: print(f'{zp} is not an OrcPresser 2.x update zip.'); return 1
    else:
        zips = find_zips()
        if not zips: print('No update found. Put OrcishDragonwildsHelper_<version>.zip (or legacy OrcPresser_<version>.zip) into this folder and run Update.cmd again.'); return 1
        v, zp = zips[-1]
    print(f'Installed: {cur}    Update file: {zp.name} (version {v})')
    if vtuple(v) <= vtuple(cur) and not force:
        print('Already up to date (use Update.cmd --force to reinstall this version).'); archive_zips(upto=cur); return 0
    if not yes and input('Apply this update? Close Orcish Dragonwilds Helper first. [Y/n] ').strip().lower() not in ('', 'y', 'yes'):
        print('Cancelled.'); return 1
    old, new, req_changed = apply(zp)
    if req_changed:
        print('Python packages changed - running Setup.cmd install ...')
        if os.name == 'nt':
            result = subprocess.call(['cmd', '/c', str(ROOT / 'Setup.cmd'), 'install'], cwd=ROOT)
            if result:
                print('Dependency installation failed. Run Setup.cmd install before starting; backup and archive retained.')
                return result
        else: print('(not on Windows: run Setup.cmd install yourself)')
    archive_zips(upto=new); prune_old_versions()
    print(f'Done. Orcish Dragonwilds Helper {new} is installed. Start it with Run.cmd. Old zips are in data\\old_versions\\.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
