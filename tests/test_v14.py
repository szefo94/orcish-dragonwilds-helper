"""1.4: PREVIEW/LIVE buttons, click-off, last-5 reads log. Tk objects mocked."""
import unittest
from collections import deque
from unittest.mock import Mock
import tkinter as tk
from app import App

def app(mode='Auto'):
    a=App.__new__(App);a.visual=False;a.mode=mode;a.run='Preview';a.last_run='Preview'
    a.ctrl=Mock();a.ctrl.running=False;a.status=Mock();a.hint=Mock();a.runbuttons={'Preview':Mock(),'Live':Mock()}
    a.generation=0;a.started=[];a.start=lambda r:(a.started.append(r),setattr(a.ctrl,'running',True),setattr(a,'run',r))
    return a
class V14(unittest.TestCase):
    def test_pick_stop_switch(self):
        a=app();a.launch('Live');self.assertEqual(a.started,['Live']);self.assertEqual(a.last_run,'Live')
        a.launch('Live');a.ctrl.stop.assert_called();self.assertEqual(a.started,['Live'])   # same button stops
        a.ctrl.running=True;a.run='Preview';a.launch('Live');self.assertEqual(a.started,['Live','Live'])  # other switches
    def test_preview_only_for_auto(self):
        a=app('Repeat');a.launch('Preview');self.assertEqual(a.started,[])
        a.launch('Live');self.assertEqual(a.started,['Live'])
    def test_hotkey_uses_last_choice(self):
        a=app();a.last_run='Live';a.toggle();self.assertEqual(a.started,['Live'])
        a.ctrl.running=False;a.mode='Hold';a.last_run='Preview';a.toggle();self.assertEqual(a.started[-1],'Live')
    def test_reads_dedupe_and_cap(self):
        a=app();a.reads=deque(maxlen=5);a.last_read=None;a.readtext=Mock()
        for l in ['A','A','B','A','C','D','E','F']:a.log_read(l)
        self.assertEqual([e.strip() for _,e in a.reads],['F','E','D','C','A'])
        a.log_read('F',True);self.assertTrue(a.reads[0][1].startswith('▶'))
    def test_click_off_moves_focus(self):
        a=app();a.root=Mock();w=Mock(spec=tk.Label);w.winfo_toplevel.return_value=a.root
        a.defocus(Mock(widget=w));a.root.focus_set.assert_called_once()
        e=Mock(spec=tk.Entry);e.winfo_toplevel.return_value=a.root
        a.defocus(Mock(widget=e));a.root.focus_set.assert_called_once()
        o=Mock(spec=tk.Canvas);o.winfo_toplevel.return_value=Mock()        # region overlay keeps its focus
        a.defocus(Mock(widget=o));a.root.focus_set.assert_called_once()
if __name__=='__main__':unittest.main()
