import unittest
import numpy as np
from aim_lab import impact_features

class AimLabTests(unittest.TestCase):
    def test_impact_features_detects_change_and_warm_pixels(self):
        a=np.zeros((40,60,3),dtype=np.uint8)
        b=a.copy();b[10:20,20:30]=(20,40,240)
        f=impact_features(b,a)
        self.assertGreater(f["change"],0)
        self.assertGreater(f["warm"],0)

    def test_impact_features_stable_frame_has_no_change(self):
        a=np.full((30,30,3),80,dtype=np.uint8)
        f=impact_features(a,a.copy())
        self.assertEqual(f["change"],0.0)
        self.assertIn("bright",f)
        self.assertIn("yellow",f)

if __name__=="__main__":unittest.main()
