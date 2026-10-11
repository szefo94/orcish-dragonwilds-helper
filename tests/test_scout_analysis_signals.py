"""Analyzer additions: producer-clock alignment, shadow agreement and scan-assistant sections."""
import json, tempfile, unittest
from pathlib import Path
from scout_analysis import align_producer_clock, analyze_session, markdown, shadow_agreement


def _write(path,rows):path.write_text("".join(json.dumps(x)+"\n" for x in rows),encoding="utf-8")


class ClockAlignment(unittest.TestCase):
    def test_offset_is_the_least_delayed_ingest(self):
        events=[{"mono":10.62,"details":{"provider":"cheat_engine","producer_time":100.0}},
                {"mono":10.90,"details":{"provider":"cheat_engine","producer_time":100.2}},
                {"mono":11.00,"details":{"provider":"ue4ss"}}]
        out=align_producer_clock(events)
        self.assertEqual(set(out),{"cheat_engine"})
        self.assertAlmostEqual(out["cheat_engine"]["offset_s"],10.62-100.0)
        self.assertEqual(out["cheat_engine"]["samples"],2)
        self.assertAlmostEqual(out["cheat_engine"]["max_delay_ms"],80,delta=.5)
        self.assertAlmostEqual(events[1]["aligned_mono"],10.82)
        self.assertNotIn("aligned_mono",events[2])


class ShadowAgreement(unittest.TestCase):
    def decisions(self):
        rows=[]
        for i,(state,phase,noise) in enumerate([("WAIT_BITE",2,5),("WAIT_BITE",2,6),("FIGHT",3,5),("FIGHT",3,7),("REEL",3,5),("REEL",4,5)]):
            rows.append({"mono":10+i*.1,"source":"controller","signal":"fishing_decision","value":{"state":state,"held":None},
                         "details":{"reason":"r","signals":{"fishing phase":{"role":"phase","value":phase,"source":"memory","age_ms":50},
                                                            "timer":{"role":"unknown","value":noise,"source":"cheat_engine","age_ms":90}}}})
        rows.append({"mono":20,"source":"controller","signal":"fishing_decision","value":{"state":"FIGHT"},"details":{"reason":"no signals"}})
        return rows

    def test_purity_separates_a_phase_signal_from_noise(self):
        rows=shadow_agreement(self.decisions())
        self.assertEqual([r["name"] for r in rows],["fishing phase","timer"])
        phase,timer=rows
        self.assertEqual(phase["samples"],6);self.assertAlmostEqual(phase["purity"],5/6)
        self.assertEqual(phase["states"]["WAIT_BITE"],{2:2});self.assertEqual(phase["states"]["REEL"],{3:1,4:1})
        self.assertEqual(phase["values_seen_in_several_states"],[3])      # 3 appears in FIGHT and REEL
        self.assertLess(timer["purity"],phase["purity"]);self.assertEqual(timer["source"],"cheat_engine")

    def test_report_and_markdown_include_new_sections(self):
        with tempfile.TemporaryDirectory() as td:
            s=Path(td)/"scout_sessions"/"20260923-100000-shadow";s.mkdir(parents=True)
            (s/"manifest.json").write_text(json.dumps({"schema":1,"session_id":"s","domain":"fishing","run":"Live"}),encoding="utf-8")
            (s/"summary.json").write_text(json.dumps({"events":1}),encoding="utf-8")
            _write(s/"vision.jsonl",[{"mono":10.0,"source":"vision","signal":"fishing_observation","value":{"color":"red","text":"","stop":False},"latency_ms":1,"fresh_ms":1,"details":{}}])
            _write(s/"controller.jsonl",self.decisions())
            _write(s/"process.jsonl",[
                {"mono":10.25,"source":"game_internal","signal":"property_change","value":3,"details":{"provider":"cheat_engine","property":"fishing phase","producer_time":500.0}},
                {"mono":10.45,"source":"game_internal","signal":"scan_result","value":1200,"details":{"provider":"cheat_engine","seq":2,"producer_time":500.1}}])
            _write(s/"annotations.jsonl",[{"mono":10.1,"source":"annotation","signal":"scan_command","value":{"seq":2,"cmd":"next","arg":"changed","state":"FIGHT","phase":"fight"}}])
            r=analyze_session(s)
            self.assertEqual(r["shadow_agreement"][0]["name"],"fishing phase")
            self.assertEqual(r["game_internal"]["clock_alignment"]["cheat_engine"]["samples"],2)
            self.assertEqual(len(r["scan_assistant"]["commands"]),1);self.assertEqual(r["scan_assistant"]["replies"][0]["seq"],2)
            md=markdown(r)
            for needle in ("## Shadow agreement","fishing phase (phase, memory)","## Cheat Engine scan assistant","Clock alignment cheat_engine"):
                self.assertIn(needle,md)


if __name__=="__main__":unittest.main()
