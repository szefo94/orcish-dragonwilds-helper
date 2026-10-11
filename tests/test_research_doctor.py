"""research_setup: scan-assistant command path in the loader, quick status, doctor and report."""
import json, tempfile, time, unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import research_setup as rs


class ResearchDoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
        self.root=base/"root";self.data=self.root/"data"
        (self.root/"tools"/"cheat-engine").mkdir(parents=True)
        rs.ce_script(self.root).write_text("-- bridge",encoding="utf-8")

    def tearDown(self):self.tmp.cleanup()

    def test_loader_block_hands_the_command_file_to_the_bridge(self):
        rs.prepare(self.root,self.data)
        lua=ET.parse(rs.ce_table(self.data)).getroot().find("LuaScript").text
        self.assertIn("ORCISH_SCOUT_CE_COMMANDS",lua);self.assertIn(str(rs.ce_commands(self.data)),lua)
        self.assertEqual(rs.ce_commands(self.data).parent,rs.ce_output(self.data).parent)

    def test_quick_status_skips_line_count(self):
        p=rs.ce_output(self.data);p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"provider":"cheat_engine","signal":"heartbeat"})+"\n",encoding="utf-8")
        s=rs.source_status(p,quick=True)
        self.assertIsNone(s["lines"]);self.assertEqual(s["last_signal"],"heartbeat")
        self.assertEqual(rs.status(self.root,self.data,quick=True)["cheat_engine"]["lines"],None)

    def test_doctor_on_fresh_install_prepares_and_points_to_cheat_engine(self):
        d=rs.doctor(self.root,self.data)
        self.assertEqual(d["prepared"]["cheat_table"],"created")
        self.assertEqual(d["candidates"],{});self.assertIsNone(d["latest_session"])
        steps=" ".join(d["next_steps"])
        self.assertIn("OrcishScout.CT",steps);self.assertIn("No Scout session yet",steps)

    def test_doctor_reads_candidates_and_latest_session(self):
        (self.data).mkdir(parents=True)
        (self.data/"settings.json").write_text(json.dumps({"Dragonwilds":{"scout_memory_candidates":[
            {"name":"phase","domain":"fishing","role":"phase","spec":"0x10:u32"},{"name":"x","domain":"general","role":"state","spec":"0x20:u8"}]}}),encoding="utf-8")
        s=self.data/"scout_sessions"/"20260923-120000-abc";s.mkdir(parents=True)
        (s/"manifest.json").write_text(json.dumps({"domain":"fishing","run":"Live"}),encoding="utf-8")
        (s/"controller.jsonl").write_text("{}\n{}\n",encoding="utf-8");(s/"memory.jsonl").write_text("",encoding="utf-8")
        (s/"process.jsonl").write_text(json.dumps({"source":"game_internal","signal":"property_change"})+"\n",encoding="utf-8")
        p=rs.ce_output(self.data);p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps({"provider":"cheat_engine","signal":"property_change"})+"\n",encoding="utf-8")
        d=rs.doctor(self.root,self.data,now=time.time())
        self.assertEqual(d["candidates"],{"fishing":1,"general":1})
        latest=d["latest_session"]
        self.assertEqual((latest["name"],latest["domain"],latest["controller"],latest["memory"],latest["game_internal"]),("20260923-120000-abc","fishing",2,0,1))
        self.assertEqual(len(d["next_steps"]),1);self.assertIn("Fish 10",d["next_steps"][0])

    def test_report_without_sessions(self):
        self.assertEqual(rs.report(self.data),(None,None))


if __name__=="__main__":unittest.main()
