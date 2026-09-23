import json, tempfile, time, unittest
from pathlib import Path

from internal_telemetry import parse_function_hook, JsonlBridgeProvider


class InternalTelemetryTests(unittest.TestCase):
    def test_parse_module_relative_function_hook(self):
        h=parse_function_hook("reel=Dragonwilds-Win64-Shipping.exe+0x1234")
        self.assertEqual(h["label"],"reel")
        self.assertEqual(h["module"],"Dragonwilds-Win64-Shipping.exe")
        self.assertEqual(h["offset"],0x1234)

    def test_parse_hook_default_label(self):
        h=parse_function_hook("Dragonwilds-Win64-Shipping.exe+0x20")
        self.assertIn("0x20",h["label"])

    def test_jsonl_bridge_emits_new_events(self):
        events=[]
        def cb(source,signal,value,**kwargs):
            events.append((source,signal,value,kwargs))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"telemetry.jsonl"
            p.write_text("",encoding="utf-8")
            b=JsonlBridgeProvider(p,cb,from_end=True);b.start()
            with p.open("a",encoding="utf-8") as f:
                f.write(json.dumps({"provider":"ue4ss","signal":"function_call","value":"reel",
                                    "function":"/Game/Test:OnReel"})+"\n");f.flush()
            deadline=time.time()+2
            while not events and time.time()<deadline:time.sleep(.02)
            b.close()
        self.assertTrue(events)
        self.assertEqual(events[0][0],"game_internal")
        self.assertEqual(events[0][1],"function_call")
        self.assertEqual(events[0][2],"reel")
        self.assertEqual(events[0][3]["details"]["provider"],"ue4ss")

    def test_bad_bridge_line_is_reported_not_fatal(self):
        events=[]
        def cb(source,signal,value,**kwargs):events.append((signal,value))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"telemetry.jsonl";p.write_text("",encoding="utf-8")
            b=JsonlBridgeProvider(p,cb,from_end=True);b.start()
            with p.open("a",encoding="utf-8") as f:f.write("{bad json}\n");f.flush()
            deadline=time.time()+2
            while not events and time.time()<deadline:time.sleep(.02)
            b.close()
        self.assertTrue(any(s=="bridge_parse_error" for s,_ in events))


if __name__=="__main__":unittest.main()
