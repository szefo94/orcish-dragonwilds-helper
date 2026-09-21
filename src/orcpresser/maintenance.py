"""Helpers used by Setup.cmd:  migrate | runtime | test | clean [--yes]"""
import sys, shutil, subprocess
from pathlib import Path
from paths import ROOT, DATA, migrate_data, cleanup_old_code, ensure_data


def main(cmd):
    ensure_data()
    if cmd == 'migrate':
        data, code = migrate_data(), cleanup_old_code()
        if data: print('Moved your data into data\\: ' + ', '.join(data))
        if code: print('Old program files moved to data\\old_version_backup\\ (safe to delete): ' + ', '.join(code))
        if not data and not code: print('Folder layout already up to date.')
    elif cmd == 'runtime':
        try:
            import onnxruntime as o
            p = o.get_available_providers()
            print('OCR runtime:', 'GPU (DirectML)' if 'DmlExecutionProvider' in p else 'CPU')
        except Exception as e:
            print('OCR runtime not importable:', e); return 1
    elif cmd == 'clean':
        items = cleanup_candidates()
        if not items: print('Nothing to clean up.'); return 0
        total = sum(size for _, size, _ in items)
        for p, size, why in items: print(f'  {size / 1024 / 1024:7.1f} MB  {p.relative_to(ROOT)}   ({why})')
        print(f'  {total / 1024 / 1024:7.1f} MB  total')
        if '--yes' not in sys.argv and input('Delete these? [y/N] ').strip().lower() not in ('y', 'yes'):
            print('Nothing deleted.'); return 0
        for p, _, _ in items:
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
        print('Cleaned up.')
    elif cmd == 'test':
        return subprocess.call([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'], cwd=ROOT)
    else:
        print(__doc__); return 2
    return 0


def _size(p):
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) if p.is_dir() else p.stat().st_size


def cleanup_candidates(root=ROOT, data=DATA, keep_versions=2):
    """Files the app no longer needs: (path, bytes, reason). Never settings, learned data, notes or test results."""
    root, data = Path(root), Path(data); out = []
    def add(p, why):
        if p.exists(): out.append((p, _size(p), why))
    add(data / 'old_version_backup', 'program files from the 1.x layout, replaced by 2.x')
    add(data / 'orcpresser.log.1', 'rotated old log')
    add(data / 'learned' / 'learned.bad.npz', 'unreadable learned data set aside earlier')
    old = data / 'old_versions'
    if old.is_dir():                             # keep the newest N backups/zips for rollback
        entries = sorted(old.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in entries[keep_versions * 2:]: add(p, f'older than the last {keep_versions} updates')
    for z in sorted(root.glob('OrcPresser_*.zip')): add(z, 'update zip in the main folder')
    for c in list((root / 'src').rglob('__pycache__')) + list((root / 'tests').rglob('__pycache__')):
        add(c, 'Python cache, rebuilt automatically')
    return out


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ''))
