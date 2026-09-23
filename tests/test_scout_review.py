import csv,tempfile,unittest
from pathlib import Path
import cv2
import numpy as np
from scout_review import read_labels,write_labels,analyze_rows,counts

class ScoutReviewTests(unittest.TestCase):
    def _session(self,td):
        s=Path(td);(s/"samples").mkdir()
        rows=[
            ["00001","0","1.0","samples/a.png","crosshair","320","180","",""],
            ["00001","250","1.25","samples/b.png","crosshair","320","180","",""],
        ]
        with (s/"labels.csv").open("w",encoding="utf-8",newline="") as f:
            w=csv.writer(f);w.writerow(["sample_id","delay_ms","mono","image","focus_source","focus_x","focus_y","label","notes"]);w.writerows(rows)
        a=np.zeros((360,640,3),dtype=np.uint8);b=a.copy();b[140:210,280:350]=(20,40,240)
        cv2.imwrite(str(s/"samples"/"a.png"),a);cv2.imwrite(str(s/"samples"/"b.png"),b)
        return s

    def test_adds_analysis_and_review_columns(self):
        with tempfile.TemporaryDirectory() as td:
            s=self._session(td);fields,rows=read_labels(s/"labels.csv")
            self.assertIn("analysis_status",fields);self.assertIn("review_status",fields)
            self.assertEqual(counts(rows),(2,0,0))

    def test_analyzes_only_unanalyzed_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            s=self._session(td);fields,rows=read_labels(s/"labels.csv")
            self.assertEqual(analyze_rows(s,rows),2)
            self.assertEqual(rows[0]["suggested_label"],"aim_context")
            first_reason=rows[0]["suggestion_reason"]
            self.assertEqual(analyze_rows(s,rows),0)
            self.assertEqual(rows[0]["suggestion_reason"],first_reason)
            write_labels(s/"labels.csv",fields,rows)
            _,again=read_labels(s/"labels.csv");self.assertEqual(again[0]["analysis_status"],"proposed")

if __name__=="__main__":unittest.main()
