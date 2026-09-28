import unittest

from ce_table import parse_cheat_table, record_spec
from scout_lab import merge_ce_candidates, parse_watch

TABLE = """<?xml version="1.0" encoding="utf-8"?>
<CheatTable CheatEngineTableVersion="45">
  <CheatEntries>
    <CheatEntry>
      <ID>0</ID>
      <Description>"Fishing"</Description>
      <GroupHeader>1</GroupHeader>
      <CheatEntries>
        <CheatEntry>
          <ID>1</ID>
          <Description>"fishing phase"</Description>
          <VariableType>4 Bytes</VariableType>
          <Address>"RSDragonwilds-WinGDK-Shipping.exe"+04A1230</Address>
          <Offsets>
            <Offset>88</Offset>
            <Offset>10</Offset>
          </Offsets>
        </CheatEntry>
        <CheatEntry>
          <ID>2</ID>
          <Description>"pull direction"</Description>
          <ShowAsSigned>1</ShowAsSigned>
          <VariableType>4 Bytes</VariableType>
          <Address>RSDragonwilds-WinGDK-Shipping.exe+1A0</Address>
        </CheatEntry>
      </CheatEntries>
    </CheatEntry>
    <CheatEntry><ID>3</ID><Description>"tension"</Description><VariableType>Float</VariableType><Address>7FF612340000</Address></CheatEntry>
    <CheatEntry><ID>4</ID><Description>"infinite bait"</Description><VariableType>Auto Assembler Script</VariableType></CheatEntry>
    <CheatEntry><ID>5</ID><Description>"aob hit"</Description><VariableType>4 Bytes</VariableType><Address>fishAOB+4</Address></CheatEntry>
    <CheatEntry><ID>6</ID><Description>"name"</Description><VariableType>String</VariableType><Address>7FF6000</Address></CheatEntry>
  </CheatEntries>
</CheatTable>
"""


class CheatTableTests(unittest.TestCase):
    def test_records_become_scout_specs(self):
        records,skipped=parse_cheat_table(TABLE)
        self.assertEqual(records,[
            # Offset index 0 (88) is applied last.
            {"name":"fishing phase","spec":"[[rsdragonwilds-wingdk-shipping.exe+0x4A1230]+0x10]+0x88:u32"},
            {"name":"pull direction","spec":"rsdragonwilds-wingdk-shipping.exe+0x1A0:i32"},
            {"name":"tension","spec":"0x7FF612340000:f32"},
        ])
        self.assertEqual([s["name"] for s in skipped],["infinite bait","aob hit","name"])
        for r in records:parse_watch(r["spec"])   # every exported spec is accepted by Scout

    def test_single_level_pointer(self):
        self.assertEqual(record_spec('"game.exe"+10',["8"],"Byte"),"[game.exe+0x10]+0x8:u8")

    def test_symbolic_offset_is_skipped(self):
        _,skipped=parse_cheat_table(TABLE.replace("<Offset>10</Offset>","<Offset>someSymbol</Offset>"))
        self.assertIn("fishing phase",[s["name"] for s in skipped])

    def test_merge_assigns_roles_from_descriptions_and_replaces_same_name(self):
        records,_=parse_cheat_table(TABLE)
        existing=[{"name":"tension","domain":"fishing","role":"tension","spec":"0x1:u8"},
                  {"name":"tension","domain":"auto_picker","role":"distance","spec":"0x2:u8"}]
        merged,added=merge_ce_candidates(existing,records,"fishing")
        self.assertEqual(added,3)
        by_name={(c["domain"],c["name"]):c for c in merged}
        self.assertEqual(by_name[("fishing","fishing phase")]["role"],"phase")
        self.assertEqual(by_name[("fishing","pull direction")]["role"],"pull_direction")
        self.assertEqual(by_name[("fishing","tension")]["spec"],"0x7FF612340000:f32")
        self.assertEqual(by_name[("auto_picker","tension")]["spec"],"0x2:u8")   # other domain untouched
        self.assertEqual(len(merged),4)


if __name__=="__main__":unittest.main()
