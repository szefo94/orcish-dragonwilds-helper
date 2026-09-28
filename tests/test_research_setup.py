import json, os, tempfile, time, unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import research_setup as rs


class ResearchSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
        self.root=base/"root";self.data=self.root/"data"
        (self.root/"tools"/"cheat-engine").mkdir(parents=True)
        rs.ce_script(self.root).write_text("-- bridge",encoding="utf-8")

    def tearDown(self):self.tmp.cleanup()

    def lua_script(self):
        return ET.parse(rs.ce_table(self.data)).getroot().find("LuaScript").text

    def test_default_bridge_paths_are_cheat_engine_and_ue4ss(self):
        paths=rs.default_bridge_paths(self.data)
        self.assertEqual([Path(p).name for p in paths],["cheat_engine.jsonl","orcish_scout_ue4ss.jsonl"])

    def test_prepare_creates_table_and_output_folder(self):
        self.assertEqual(rs.prepare(self.root,self.data),{"cheat_table":"created"})
        self.assertTrue(rs.ce_output(self.data).parent.is_dir())
        lua=self.lua_script()
        self.assertIn(str(rs.ce_output(self.data)),lua);self.assertIn(str(rs.ce_script(self.root)),lua)
        self.assertIn("dofile(",lua)

    def test_table_refresh_updates_loader_and_keeps_user_entries(self):
        rs.prepare(self.root,self.data)
        t=rs.ce_table(self.data)
        user_entry='<CheatEntry><ID>7</ID><Description>"fishing phase"</Description></CheatEntry>'
        t.write_text(t.read_text(encoding="utf-8").replace("<CheatEntries>\n","<CheatEntries>\n"+user_entry+"\n"),encoding="utf-8")
        self.assertEqual(rs.ensure_cheat_table(self.root,self.data),"unchanged")
        moved=self.root.parent/"moved & copied";(moved/"tools"/"cheat-engine").mkdir(parents=True)   # re-extracted elsewhere
        self.assertEqual(rs.ensure_cheat_table(moved,self.data),"refreshed")
        text=t.read_text(encoding="utf-8")
        self.assertIn(user_entry,text)
        self.assertIn(str(rs.ce_script(moved)),self.lua_script())   # '&' was XML-escaped, so it parses back
        self.assertEqual(text.count("ORCISH-SCOUT-LOADER BEGIN"),1)

    def test_table_without_loader_is_left_alone(self):
        t=rs.ce_table(self.data);t.parent.mkdir(parents=True);t.write_text("<CheatTable/>",encoding="utf-8")
        self.assertEqual(rs.ensure_cheat_table(self.root,self.data),"unmanaged")
        self.assertEqual(t.read_text(encoding="utf-8"),"<CheatTable/>")

    def test_lua_long_string_cannot_be_closed_by_path(self):
        self.assertEqual(rs._lua_long(r"C:\a]]b"),r"[=[C:\a]]b]=]")
        self.assertEqual(rs._lua_long(r"C:\a]=]b"),r"[==[C:\a]=]b]==]")

    def test_source_status_reports_lines_last_signal_and_age(self):
        p=rs.ce_output(self.data);p.parent.mkdir(parents=True)
        p.write_text("\n".join(json.dumps(x) for x in (
            {"provider":"cheat_engine","signal":"bridge_start"},{"provider":"cheat_engine","signal":"property_change","value":3},
        ))+"\nnot json\n",encoding="utf-8")
        now=time.time();os.utime(p,(now-30,now-30))
        s=rs.source_status(p,now=now)
        self.assertEqual(s["lines"],3);self.assertEqual(s["last_signal"],"property_change")
        self.assertEqual(s["signals"],["bridge_start","property_change"]);self.assertAlmostEqual(s["age_s"],30,delta=1)
        self.assertFalse(rs.source_status(self.data/"missing.jsonl")["exists"])


if __name__=="__main__":unittest.main()
