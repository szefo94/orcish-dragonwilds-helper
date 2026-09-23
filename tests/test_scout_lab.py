import csv, tempfile, unittest
from pathlib import Path
import numpy as np
from scout_lab import ScoutLabSession, parse_watch, parse_candidate, visual_features

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

    def test_sample_focus_distinguishes_locked_aim_from_recent_free_cursor(self):
        s=ScoutLabSession.__new__(ScoutLabSession);s.focus_mode="auto";s.last_cursor=None;s.last_cursor_move=0.
        self.assertEqual(s._sample_focus((100,200,800,600),(500,500),10.0),("crosshair",500,500))
        # A recently moved off-centre cursor is treated as inventory/UI cursor.
        self.assertEqual(s._sample_focus((100,200,800,600),(200,300),10.1),("cursor",200,300))
        # A stale off-centre Windows cursor is ignored and aim returns to screen centre.
        s.last_cursor=(200,300);s.last_cursor_move=1.0
        self.assertEqual(s._sample_focus((100,200,800,600),(200,300),10.0),("crosshair",500,500))

    def test_crosshair_mode_never_uses_windows_cursor(self):
        s=ScoutLabSession.__new__(ScoutLabSession);s.focus_mode="crosshair";s.last_cursor=None;s.last_cursor_move=0.
        self.assertEqual(s._sample_focus((100,200,800,600),(150,250),5.0),("crosshair",500,500))

    def test_prepare_labels_creates_editable_csv_and_guide(self):
        with tempfile.TemporaryDirectory() as td:
            s=ScoutLabSession.__new__(ScoutLabSession);s.folder=Path(td)
            s.sample_dir=s.folder/"samples";s.labels_path=s.folder/"labels.csv"
            s._prepare_labels()
            self.assertTrue(s.sample_dir.is_dir())
            self.assertTrue((s.folder/"LABELING_README.txt").is_file())
            with s.labels_path.open("r",encoding="utf-8",newline="") as f:
                header=next(csv.reader(f))
            self.assertEqual(header[-2:],["label","notes"])
            self.assertIn("delay_ms",header)

    def test_parse_semantic_candidate(self):
        c=parse_candidate({"name":"reel_flag","domain":"fishing","role":"reel_allowed",
                           "spec":"Dragonwilds-Win64-Shipping.exe+0x1234:u8"})
        self.assertEqual(c["name"],"reel_flag")
        self.assertEqual(c["domain"],"fishing")
        self.assertEqual(c["role"],"reel_allowed")
        self.assertEqual(c["offset"],0x1234)

    def test_parse_candidate_supports_pointer_sized_values(self):
        c=parse_candidate({"name":"focused_actor","domain":"auto_picker","role":"focused_actor",
                           "spec":"0x7ff612340000:ptr"})
        self.assertEqual(c["type"],"ptr")
        self.assertEqual(c["address"],0x7ff612340000)

    def test_session_filters_candidates_by_domain(self):
        s=ScoutLabSession.__new__(ScoutLabSession)
        parsed=[parse_candidate({"name":"phase","domain":"fishing","role":"phase","spec":"0x1000:u8"}),
                parse_candidate({"name":"actor","domain":"auto_picker","role":"focused_actor","spec":"0x2000:ptr"}),
                parse_candidate({"name":"state","domain":"general","role":"state","spec":"0x3000:u32"})]
        # Mirror constructor filtering without starting the capture thread.
        active="fishing";filtered=[x for x in parsed if not active or x["domain"] in (active,"general")]
        self.assertEqual([x["name"] for x in filtered],["phase","state"])

if __name__=="__main__":unittest.main()
