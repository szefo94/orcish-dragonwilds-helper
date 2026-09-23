import unittest
import numpy as np
from aim_lab import impact_features, moving_candidates

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

    def test_motion_candidates_find_localized_motion_in_playfield(self):
        a=np.zeros((300,500,3),dtype=np.uint8)
        b=a.copy();b[120:180,220:280]=(255,255,255)
        found=moving_candidates(b,a)
        self.assertTrue(found)
        x,y,w,h=found[0]["bbox"]
        self.assertLessEqual(x,220);self.assertLessEqual(y,120)
        self.assertGreaterEqual(x+w,280);self.assertGreaterEqual(y+h,180)
        self.assertEqual(found[0]["source"],"motion")

    def test_motion_candidates_ignore_top_hud_motion(self):
        a=np.zeros((300,500,3),dtype=np.uint8)
        b=a.copy();b[10:45,210:290]=(255,255,255)
        self.assertEqual(moving_candidates(b,a),[])

    def test_motion_candidates_skip_global_camera_change(self):
        a=np.zeros((300,500,3),dtype=np.uint8)
        b=np.full_like(a,255)
        self.assertEqual(moving_candidates(b,a),[])

if __name__=="__main__":unittest.main()
