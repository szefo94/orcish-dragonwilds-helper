import unittest
import numpy as np
from scout_lab import parse_watch, visual_features

class ScoutLabTests(unittest.TestCase):
    def test_parse_module_relative_watch(self):
        w=parse_watch("Dragonwilds-Win64-Shipping.exe+0x1234:f32")
        self.assertEqual(w["module"],"dragonwilds-win64-shipping.exe")
        self.assertEqual(w["offset"],0x1234)
        self.assertEqual(w["type"],"f32")
        self.assertIsNone(w["address"])

    def test_parse_absolute_watch(self):
        w=parse_watch("0x7ff612340000:u32")
        self.assertEqual(w["address"],0x7ff612340000)
        self.assertEqual(w["type"],"u32")

    def test_invalid_watch_is_rejected(self):
        for s in ("bad","module+oops:f32","0x0:u32","0x123:string"):
            with self.assertRaises((ValueError,TypeError)):parse_watch(s)

    def test_visual_features_returns_center_and_patch_stats(self):
        frame=np.zeros((9,9,3),dtype=np.uint8)
        frame[:]=(10,20,30);frame[4,4]=(40,50,60)
        f=visual_features(frame)
        self.assertEqual(f["size"],[9,9])
        self.assertEqual(f["center_bgr"],[40.0,50.0,60.0])
        self.assertGreater(f["std"],0)

if __name__=="__main__":unittest.main()
