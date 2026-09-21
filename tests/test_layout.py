"""2.0: folder layout — migration from the flat layout (<= 1.9) into data/ and old-code cleanup."""
import unittest, tempfile
from pathlib import Path
import paths

class Layout(unittest.TestCase):
    def flat(self):
        r=Path(tempfile.mkdtemp())
        (r/'settings.json').write_text('{"Dragonwilds":{"exclude":"Stone"}}');(r/'learned').mkdir();(r/'learned'/'learned.npz').write_bytes(b'x')
        (r/'fishing_notes.md').write_text('my notes');(r/'orcpresser.log').write_text('log')
        for n in ('app.py','vision.py','SetupGPU.cmd','FRAMEWORK.md','test_core.py','requirements.txt'):(r/n).write_text('old')
        (r/'__pycache__').mkdir();(r/'Run.cmd').write_text('run');(r/'README.md').write_text('readme')
        return r
    def test_data_moved_not_overwritten(self):
        r=self.flat();d=r/'data';d.mkdir();(d/'fishing_notes.md').write_text('newer')
        moved=paths.migrate_data(r,d)
        self.assertIn('settings.json',moved);self.assertIn('learned',moved);self.assertNotIn('fishing_notes.md',moved)
        self.assertEqual((d/'fishing_notes.md').read_text(),'newer');self.assertTrue((d/'learned'/'learned.npz').exists())
        self.assertEqual(paths.migrate_data(r,d),[])                       # idempotent
    def test_old_code_backed_up_user_files_kept(self):
        r=self.flat();d=r/'data';moved=paths.cleanup_old_code(r,d)
        for n in ('app.py','vision.py','SetupGPU.cmd','FRAMEWORK.md','test_core.py','requirements.txt','__pycache__'):self.assertIn(n,moved)
        self.assertTrue((d/'old_version_backup'/'app.py').exists());self.assertFalse((r/'__pycache__').exists())
        self.assertTrue((r/'Run.cmd').exists());self.assertTrue((r/'README.md').exists());self.assertTrue((r/'settings.json').exists())
    def test_real_tree_shape(self):
        self.assertEqual(paths.CODE.name,'orcpresser');self.assertEqual(paths.CODE.parent.name,'src')
        self.assertTrue((paths.ROOT/'tests').is_dir());self.assertEqual(paths.DATA,paths.ROOT/'data')
if __name__=='__main__':unittest.main()
