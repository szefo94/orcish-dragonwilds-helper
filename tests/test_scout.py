import json, os, tempfile, unittest
from pathlib import Path
from scout import ScoutRecorder


class ScoutRecorderTests(unittest.TestCase):
    def test_parallel_session_files_and_timing_fields(self):
        with tempfile.TemporaryDirectory() as td:
            r=ScoutRecorder(td,'fishing','Preview',pid=os.getpid(),metadata={'helper_version':'test'},clock=lambda:12.5)
            r.event('vision','reel',True,confidence=.9,mono=10.0,latency_ms=80,fresh_ms=120,
                    details={'frame_mono':10.0,'detected_mono':10.08},stream='vision')
            r.event('controller','decision',{'held':'LMB'},mono=10.12,stream='controller')
            folder=r.folder;r.close('done')
            manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['domain'],'fishing');self.assertEqual(manifest['run'],'Preview')
            self.assertTrue((folder/'process.jsonl').exists())
            v=json.loads((folder/'vision.jsonl').read_text(encoding='utf-8').splitlines()[0])
            self.assertEqual(v['mono'],10.0);self.assertEqual(v['latency_ms'],80.0);self.assertEqual(v['fresh_ms'],120.0)
            self.assertEqual(v['details']['frame_mono'],10.0)
            summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['reason'],'done');self.assertGreaterEqual(summary['events'],4)

    def test_close_is_idempotent_and_blocks_new_events(self):
        with tempfile.TemporaryDirectory() as td:
            r=ScoutRecorder(td,'auto_picker','Live',clock=lambda:1.0)
            r.close('x');before=r.seq
            r.close('y');self.assertFalse(r.event('vision','prompt',True));self.assertEqual(r.seq,before)


if __name__=='__main__':unittest.main()
