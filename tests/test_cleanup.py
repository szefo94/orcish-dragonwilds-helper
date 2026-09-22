"""2.2: Setup → 6 clean-up only lists files the app no longer needs; never user data."""
import unittest, tempfile
from pathlib import Path
import maintenance

class Cleanup(unittest.TestCase):
    def test_candidates(self):
        r=Path(tempfile.mkdtemp());d=r/'data'
        for rel in ('data/settings.json','data/learned/learned.npz','data/fishing_notes.md','data/benchmarks/bench_1.json','data/orcpresser.log',
                    'data/orcpresser.log.1','data/learned/learned.bad.npz','data/old_version_backup/app.py','OrcPresser_2.0.zip','src/orcpresser/__pycache__/x.pyc'):
            p=r/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('x')
        found={str(p.relative_to(r)).replace('\\','/') for p,_,_ in maintenance.cleanup_candidates(r,d)}
        self.assertEqual(found,{'data/old_version_backup','data/orcpresser.log.1','data/learned/learned.bad.npz','OrcPresser_2.0.zip','src/orcpresser/__pycache__'})
if __name__=='__main__':unittest.main()
