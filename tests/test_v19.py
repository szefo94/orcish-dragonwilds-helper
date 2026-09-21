"""1.9: key table, merged Hold tab (constant / timed), precise repeat scheduling, per-tab visibility."""
import unittest
from engine import Controller
import keys

class Keys(unittest.TestCase):
    def test_aliases_resolve_to_same_key(self):
        for a in ('LMB','LButton','left mouse','Mouse1','lmb — left mouse'):self.assertEqual(keys.resolve(a).name,'LMB')
        self.assertEqual(keys.resolve('XButton2').name,'Mouse 5');self.assertEqual(keys.resolve('Mouse 5').data,2)
        self.assertEqual(keys.resolve('pgup').name,'Page Up');self.assertEqual(keys.resolve('arrow left').vk,0x25)
        self.assertEqual(keys.resolve('num7').vk,0x67);self.assertEqual(keys.resolve('e').vk,ord('E'))
    def test_extended_flags(self):
        self.assertEqual(keys.resolve('Up').extended,1);self.assertEqual(keys.resolve('Delete').extended,1)
        self.assertEqual(keys.resolve('Space').extended,0);self.assertEqual(keys.resolve('Right Ctrl').extended,1)
    def test_function_keys_and_reserved(self):
        self.assertEqual(keys.resolve('F1').vk,0x70);self.assertEqual(keys.resolve('f24').vk,0x87)
        with self.assertRaises(ValueError):keys.resolve('F8')
        for bad in ('\\\\','F25','banana',''):
            with self.assertRaises(ValueError):keys.resolve(bad)
    def test_dropdown_all_resolve_and_no_f8(self):
        names=keys.dropdown();self.assertNotIn('F8',names);self.assertIn('LMB',names);self.assertIn('Page Down',names)
        for n in names:self.assertEqual(keys.resolve(n).name,n)
    def test_mouse_flags(self):
        k=keys.resolve('RMB');self.assertEqual((k.kind,k.down,k.up),('mouse',8,16))

class HoldModes(unittest.TestCase):
    def setUp(self):self.ev=[];self.c=Controller(lambda k,d:self.ev.append((k,d)))
    def test_constant_hold_until_stopped(self):
        self.c.start('Hold','LMB',.1,.05);self.c.tick(0,True);self.c.tick(100,True)
        self.assertEqual(self.ev,[('LMB',True)]);self.assertIsNone(self.c.next_due(100))
        self.c.stop();self.assertEqual(self.ev,[('LMB',True),('LMB',False)])
    def test_timed_hold_releases_and_reports(self):
        self.c.start('Timed','E',.1,1.5);self.c.tick(10,True)
        self.assertAlmostEqual(self.c.next_due(10.5),1.0);self.c.tick(11.49,True);self.assertTrue(self.c.running)
        self.c.tick(11.5,True);self.assertFalse(self.c.running);self.assertAlmostEqual(self.c.finished,1.5)
        self.assertEqual(self.ev,[('E',True),('E',False)])
    def test_repeat_schedule_does_not_drift(self):
        self.c.start('Repeat','Space',.1,.05);t=0.;downs=[]
        for i in range(2000):
            t+=0.0137                               # coarse, irregular wake-ups
            n=len(self.ev);self.c.tick(t,True)
            if len(self.ev)>n and self.ev[-1][1]:downs.append(t)
        rate=(len(downs)-1)/(downs[-1]-downs[0]);self.assertAlmostEqual(rate,10,delta=.2)
    def test_repeat_after_stall_restarts_not_bursts(self):
        self.c.start('Repeat','Space',.1,.05);self.c.tick(0,True);self.c.tick(.06,True)
        self.c.tick(5,True);n=len([e for e in self.ev if e[1]]);self.c.tick(5.001,True);self.c.tick(5.06,True);self.c.tick(5.07,True)
        self.assertEqual(len([e for e in self.ev if e[1]]),n)   # no catch-up burst
    def test_per_run_press_counter(self):
        self.c.start('Repeat','Space',.1,.05);self.c.tick(0,True);self.c.tick(.2,True)
        self.c.start('Repeat','Space',.1,.05);self.assertEqual(self.c.count-self.c.base_count,0)
if __name__=='__main__':unittest.main()
