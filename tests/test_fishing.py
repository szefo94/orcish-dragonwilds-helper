"""Synthetic fishing evidence: input ordering, stale frames, confirmation and calibration."""
import unittest
import numpy as np
from fishing import FishingController, FishingConfig, Observation, CastCalibration
from fishing_capture import indicator, rect_pixels

class Fishing(unittest.TestCase):
    def setUp(self):
        self.events=[];self.c=FishingController(lambda k,d:self.events.append((k,d)))
        self.c.start(preview=False);self.c.tick(10)
    def see(self,t,color='unknown',text='',stamp=None,active=None,active_stamp=None):
        ts=t if stamp is None else stamp;ats=t if active_stamp is None else active_stamp
        self.c.observe(Observation(t,color,text,ts,active=active,active_stamp=ats),t)
    def fight(self):
        self.see(10,'red');self.see(10.05,'red')
    def test_preview_never_outputs(self):
        self.c.start(preview=True);self.fight();self.c.stop()
        self.assertEqual(self.events,[])
    def test_red_holds_same_direction_without_pulsing(self):
        self.fight();self.see(10.4,'red');self.see(11.0,'red')
        self.assertEqual(self.events,[('A',True)])
    def test_blue_keeps_direction_then_next_red_swaps_once(self):
        self.fight();self.see(10.1,'blue');self.see(10.15,'blue')
        self.assertEqual(self.c.held,'A');self.assertEqual(self.events,[('A',True)])
        self.see(10.2,'red');self.see(10.25,'red')
        self.assertEqual(self.c.held,'D');self.assertEqual(self.events,[('A',True),('A',False),('D',True)])
        self.see(10.8,'red');self.assertEqual(self.events,[('A',True),('A',False),('D',True)])
    def test_reel_then_red_releases_mouse_before_direction(self):
        self.fight();self.see(10.1,'blue','Reel (Hold)');self.see(10.55,'blue','Reel (Hold)')
        self.assertEqual(self.c.state,'REEL');self.assertEqual(self.c.held,'LMB')
        self.see(10.6,'red','Reel (Hold)',10.55);self.see(10.65,'red','Reel (Hold)',10.55)
        self.assertEqual(self.events[-2:],[('LMB',False),('D',True)])
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
    def test_brief_unknown_keeps_direction_held(self):
        self.fight();self.see(10.1);self.see(10.15);self.see(10.3)
        self.assertTrue(self.c.running);self.assertEqual(self.c.held,'A');self.assertEqual(self.events,[('A',True)])
    def test_sustained_unknown_releases_after_grace(self):
        self.fight();self.see(10.1);self.see(10.15);self.see(10.56)
        self.assertTrue(self.c.running);self.assertIsNone(self.c.held);self.assertEqual(self.events,[('A',True),('A',False)])
    def test_unknown_gap_preserves_last_reliable_blue_for_swap(self):
        self.fight();self.see(10.1,'blue');self.see(10.15,'blue')
        self.see(10.2);self.see(10.25)
        self.assertEqual(self.c.held,'A')
        self.see(10.3,'red');self.see(10.35,'red')
        self.assertEqual(self.c.held,'D');self.assertEqual(self.events,[('A',True),('A',False),('D',True)])
    def test_no_fish_stops_for_manual_travel(self):
        self.fight();self.see(10.1,text='No fish here');self.see(10.55,text='No fish here')
        self.assertFalse(self.c.running);self.assertEqual(self.c.state,'FAILED')
    def test_confirmed_catch_stops(self):
        self.fight();self.see(10.1,text='You caught a fish');self.see(10.55,text='You caught a fish')
        self.assertFalse(self.c.running);self.assertEqual(self.c.state,'CAUGHT')
    def test_recurring_waits_for_active_clear_then_new_active(self):
        self.c=FishingController(lambda k,d:self.events.append((k,d)),FishingConfig(recurring=True,require_active=True));self.c.start(False);self.c.tick(10)
        self.see(10,'red',active=True);self.see(10.4,'red',active=True)
        self.assertEqual(self.c.state,'FIGHT');self.assertEqual(self.c.held,'A')
        self.see(10.8,'blue','You caught a fish',active=True);self.see(11.2,'blue','You caught a fish',active=True)
        self.assertTrue(self.c.running);self.assertEqual(self.c.state,'WAIT_CLEAR');self.assertIsNone(self.c.held)
        self.see(11.6,'unknown','You caught a fish',active=True);self.assertEqual(self.c.state,'WAIT_CLEAR')
        self.see(12.0,'unknown','You caught a fish',active=False);self.see(12.4,'unknown','You caught a fish',active=False)
        self.assertEqual(self.c.state,'WAIT_ACTIVE')
        self.see(12.8,'red',active=True);self.see(13.2,'red',active=True)
        self.assertEqual(self.c.state,'FIGHT');self.assertEqual(self.c.held,'A')
    def test_recurring_depleted_still_stops(self):
        self.c=FishingController(lambda k,d:self.events.append((k,d)),FishingConfig(recurring=True));self.c.start(False);self.c.tick(10);self.fight()
        self.see(10.5,text='No fish here');self.see(10.9,text='No fish here')
        self.assertFalse(self.c.running);self.assertEqual(self.c.state,'DEPLETED')
    def test_blue_holds_direction_while_waiting_for_reel(self):
        self.fight();self.see(10.1,'blue');self.see(10.15,'blue')
        self.assertEqual(self.c.held,'A');self.assertIn('keep direction',self.c.reason)
    def test_blue_reel_releases_direction_before_lmb(self):
        self.fight();self.see(10.1,'blue','Reel (Hold)');self.see(10.5,'blue','Reel (Hold)')
        self.assertEqual(self.events[-2:],[('A',False),('LMB',True)])
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
        for v in (0,.01,99,float('nan')):
            with self.assertRaises(ValueError):FishingConfig(unknown_grace_seconds=v).validate()
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
    def test_dragonwilds_pastel_blue_reference(self):
        frame=np.full((16,59,3),(230,223,181),dtype=np.uint8)  # RGB 181/223/230 in BGR order
        self.assertEqual(indicator(frame)[0],'blue')
    def test_thin_red_burndown_edge_over_blue_fill(self):
        frame=np.full((16,300,3),(12,13,16),dtype=np.uint8)
        frame[:,1:63]=(230,223,181)     # sampled Dragonwilds blue
        frame[:,63:65]=(50,68,208)      # sampled 2 px red live edge
        color,red,blue=indicator(frame)
        self.assertEqual(color,'red');self.assertLess(red,.01);self.assertGreater(blue,.15)
    def test_region_on_negative_monitor(self):
        self.assertEqual(rect_pixels((-1920,0,1920,1080),(.5,.5,.25,.1)),dict(left=-960,top=540,width=480,height=108))
