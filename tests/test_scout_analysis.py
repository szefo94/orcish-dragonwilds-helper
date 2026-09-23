import json, tempfile, unittest
from pathlib import Path
from scout_analysis import analyze_session, sha256_file, write_report, write_all_reports

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
                {"mono":1.0,"source":"vision","signal":"prompt","value":{"action":"Collect","key":"E","hold":False,"source":"ocr"},"confidence":.9,"latency_ms":40,"fresh_ms":50,"details":{"capture_ms":5,"detect_ms":30,"total_worker_ms":38,"detected_mono":1.04,"consumed_mono":1.05}},
                {"mono":2.0,"source":"vision","signal":"prompt","value":None,"latency_ms":35,"fresh_ms":45,"details":{"capture_ms":4,"detect_ms":25,"total_worker_ms":32,"detected_mono":2.035,"consumed_mono":2.045}}
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
            self.assertAlmostEqual(r["fishing"]["state_transitions"][0]["duration_s"],.5)
            self.assertEqual(r["fishing"]["reel_entries"],1)
            self.assertEqual(r["latency_ms"]["median"],85.0)
            self.assertTrue(r["raw_logs_preserved"])

    def test_auto_picker_prompt_transitions(self):
        with tempfile.TemporaryDirectory() as td:
            s=self._session(td,"auto_picker");r=analyze_session(s)
            self.assertEqual(r["auto_picker"]["approved"],1)
            self.assertEqual(r["auto_picker"]["sent_decisions"],1)
            self.assertEqual(len(r["auto_picker"]["prompt_transitions"]),2)
            self.assertEqual(r["stage_timing_ms"]["capture"]["median"],4.5)
            self.assertEqual(r["stage_timing_ms"]["detect"]["median"],27.5)

    def test_all_sessions_generates_combined_reports_and_preserves_raw(self):
        with tempfile.TemporaryDirectory() as td:
            s1=self._session(td,"fishing")
            s2=Path(td)/"scout_sessions"/"20260923-080000-auto";s2.mkdir(parents=True)
            (s2/"manifest.json").write_text(json.dumps({"schema":1,"session_id":"y","domain":"auto_picker","run":"Live"}),encoding="utf-8")
            (s2/"summary.json").write_text(json.dumps({"events":2,"reason":"done"}),encoding="utf-8")
            (s2/"vision.jsonl").write_text(json.dumps({"mono":20.0,"source":"vision","signal":"prompt","value":{"action":"Collect","key":"E","hold":False,"source":"ocr"},"latency_ms":30,"fresh_ms":40})+"\n",encoding="utf-8")
            (s2/"controller.jsonl").write_text(json.dumps({"mono":20.1,"source":"controller","signal":"decision","value":{"sent":True}})+"\n",encoding="utf-8")
            (s2/"process.jsonl").write_text("",encoding="utf-8")
            before={}
            for s in (s1,s2):
                before[s.name]={p.name:sha256_file(p) for p in s.iterdir() if p.is_file()}
            sessions,jp,mp,combo=write_all_reports(td)
            self.assertEqual(len(sessions),2)
            self.assertEqual(combo["domains"],{"fishing":1,"auto_picker":1,"aim":0,"scout_lab":0})
            self.assertTrue(jp.is_file());self.assertTrue(mp.is_file())
            self.assertEqual(jp.name,"ALL_SESSIONS.json");self.assertEqual(mp.name,"ALL_SESSIONS.md")
            for s in (s1,s2):
                after={p.name:sha256_file(p) for p in s.iterdir() if p.is_file()}
                self.assertEqual(before[s.name],after)

    def test_scout_lab_summary(self):
        with tempfile.TemporaryDirectory() as td:
            s=Path(td)/"scout_sessions"/"20260923-090000-lab";s.mkdir(parents=True)
            (s/"manifest.json").write_text(json.dumps({"schema":1,"session_id":"z","domain":"scout_lab","run":"Research"}),encoding="utf-8")
            (s/"summary.json").write_text(json.dumps({"events":5,"reason":"done"}),encoding="utf-8")
            (s/"vision.jsonl").write_text(
                json.dumps({"mono":1.0,"source":"vision","signal":"cursor_probe","value":{"screen":[100,100]}})+"\n"+
                json.dumps({"mono":1.1,"source":"vision","signal":"crosshair_probe","value":{"screen":[200,200]}})+"\n",encoding="utf-8")
            (s/"controller.jsonl").write_text("",encoding="utf-8")
            (s/"process.jsonl").write_text("",encoding="utf-8")
            (s/"memory.jsonl").write_text(json.dumps({"mono":1.2,"source":"memory","signal":"watch","value":{"spec":"game.exe+0x10:u32","ok":True,"value":7}})+"\n",encoding="utf-8")
            (s/"annotations.jsonl").write_text(json.dumps({"mono":1.3,"source":"annotation","signal":"mark","value":"head"})+"\n",encoding="utf-8")
            r=analyze_session(s)
            self.assertEqual(r["scout_lab"]["cursor_probes"],1)
            self.assertEqual(r["scout_lab"]["memory_samples"],1)
            self.assertEqual(r["scout_lab"]["memory_success_pct"],100.0)
            self.assertEqual(r["scout_lab"]["annotations"][0]["label"],"head")
            self.assertIn("memory.jsonl",r["source_hashes"])

    def test_aim_summary_and_sidecar_streams(self):
        with tempfile.TemporaryDirectory() as td:
            s=Path(td)/"scout_sessions"/"20260923-100000-aim";s.mkdir(parents=True)
            (s/"manifest.json").write_text(json.dumps({"schema":1,"session_id":"a","domain":"aim","run":"Research"}),encoding="utf-8")
            (s/"summary.json").write_text(json.dumps({"events":8,"reason":"done"}),encoding="utf-8")
            tracks=[
                {"mono":1.0,"source":"vision","signal":"aim_track","confidence":.8,"value":{"id":1,"bbox":[10,20,40,80],"crosshair_error":[10,0]}},
                {"mono":1.1,"source":"vision","signal":"aim_track","confidence":.9,"value":{"id":1,"bbox":[12,20,40,80],"crosshair_error":[5,0]}},
                {"mono":1.2,"source":"vision","signal":"impact_candidate","value":{"candidate":True,"change":.1}}
            ]
            (s/"vision.jsonl").write_text("".join(json.dumps(x)+"\n" for x in tracks),encoding="utf-8")
            (s/"controller.jsonl").write_text("",encoding="utf-8")
            (s/"process.jsonl").write_text("",encoding="utf-8")
            (s/"memory.jsonl").write_text(json.dumps({"mono":1.05,"source":"memory","signal":"watch","value":{"spec":"game.exe+0x20:f32","ok":True,"value":12.5}})+"\n",encoding="utf-8")
            anns=[
                {"mono":.9,"source":"annotation","signal":"target_seed","value":{"id":1}},
                {"mono":1.25,"source":"annotation","signal":"aim_mark","value":{"label":"crit"}}
            ]
            (s/"annotations.jsonl").write_text("".join(json.dumps(x)+"\n" for x in anns),encoding="utf-8")
            (s/"system.jsonl").write_text(json.dumps({"mono":.8,"source":"system","signal":"sidecar_started","value":{"watches":1}})+"\n",encoding="utf-8")
            r=analyze_session(s)
            self.assertEqual(r["aim"]["track_samples"],2)
            self.assertEqual(r["aim"]["seeded_targets"],1)
            self.assertEqual(r["aim"]["impact_candidates"],1)
            self.assertEqual(r["aim"]["target_ids"],["1"])
            self.assertEqual(r["independent_scout"]["memory_samples"],1)
            self.assertEqual(r["independent_scout"]["memory_success_pct"],100.0)
            self.assertIn("system.jsonl",r["source_hashes"])

    def test_lmb_sample_labels_are_summarized_without_modification(self):
        with tempfile.TemporaryDirectory() as td:
            s=self._session(td,"auto_picker")
            labels=s/"labels.csv"
            labels.write_text(
                "sample_id,delay_ms,mono,image,focus_source,focus_x,focus_y,label,notes\n"
                "00001,0,1.0,samples/a.png,crosshair,400,300,target,body\n"
                "00001,250,1.25,samples/b.png,crosshair,400,300,crit,damage marker\n"
                "00002,0,2.0,samples/c.png,cursor,120,220,,\n",encoding="utf-8")
            before=sha256_file(labels);r=analyze_session(s);after=sha256_file(labels)
            self.assertEqual(before,after)
            self.assertEqual(r["lmb_samples"]["sample_ids"],2)
            self.assertEqual(r["lmb_samples"]["frames"],3)
            self.assertEqual(r["lmb_samples"]["labeled_frames"],2)
            self.assertEqual(r["lmb_samples"]["labels"],{"target":1,"crit":1})
            self.assertIn("labels.csv",r["source_hashes"])

if __name__=="__main__":unittest.main()
