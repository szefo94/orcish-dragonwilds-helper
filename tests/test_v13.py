"""1.3: exclusions, configurable auto repeat/tap, opacity-0 minimize, strip merging."""
import unittest
from unittest.mock import Mock
from engine import Controller
from vision import Prompt, associate, exclusions, excluded_term, strips
from . import test_update as tu

T=Prompt('Collect Water','E',False,.99,(0,0,30,30),'Collect Water')
H=Prompt('Siphon','E',True,.99,(0,0,30,30),'Siphon [Hold]')
class V13(unittest.TestCase):
    def setUp(self):self.ev=[];self.c=Controller(lambda k,d:self.ev.append((k,d)))
    def test_parse_and_match(self):
        self.assertEqual(exclusions(' Stone, ,cabbage ,Stone,  Ash   Tree '),('stone','cabbage','ash tree'))
        self.assertEqual(excluded_term('Collect  STONES',('stone',)),'stone')
        self.assertIsNone(excluded_term('Collect Limestone',('stone',)))   # word-start only
        self.assertEqual(excluded_term('Ash tree',('ash tree',)),'ash tree')
    def test_exclusion_uses_name_line_above(self):
        cap=[(250,100,35,35)]
        items=[(10,40,120,70,'Stone',.9),(10,100,230,135,'Collect',.99),(258,105,278,130,'E',.99)]
        rej=[]
        self.assertEqual(associate(cap,items,['Collect'],('stone',),rej),[])
        self.assertEqual(rej[0][:3],('Collect','E','stone'))
        self.assertEqual(len(associate(cap,items,['Collect'],('cabbage',))),1)
        far=[(10,-200,120,-170,'Stone',.9)]+items[1:]   # text far above is not context
        self.assertEqual(len(associate(cap,far,['Collect'],('stone',))),1)
    def test_repeat_uses_interval_and_tap_length(self):
        self.c.start('Auto','E',.2,.05,False,repeat=True)
        self.c.observation(T,1.0);self.c.observation(T,1.15)          # confirm -> tap 1
        self.c.tick(1.20,True);self.c.observation(T,1.30);self.c.tick(1.35,True);self.c.tick(1.40,True)
        self.assertEqual(self.ev,[('E',True),('E',False),('E',True)])  # tap 2 at 1.35 = 1.15+.2
        self.assertAlmostEqual(self.c.until,1.40)                      # 50 ms tap
    def test_repeat_stops_when_prompt_missing_or_stale(self):
        self.c.start('Auto','E',.2,.05,False,repeat=True)
        self.c.observation(T,1.0);self.c.observation(T,1.15);self.c.tick(1.25,True)
        self.c.observation(None,1.3);self.c.tick(1.6,True);self.c.tick(2,True)
        self.assertEqual(len(self.ev),2)
        self.c.observation(T,3);self.c.observation(T,3.1);self.c.tick(3.2,True)
        self.c.tick(3.7,True)                                          # > FRESH since last scan
        self.assertEqual(len(self.ev),4)
    def test_no_repeat_without_option_and_holds_never_repeat(self):
        self.c.start('Auto','E',.2,.05,False)
        self.c.observation(T,1);self.c.observation(T,1.1);self.c.tick(1.2,True);self.c.tick(1.5,True)
        self.assertEqual(len(self.ev),2)
        self.setUp();self.c.start('Auto','E',.2,.05,False,repeat=True)
        self.c.observation(H,1);self.c.observation(H,1.1);self.c.tick(1.5,True)
        self.assertEqual(self.ev,[('E',True)]);self.assertAlmostEqual(self.c.until,16.1)
    def test_strips_merge_without_overlap(self):
        r=strips([(800,100,35,35),(812,110,16,17),(800,160,35,35),(800,600,35,35)],(900,1200),False)
        for i,a in enumerate(r):
            for b in r[i+1:]:self.assertFalse(a[0]<=b[2] and a[2]>=b[0] and a[1]<=b[3] and a[3]>=b[1])
        self.assertEqual(len(r),2)
        self.assertLess(strips([(800,300,35,35)],(900,1200),True)[0][1],strips([(800,300,35,35)],(900,1200))[0][1])

class Opacity(unittest.TestCase):
    def test_zero_minimizes_once_on_focus_loss(self):
        a=tu.UpdateTests().app();a.opacity.get.return_value=0;a.last_focused=True
        a.tick();a.root.iconify.assert_called_once()
        a.tick();a.root.iconify.assert_called_once()                   # not every tick
        self.assertTrue(a.ctrl.running)
    def test_nonzero_still_uses_alpha(self):
        a=tu.UpdateTests().app();a.opacity.get.return_value=35;a.last_focused=True
        a.tick();a.root.iconify.assert_not_called();a.root.attributes.assert_called_with('-alpha',.35)
if __name__=='__main__':unittest.main()
