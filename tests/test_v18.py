"""1.8: start-up robustness — safe start ("zero point"), stuck-key release, no heavy imports in UI thread."""
import unittest, tempfile, sys, time
from pathlib import Path
from unittest.mock import Mock
from settings import Settings
from learn import Learner

class Startup(unittest.TestCase):
    def test_dxgi_check_does_not_import(self):
        sys.modules.pop('dxcam',None)
        from capture import dxgi_available
        dxgi_available();self.assertNotIn('dxcam',sys.modules)
    def test_corrupt_learned_data_starts_empty_and_reports(self):
        d=Path(tempfile.mkdtemp());(d/'learned.npz').write_text('garbage')
        L=Learner(d);self.assertEqual(L.stats()[:2],(0,0));self.assertIsNotNone(L.load_error)
    def test_safe_learner_never_writes(self):
        d=Path(tempfile.mkdtemp());L=Learner(d,load=False,persist=False);L.dirty=True;L.save()
        self.assertFalse((d/'learned.npz').exists())
    def test_progress_flags_stall_once(self):
        from app import App
        a=App.__new__(App);a.ready=False;a.detected=Mock();a.stage='loading OCR models'
        a.stage_since=time.monotonic()-50;a.load_started=a.stage_since;a.stop=Mock()
        a.loading_progress(time.monotonic());a.loading_progress(time.monotonic())
        a.stop.assert_called_once();self.assertIn('loading OCR models',a.stop.call_args[0][0])
    def test_progress_never_raises_on_partial_app(self):
        from app import App
        App.__new__(App).loading_progress(time.monotonic())

class Release(unittest.TestCase):
    def test_release_all_sends_up_for_used_keys_and_mouse(self):
        from app import WinIO
        io=WinIO.__new__(WinIO);import threading;io.lock=threading.RLock();io.held='E';io.used={'E','F'};sent=[]
        io.event=lambda k,d:sent.append((k,d))
        io.release_all()
        self.assertEqual(set(sent),{('E',False),('F',False),('LBUTTON',False),('RBUTTON',False),('MBUTTON',False)})
        self.assertIsNone(io.held)
if __name__=='__main__':unittest.main()
