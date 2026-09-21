"""Synthetic fishing evidence: input ordering, stale frames, confirmation and calibration."""
import unittest
import numpy as np
from fishing import FishingController, FishingConfig, Observation, CastCalibration
from fishing_capture import indicator, rect_pixels

class Fishing(unittest.TestCase):
    def setUp(self):
        self.events=[];self.c=FishingController(lambda k,d:self.events.append((k,d)))
        self.c.start(preview=False);self.c.tick(10)
    def see(self,t,color='unknown',text='',stamp=None):
        self.c.observe(Observation(t,color,text,t if stamp is None else stamp),t)
    def fight(self):
        self.see(10,'red');self.see(10.05,'red')
    def test_preview_never_outputs(self):
        self.c.start(preview=True);self.fight();self.c.stop()
        self.assertEqual(self.events,[])
    def test_red_probe_releases_before_opposite(self):
        self.fight();self.see(10.4,'red')
        self.assertEqual(self.events,[('A',True),('A',False),('D',True)])
    def test_reel_then_red_releases_mouse_before_direction(self):
        self.fight();self.see(10.1,'blue','Reel (Hold)');self.see(10.55,'blue','Reel (Hold)')
        self.assertEqual(self.c.state,'REEL');self.assertEqual(self.c.held,'LMB')
        self.see(10.6,'red','Reel (Hold)',10.55);self.see(10.65,'red','Reel (Hold)',10.55)
        self.assertEqual(self.events[-2:],[('LMB',False),('A',True)])
    def test_cached_ocr_is_not_second_confirmation(self):
        self.c.config.auto_cast=True
        self.see(10,text='Cast (Hold)',stamp=10);self.see(10.1,text='Cast (Hold)',stamp=10)
        self.assertIsNone(self.c.held)
        self.see(10.4,text='Cast (Hold)');self.assertEqual(self.c.held,'LMB')
    def test_trial_cast_releases_and_stops(self):
        self.c.start(False,True);self.c.tick(10)
        self.see(10,text='Cast (Hold)');self.see(10.4,text='Cast (Hold)')
        self.see(10.8);self.c.tick(11.01)
        self.assertEqual(self.events,[('LMB',True),('LMB',False)])
        self.assertFalse(self.c.running);self.assertEqual(self.c.state,'TRIAL_DONE')
    def test_focus_loss_releases(self):
        self.fight();self.c.tick(10.1,False)
        self.assertFalse(self.c.running);self.assertEqual(self.events[-1],('A',False))
    def test_stale_capture_releases(self):
        self.fight();self.c.tick(11)
        self.assertFalse(self.c.running);self.assertIsNone(self.c.held)
    def test_old_frame_cannot_start_action(self):
        self.c.observe(Observation(1,'red'),10);self.c.observe(Observation(1,'red'),10)
        self.assertEqual(self.events,[])
    def test_unknown_is_not_a_catch(self):
        self.fight();self.see(10.1);self.see(10.15)
        self.assertTrue(self.c.running);self.assertIsNone(self.c.held);self.assertNotEqual(self.c.state,'CAUGHT')
    def test_confirmed_catch_stops(self):
        self.fight();self.see(10.1,text='You caught a fish');self.see(10.55,text='You caught a fish')
        self.assertFalse(self.c.running);self.assertEqual(self.c.state,'CAUGHT')
    def test_blue_release_option(self):
        self.c.config.blue_release=True;self.fight();self.see(10.1,'blue');self.see(10.15,'blue')
        self.assertIsNone(self.c.held)
    def test_stale_reel_text_does_not_hold_forever(self):
        self.fight();self.see(10.1,'blue','Reel (Hold)');self.see(10.5,'blue','Reel (Hold)')
        self.see(12.1,'blue','Reel (Hold)',10.5)
        self.assertIsNone(self.c.held)
    def test_restart_resets_wait_timeout(self):
        self.c.changed=10;self.c.start();self.c.tick(100);self.c.tick(100.1)
        self.assertTrue(self.c.running)
    def test_no_capture_timeout(self):
        self.c.tick(14);self.assertFalse(self.c.running)
    def test_invalid_config(self):
        for v in (0,99,float('nan'),float('inf')):
            with self.assertRaises(ValueError):FishingConfig(cast_seconds=v).validate()
    def test_calibration_bracket(self):
        b=CastCalibration();self.assertAlmostEqual(b.feedback(.65,'short'),.925)
        self.assertAlmostEqual(b.feedback(1.,'long'),.825)
        b.feedback(.825,'hit');self.assertAlmostEqual(b.confirmed,.825)
    def test_color_detection(self):
        frame=np.zeros((20,20,3),dtype=np.uint8)
        self.assertEqual(indicator(frame)[0],'unknown')
        frame[:]=(0,0,255);self.assertEqual(indicator(frame)[0],'red')
        frame[:]=(255,0,0);self.assertEqual(indicator(frame)[0],'blue')
        frame[:10]=(0,0,255);self.assertEqual(indicator(frame)[0],'unknown')
    def test_region_on_negative_monitor(self):
        self.assertEqual(rect_pixels((-1920,0,1920,1080),(.5,.5,.25,.1)),dict(left=-960,top=540,width=480,height=108))
