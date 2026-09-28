import json, tempfile, time, unittest
from pathlib import Path

from internal_telemetry import parse_function_hook, parse_bridge_paths, JsonlBridgeProvider, InternalTelemetryHub


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

    def test_bridge_paths_accept_string_list_and_dedupe(self):
        self.assertEqual(parse_bridge_paths(' a.jsonl ; "b.jsonl";a.jsonl;'),["a.jsonl","b.jsonl"])
        self.assertEqual(parse_bridge_paths(["x","","x","y"]),["x","y"])
        self.assertEqual(parse_bridge_paths(None),[])

    def test_bridge_created_after_start_is_read_from_beginning(self):
        events=[]
        def cb(source,signal,value,**kwargs):events.append(signal)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"late.jsonl"
            b=JsonlBridgeProvider(p,cb,from_end=True);b.start()
            p.write_text(json.dumps({"provider":"ue4ss","signal":"bridge_start"})+"\n",encoding="utf-8")
            deadline=time.time()+2
            while not events and time.time()<deadline:time.sleep(.02)
            b.close()
        self.assertEqual(events,["bridge_start"])

    def test_hub_reads_every_configured_bridge(self):
        events=[]
        def cb(source,signal,value,**kwargs):
            if signal=="property_change":events.append(kwargs["details"]["provider"])
        with tempfile.TemporaryDirectory() as td:
            ue,ce=Path(td)/"ue4ss.jsonl",Path(td)/"cheat_engine.jsonl"
            for f in (ue,ce):f.write_text("",encoding="utf-8")
            hub=InternalTelemetryHub(0,cb,{"bridge_enabled":True,"bridge_paths":[str(ue),str(ce)]}).start()
            with ue.open("a",encoding="utf-8") as f:f.write(json.dumps({"provider":"ue4ss","signal":"property_change","value":1})+"\n")
            with ce.open("a",encoding="utf-8") as f:f.write(json.dumps({"signal":"property_change","value":2})+"\n")
            deadline=time.time()+2
            while len(events)<2 and time.time()<deadline:time.sleep(.02)
            status=hub.status();hub.close()
        self.assertEqual(sorted(events),["cheat_engine","ue4ss"])   # file stem is the fallback provider
        self.assertEqual(status["events"],2);self.assertEqual(len(status["providers"]),2)

    def test_bridge_keeps_all_producer_fields_in_details(self):
        got=[]
        b=JsonlBridgeProvider("unused.jsonl",lambda *a,**k:got.append(k["details"]),provider="fallback")
        b._emit({"signal":"property_change","value":3,"property":"C.P","label":"phase","details":{"from":"1"},"error":None})
        d=got[0]
        self.assertEqual((d["provider"],d["property"],d["label"],d["from"]),("fallback","C.P","phase","1"))
        self.assertIn("error",d);self.assertNotIn("value",d)

    def test_disabled_bridge_starts_nothing(self):
        hub=InternalTelemetryHub(0,lambda *a,**k:None,{"bridge_enabled":False,"bridge_paths":["x.jsonl"]}).start()
        self.assertEqual(hub.providers,[])


if __name__=="__main__":unittest.main()
