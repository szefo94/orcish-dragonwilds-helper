import json, tempfile, unittest
from pathlib import Path
from scout_analysis import analyze_session, sha256_file, write_report

class ScoutAnalyzerTests(unittest.TestCase):
    def _session(self,root,domain="fishing"):
        s=Path(root)/"scout_sessions"/"20260923-070000-test";s.mkdir(parents=True)
        (s/"manifest.json").write_text(json.dumps({"schema":1,"session_id":"x","domain":domain,"run":"Preview"}),encoding="utf-8")
        (s/"summary.json").write_text(json.dumps({"events":4,"reason":"done"}),encoding="utf-8")
        if domain=="fishing":
            vision=[
                {"mono":10.0,"source":"vision","signal":"fishing_observation","value":{"color":"unknown","text":"","stop":True,"pull_left":False,"pull_right":False},"latency_ms":80,"fresh_ms":100,"details":{"ocr_ms":70}},
                {"mono":10.5,"source":"vision","signal":"fishing_observation","value":{"color":"red","text":"Reel (Hold)","stop":False,"pull_left":True,"pull_right":True},"latency_ms":90,"fresh_ms":120,"details":{"ocr_ms":85}}
            ]
            controller=[
                {"mono":10.1,"source":"controller","signal":"fishing_decision","value":{"state":"WAIT_BITE","held":None},"details":{"reason":"waiting"}},
                {"mono":10.6,"source":"controller","signal":"fishing_decision","value":{"state":"REEL","held":"LMB"},"details":{"reason":"reel"}}
            ]
        else:
            vision=[
                {"mono":1.0,"source":"vision","signal":"prompt","value":{"action":"Collect","key":"E","hold":False,"source":"ocr"},"confidence":.9,"latency_ms":40,"fresh_ms":50},
                {"mono":2.0,"source":"vision","signal":"prompt","value":None,"latency_ms":35,"fresh_ms":45}
            ]
            controller=[{"mono":1.1,"source":"controller","signal":"decision","value":{"sent":True,"held":None,"running":True}}]
        (s/"vision.jsonl").write_text("".join(json.dumps(x)+"\n" for x in vision),encoding="utf-8")
        (s/"controller.jsonl").write_text("".join(json.dumps(x)+"\n" for x in controller),encoding="utf-8")
        (s/"process.jsonl").write_text(json.dumps({"mono":9.9,"source":"process","signal":"snapshot","value":{"pid":1}})+"\n",encoding="utf-8")
        return s

    def test_fishing_report_and_source_logs_are_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            s=self._session(td,"fishing")
            before={p.name:sha256_file(p) for p in s.iterdir() if p.is_file()}
            jp,mp,r=write_report(s,td)
            after={p.name:sha256_file(p) for p in s.iterdir() if p.is_file()}
            self.assertEqual(before,after)
            self.assertTrue(jp.is_file());self.assertTrue(mp.is_file())
            self.assertEqual(jp.parent,Path(td)/"scout_reports")
            self.assertEqual(r["fishing"]["state_transitions"][-1]["state"],"REEL")
            self.assertEqual(r["latency_ms"]["median"],85.0)
            self.assertTrue(r["raw_logs_preserved"])

    def test_auto_picker_prompt_transitions(self):
        with tempfile.TemporaryDirectory() as td:
            s=self._session(td,"auto_picker");r=analyze_session(s)
            self.assertEqual(r["auto_picker"]["approved"],1)
            self.assertEqual(r["auto_picker"]["sent_decisions"],1)
            self.assertEqual(len(r["auto_picker"]["prompt_transitions"]),2)

if __name__=="__main__":unittest.main()
