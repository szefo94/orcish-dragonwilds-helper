"""2.1: version updater — newest zip by internal version, mirrored code folders, data untouched."""
import unittest, tempfile, zipfile
from pathlib import Path
import updater

def tree(root,files):
    for rel,txt in files.items():
        p=Path(root)/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(txt)
def make_zip(path,version,extra=None,req='numpy\n'):
    files={'OrcPresser/src/orcpresser/version.py':f"VERSION = '{version}'\n",'OrcPresser/src/orcpresser/app.py':f'# app {version}\n',
           'OrcPresser/src/requirements.txt':req,'OrcPresser/Run.cmd':f'run {version}','OrcPresser/Update.cmd':'upd','OrcPresser/docs/CHANGELOG.md':version}
    files.update(extra or {})
    with zipfile.ZipFile(path,'w') as z:
        for n,t in files.items():z.writestr(n,t)
    return path

class Updater(unittest.TestCase):
    def install(self):
        r=Path(tempfile.mkdtemp())
        tree(r,{'src/orcpresser/app.py':'# app 2.0\n','src/orcpresser/old_module.py':'x','src/requirements.txt':'numpy\n','Run.cmd':'run 2.0',
                'data/settings.json':'{"mine":1}','data/learned/learned.npz':'L','.venv/marker':'v','docs/CHANGELOG.md':'2.0'})
        return r
    def test_versions(self):
        r=self.install();self.assertEqual(updater.current_version(r),'2.0')
        make_zip(r/'OrcPresser_2.1.zip','2.1');make_zip(r/'OrcPresser_zzz.zip','2.10');(r/'OrcPresser_1.9.zip').write_bytes(b'not a 2.x zip')
        self.assertEqual([v for v,_ in updater.find_zips(r)],['2.1','2.10'])        # numeric, 1.x ignored
    def test_github_download_zip_is_discovered(self):
        r=self.install();make_zip(r/'orcish-dragonwilds-helper-main.zip','2.5')
        found=updater.find_zips(r);self.assertEqual([(v,p.name) for v,p in found],[('2.5','orcish-dragonwilds-helper-main.zip')])
        self.assertEqual(updater.zip_version(found[0][1]),'2.5')
    def test_apply_mirrors_and_keeps_data(self):
        r=self.install();z=make_zip(r/'OrcPresser_2.1.zip','2.1')
        old,new,req=updater.apply(z,r,r/'data',log=lambda *_:None)
        self.assertEqual((old,new,req),('2.0','2.1',False))
        self.assertEqual((r/'src/orcpresser/app.py').read_text(),'# app 2.1\n');self.assertEqual((r/'Run.cmd').read_text(),'run 2.1')
        self.assertTrue((r/'Update.cmd').exists());self.assertFalse((r/'src/orcpresser/old_module.py').exists())
        self.assertTrue((r/'data/old_versions/2.0/src/orcpresser/old_module.py').exists())
        self.assertEqual((r/'data/settings.json').read_text(),'{"mine":1}');self.assertTrue((r/'.venv/marker').exists())
        self.assertEqual(updater.current_version(r),'2.1')
    def test_requirements_change_detected(self):
        r=self.install();z=make_zip(r/'OrcPresser_2.2.zip','2.2',req='numpy\ndxcam\n')
        self.assertTrue(updater.apply(z,r,r/'data',log=lambda *_:None)[2])
    def test_archive_moves_applied_and_older(self):
        r=self.install();make_zip(r/'OrcPresser_2.1.zip','2.1');make_zip(r/'OrcPresser_2.2.zip','2.2')
        updater.archive_zips(r,r/'data',upto='2.1')
        self.assertTrue((r/'data/old_versions/OrcPresser_2.1.zip').exists());self.assertTrue((r/'OrcPresser_2.2.zip').exists())
    def test_prune_keeps_last_two_updates(self):
        import os,time
        r=self.install();old=r/'data'/'old_versions';old.mkdir(parents=True)
        for i,n in enumerate(['2.0','OrcPresser_2.1.zip','2.1','OrcPresser_2.2.zip','2.2','OrcPresser_2.3.zip']):
            p=old/n;(p.mkdir() if '.zip' not in n else p.write_text('z'));os.utime(p,(time.time()+i,time.time()+i))
        gone=updater.prune_old_versions(r/'data');self.assertEqual(sorted(gone),['2.0','OrcPresser_2.1.zip'])
        self.assertEqual(len(list(old.iterdir())),4)
if __name__=='__main__':unittest.main()
