"""1.7: reaction-time meter, window size/position persistence."""
import unittest, tempfile
from pathlib import Path
from unittest.mock import Mock
from engine import ReactionMeter
from settings import Settings

A=('Collect','E',False);B=('Harvest','F',True)
class Meter(unittest.TestCase):
    def test_first_seen_to_press(self):
        m=ReactionMeter();m.scan(A,10.0);m.scan(A,10.2)
        r=m.fired(10.35,'Collect E',95,'OCR')
        self.assertAlmostEqual(r['ms'],350,places=3);self.assertEqual(r['scans'],2)
    def test_repeat_taps_not_counted_again(self):
        m=ReactionMeter();m.scan(A,1.0);self.assertIsNotNone(m.fired(1.2,'x',1,'OCR'))
        m.scan(A,1.3);self.assertIsNone(m.fired(1.4,'x',1,'OCR'));self.assertEqual(len(m.hist),1)
    def test_new_sighting_resets(self):
        m=ReactionMeter();m.scan(A,1.0);m.fired(1.1,'x',1,'OCR');m.scan(None,2.0);m.scan(A,3.0)
        self.assertAlmostEqual(m.fired(3.05,'x',1,'OCR')['ms'],50,places=3)
        m.scan(B,4.0);self.assertAlmostEqual(m.fired(4.5,'y',1,'OCR')['ms'],500,places=3)
        self.assertIn('Avg 3',m.summary())
    def test_nothing_seen(self):
        self.assertIsNone(ReactionMeter().fired(1,'x',1,'OCR'));self.assertEqual(ReactionMeter().summary(),'No action yet')
    def test_history_capped(self):
        m=ReactionMeter(keep=3)
        for i in range(6):m.scan(None,i);m.scan(A,i);m.fired(i+.1,'x',1,'OCR')
        self.assertEqual(len(m.hist),3)

class Window(unittest.TestCase):
    def app(self,saved=None,on_screen=True):
        from app import App
        a=App.__new__(App);a.root=Mock();a.root.geometry.return_value='1x1+0+0'
        a.settings=Settings(Path(tempfile.mkdtemp())/'s.json','T')
        if saved:
            for k,v in saved.items():a.settings.set(k,v)
        a.on_screen=Mock(return_value=on_screen);a.work_area=Mock(return_value=(0,0,1920,1040));a.natural_size=Mock(return_value=(1392,858))
        return a
    def test_restores_saved_geometry(self):
        a=self.app({'geometry':'1200x800+100+50'});a.place_window();a.root.geometry.assert_called_with('1200x800+100+50')
    def test_offscreen_or_bogus_falls_back_to_fit(self):
        for saved,on in [({'geometry':'1200x800+5000+50'},False),({'geometry':'1x1+0+0'},True),({},True)]:
            a=self.app(saved,on);a.place_window();a.root.geometry.assert_called_with('1392x858+520+0')
    def test_fit_clamped_to_small_screen(self):
        a=self.app();a.work_area=Mock(return_value=(0,0,1280,760));a.place_window()
        a.root.geometry.assert_called_with('1280x728+0+0')
    def test_zoomed_restored_and_saved_with_normal_size(self):
        a=self.app({'geometry':'1200x800+100+50','zoomed':True});a.place_window();a.root.state.assert_called_with('zoomed')
        a.win_zoomed=True;a.save_window()
        self.assertEqual(a.settings.get('geometry'),'1200x800+100+50');self.assertTrue(a.settings.get('zoomed'))
if __name__=='__main__':unittest.main()
