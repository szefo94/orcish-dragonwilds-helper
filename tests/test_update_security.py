import io, stat, tempfile, unittest, zipfile
from pathlib import Path
import updater
from tests.test_updater import make_zip, tree

class UpdateSecurity(unittest.TestCase):
    def check_rejected(self,name,attrs=0):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            # ZipInfo(name) would itself rewrite \ to / on Windows (os.sep), destroying the case we're
            # testing before it is ever stored; set .filename directly so the raw name is what gets persisted.
            info=zipfile.ZipInfo('x');info.filename=name;info.external_attr=attrs;z.writestr(info,'x')
        with zipfile.ZipFile(stream) as z:
            with self.assertRaises(ValueError):updater.validate_archive(z)
    def test_bad_paths(self):
        for name in ('../outside.py','/root/file','C:/bad','a\\bad','a/file:stream','a/NUL.txt','a/file.','a/file '):
            with self.subTest(name=name):self.check_rejected(name)
    def test_symlink_rejected(self):self.check_rejected('src/link',stat.S_IFLNK<<16)
    def test_duplicate_case_rejected(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('src/X','a');z.writestr('src/x','b')
        with zipfile.ZipFile(stream) as z:
            with self.assertRaises(ValueError):updater.validate_archive(z)
    def test_renamed_archive_discovered_and_replaced_code_backed_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);tree(r,{'src/orcpresser/app.py':'old app','src/orcpresser/version.py':"VERSION='2.2'",'Run.cmd':'old launcher'})
            zp=make_zip(r/'OrcishDragonwildsHelper_2.3.zip','2.3')
            self.assertEqual(updater.find_zips(r)[0][0],'2.3')
            updater.apply(zp,r,log=lambda *_:None)
            self.assertEqual((r/'data/old_versions/2.2/src/orcpresser/app.py').read_text(),'old app')
            self.assertEqual((r/'data/old_versions/2.2/Run.cmd').read_text(),'old launcher')
    def test_invalid_zip_does_not_replace_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);tree(r,{'src/orcpresser/app.py':'original'})
            zp=make_zip(r/'OrcPresser_2.3.zip','2.3',{'../outside':'bad'})
            with self.assertRaises(ValueError):updater.apply(zp,r,log=lambda *_:None)
            self.assertEqual((r/'src/orcpresser/app.py').read_text(),'original')
