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

    def test_default_bridge_paths_are_ue4ss_and_cheat_engine(self):
        paths=rs.default_bridge_paths(self.data)
        self.assertEqual([Path(p).name for p in paths],["orcish_scout_ue4ss.jsonl","cheat_engine.jsonl"])

    def test_prepare_creates_hooks_file_table_and_folders(self):
        r=rs.prepare(self.root,self.data)
        self.assertEqual(r,{"hooks_file":"created","cheat_table":"created"})
        self.assertTrue(rs.ue4ss_scans(self.data).is_dir());self.assertTrue(rs.ce_output(self.data).parent.is_dir())
        self.assertIn("scan Fish",rs.ue4ss_hooks(self.data).read_text(encoding="utf-8"))
        lua=self.lua_script()
        self.assertIn(str(rs.ce_output(self.data)),lua);self.assertIn(str(rs.ce_script(self.root)),lua)
        self.assertIn("dofile(",lua)

    def test_prepare_never_overwrites_user_hooks(self):
        p=rs.ue4ss_hooks(self.data);p.parent.mkdir(parents=True);p.write_text("function mine = /Game/X:Y\n",encoding="utf-8")
        self.assertEqual(rs.prepare(self.root,self.data)["hooks_file"],"exists")
        self.assertEqual(p.read_text(encoding="utf-8"),"function mine = /Game/X:Y\n")

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

    def test_lua_long_string_survives_closing_brackets(self):
        self.assertEqual(rs._lua_long(r"C:\a]]b"),r"[=[C:\a]]b]=]")
        self.assertEqual(rs._lua_long(r"C:\a]=]b"),r"[==[C:\a]=]b]==]")
        self.assertEqual(rs._lua_long(r"C:\plain"),r"[=[C:\plain]=]")

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

    def test_hook_suggestions_come_from_unique_scanned_functions(self):
        d=rs.ue4ss_scans(self.data);d.mkdir(parents=True);scan=d/"scan_1.jsonl"
        rows=[{"kind":"function","hook_name":"/Game/F/BP_Rod.BP_Rod_C:OnFishBite"},
              {"kind":"function","hook_name":"/Game/F/BP_Rod.BP_Rod_C:OnFishBite"},
              {"kind":"object","full_name":"BP_Rod_C /Game/Maps/M.M:PersistentLevel.BP_Rod_C_1"},
              {"kind":"function","hook_name":"/Script/Game.FishingComponent:ReelIn"}]
        scan.write_text("\n".join(json.dumps(r) for r in rows)+"\n",encoding="utf-8")
        self.assertEqual(rs.latest_scan(self.data),scan)
        self.assertEqual(rs.hook_suggestions(scan),[
            "function onfishbite = /Game/F/BP_Rod.BP_Rod_C:OnFishBite",
            "function reelin = /Script/Game.FishingComponent:ReelIn"])


if __name__=="__main__":unittest.main()
