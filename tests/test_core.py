import unittest
from engine import Controller
from vision import Prompt, associate, keycaps
import cv2
import numpy as np

P=Prompt('Collect','E',False,.99,(0,0,30,30),'Collect')
H=Prompt('Siphon','E',True,.99,(0,0,30,30),'Siphon [Hold]')
class Tests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.c=Controller(lambda k,d:self.events.append((k,d)))
    def auto(self,preview=False):self.c.start('Auto','E',.1,.05,preview)
    def test_two_scans_and_latch(self):
        self.auto();self.c.observation(P,1);self.assertFalse(self.events)
        self.c.observation(P,1.3);self.c.tick(1.4,True)
        self.c.observation(P,3);self.assertEqual(self.events,[('E',True),('E',False)])
    def test_preview(self):
        self.auto(True);self.c.observation(H,1);self.c.observation(H,1.3);self.assertFalse(self.events)
    def test_hold_release_on_lost_prompt(self):
        self.auto();self.c.observation(H,1);self.c.observation(H,1.3);self.c.observation(None,1.6)
        self.assertEqual(self.events,[('E',True),('E',False)])
    def test_stale_hold(self):
        self.auto();self.c.observation(H,1);self.c.observation(H,1.3);self.c.tick(2.3,True)
        self.assertIsNone(self.c.held)
    def test_focus_stops(self):
        self.c.start('Hold','LBUTTON',.1,.05);self.c.tick(1,True);self.c.tick(2,False)
        self.assertFalse(self.c.running);self.assertEqual(self.events[-1],('LBUTTON',False))
    def test_timed_once(self):
        self.c.start('Timed','E',.1,.3);self.c.tick(1,True);self.c.tick(1.31,True);self.c.tick(4,True)
        self.assertEqual(len(self.events),2);self.assertFalse(self.c.running)
    def test_stop_prevents_stale_result(self):
        self.auto();self.c.observation(H,1);self.c.stop();self.c.observation(H,1.3);self.assertFalse(self.events)
    def test_action_pairing(self):
        caps=[(250,20,35,35),(250,80,35,35)]
        items=[(10,20,230,55,'Collect Water',.99),(258,25,278,50,'E',.99),(10,80,240,115,'Fill Watering Can',.99),(258,85,278,110,'F',.99)]
        out=associate(caps,items,['Fill Watering Can','Collect Water'])
        self.assertEqual([(p.action,p.key) for p in out],[('Fill Watering Can','F'),('Collect Water','E')])
    def test_disallowed_and_missing_hold(self):
        items=[(10,20,230,55,'Siphon (6)',.99),(258,25,278,50,'E',.99)]
        self.assertEqual(associate([(250,20,35,35)],items,['Siphon']),[])
        items[0]=(10,20,230,55,'Uproot',.99)
        self.assertEqual(associate([(250,20,35,35)],items,['Collect']),[])
    def test_dim_keycap_rejected(self):
        img=np.zeros((100,200,3),dtype=np.uint8)
        cv2.rectangle(img,(20,20),(55,55),(100,100,100),2)
        self.assertFalse(keycaps(img))
        cv2.rectangle(img,(100,20),(135,55),(240,240,240),2)
        self.assertTrue(keycaps(img))
if __name__=='__main__':unittest.main()
