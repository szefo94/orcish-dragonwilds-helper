"""Regression checks for 1.1 without a Windows desktop."""
import unittest
from unittest.mock import Mock
from app import App
from engine import Controller
from vision import associate

class UpdateTests(unittest.TestCase):
    def app(self):
        a=App.__new__(App)
        a.visual=False;a.root=Mock();a.root.winfo_rootx.return_value=0;a.root.winfo_rooty.return_value=0
        a.root.winfo_width.return_value=920;a.root.winfo_height.return_value=780
        a.io=Mock();a.io.tripped=False;a.io.foreground.return_value=10
        a.io.own.side_effect=lambda h:h==20;a.io.pressed.return_value=False
        a.opacity=Mock();a.opacity.get.return_value=60
        a.previous_hot=False;a.selecting=False;a.armed=False;a.target=10;a.mode='Hold'
        a.generation=0;a.status=Mock();a.startbutton=Mock();a.drain=Mock()
        a.events=[];a.ctrl=Controller(lambda k,d:a.events.append((k,d)))
        a.ctrl.start('Hold','E',.1,.05);a.ctrl.tick(0,True)
        return a
    def test_hover_keeps_running_and_unfocused_opacity(self):
        a=self.app();a.tick()
        self.assertTrue(a.ctrl.running);self.assertEqual(a.ctrl.held,'E')
        a.io.u.GetCursorPos.assert_not_called()
        a.root.attributes.assert_called_with('-alpha',.6)
        self.assertEqual(a.events,[('E',True)])
    def test_panel_focus_stops_and_restores_opacity(self):
        a=self.app();a.io.foreground.return_value=20;a.tick()
        self.assertFalse(a.ctrl.running);self.assertIsNone(a.ctrl.held)
        self.assertEqual(a.events,[('E',True),('E',False)])
        a.root.attributes.assert_called_with('-alpha',1.)
    def test_harvest_reads_key_and_hold_and_respects_allowlist(self):
        cap=[(250,20,35,35)]
        for label,hold in [('Harvest',False),('Harvest [Hold]',True)]:
            items=[(10,20,230,55,label,.99),(258,25,278,50,'F',.99)]
            found=associate(cap,items,['Harvest'])
            self.assertEqual(len(found),1)
            self.assertEqual(found[0].identity,('Harvest','F',hold))
            self.assertEqual(associate(cap,items,['Collect']),[])
    def test_fill_compost_bucket(self):
        cap=[(350,20,35,35)]
        for label,hold in [('Fill compost Bucket',False),('Fill Compost Bucket [Hold]',True)]:
            items=[(10,20,330,55,label,.99),(358,25,378,50,'F',.99)]
            found=associate(cap,items,['Fill Compost Bucket'])
            self.assertEqual(len(found),1)
            self.assertEqual(found[0].identity,('Fill Compost Bucket','F',hold))
            self.assertEqual(associate(cap,items,['Fill Watering Can','Collect']),[])
if __name__=='__main__':unittest.main()
