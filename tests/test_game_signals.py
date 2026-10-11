"""Signal sources and hub: pure logic with fake readers and fake clocks."""
import unittest
from game_signals import (CANDIDATE_ROLES, CallbackHookSource, MemoryCandidateSource, SignalHub, SignalSample, infer_role)


class FakeReader:
    def __init__(self,values):self.values=values;self.closed=False
    def read(self,cand):
        v=self.values.get(cand["name"])
        if v is None:return {"ok":False,"error":"null_pointer"}
        return {"ok":True,"address":0x1000,"value":v}
    def close(self):self.closed=True


def cand(name,domain="fishing",role="phase",spec="0x1000:u32"):
    return {"name":name,"domain":domain,"role":role,"spec":spec}


class InferRole(unittest.TestCase):
    def test_role_from_free_text_names(self):
        self.assertEqual(infer_role("fishing phase","fishing"),"phase")
        self.assertEqual(infer_role("Pull Direction","fishing"),"pull_direction")
        self.assertEqual(infer_role("widget-pull-left","fishing"),"widget_pull_left")
        self.assertEqual(infer_role("can interact","auto_picker"),"can_interact")
        self.assertEqual(infer_role("mystery","fishing"),"unknown")
        self.assertEqual(infer_role("counter 1","nope"),"counter")   # unknown domain uses the general roles
        self.assertEqual(set(CANDIDATE_ROLES),{"fishing","auto_picker","general"})


class MemorySource(unittest.TestCase):
    def test_reads_emit_candidate_rows_and_transitions(self):
        events=[];reader=FakeReader({"phase":2})
        src=MemoryCandidateSource([cand("phase")],lambda:reader,lambda *a,**k:events.append((a,k)),clock=lambda:0.)
        s1=src.poll(1.0);reader.values["phase"]=3;s2=src.poll(1.1)
        self.assertEqual([x.value for x in s1+s2],[2,3])
        self.assertTrue(all(isinstance(x,SignalSample) and x.ok for x in s1+s2))
        signals=[a[1] for a,_ in events]
        self.assertEqual(signals,["candidate","candidate","candidate_transition"])
        transition=events[-1][0][2]
        self.assertEqual((transition["from"],transition["to"]),(2,3))
        row=events[0][0][2]   # memory.jsonl row format is unchanged for the analyzer
        self.assertEqual({k:row[k] for k in ("name","domain","role","spec","ok","value")},
                         {"name":"phase","domain":"fishing","role":"phase","spec":"0x1000:u32","ok":True,"value":2})

    def test_failed_read_is_a_sample_with_error(self):
        src=MemoryCandidateSource([cand("phase")],lambda:FakeReader({}),None)
        s=src.poll(1.0)[0]
        self.assertFalse(s.ok);self.assertEqual(s.error,"null_pointer");self.assertIsNone(s.value)

    def test_backend_failure_is_logged_once_and_retried_after_backoff(self):
        events=[];attempts=[]
        def open_reader():
            attempts.append(1)
            if len(attempts)<3:raise OSError(5,"OpenProcess failed")
            return FakeReader({"phase":1})
        src=MemoryCandidateSource([cand("phase")],open_reader,lambda *a,**k:events.append(a),retry_s=5.0)
        for t in (0.0,0.1,0.2,1.0,4.9):self.assertEqual(src.poll(t),[])
        self.assertEqual(len(attempts),1)                       # no retry storm inside the backoff
        self.assertEqual([a[1] for a in events],["backend_error"])
        self.assertEqual(src.poll(5.0),[]);self.assertEqual(len(attempts),2)
        self.assertEqual(len(events),1)                         # same error text is not repeated
        self.assertEqual(len(src.poll(10.0)),1);self.assertEqual(len(attempts),3)

    def test_close_releases_reader(self):
        reader=FakeReader({"phase":1});src=MemoryCandidateSource([cand("phase")],lambda:reader,None)
        src.poll(0.);src.close()
        self.assertTrue(reader.closed);self.assertIsNone(src.reader)


class Hub(unittest.TestCase):
    def test_snapshot_keeps_fresh_successful_signals_of_the_active_domain(self):
        hub=SignalHub("fishing")
        reader=FakeReader({"phase":2,"state":7})
        hub.add(MemoryCandidateSource([cand("phase"),cand("state","general","state"),cand("actor","auto_picker","focused_actor"),cand("broken")],lambda:reader,None)).start()
        rows=hub.poll(10.0)
        self.assertEqual(len(rows),4);self.assertEqual(rows[0]["name"],"phase")
        snap=hub.snapshot(now=10.2)
        self.assertEqual(set(snap),{"phase","state"})            # auto_picker and failed reads excluded
        self.assertEqual(snap["phase"]["value"],2);self.assertEqual(snap["phase"]["role"],"phase")
        self.assertAlmostEqual(snap["phase"]["age_ms"],200,delta=1)
        self.assertEqual(hub.snapshot(now=20.0),{})               # stale after max_age
        self.assertEqual(hub.status()["signals"],4)

    def test_bridge_events_become_signals(self):
        hub=SignalHub("fishing")
        s=hub.ingest_bridge("property_change",3,{"provider":"cheat_engine","property":"fishing phase"},mono=5.0)
        self.assertEqual((s.source,s.role,s.name,s.value),("cheat_engine","phase","fishing phase",3))
        self.assertIsNone(hub.ingest_bridge("heartbeat",1,{"provider":"cheat_engine"},mono=5.0))
        self.assertEqual(hub.snapshot(now=5.1)["fishing phase"]["source"],"cheat_engine")

    def test_hook_source_drains_pushed_samples_on_poll(self):
        hub=SignalHub("fishing");hook=hub.add(CallbackHookSource("frida","fishing",max_pending=2))
        hook.push("reel allowed",1,mono=1.0);hook.push("reel allowed",0,mono=1.5);hook.push("overflow",1,mono=1.6)
        self.assertEqual(hook.dropped,1)
        rows=hub.poll(2.0)
        self.assertEqual([r["value"] for r in rows],[1,0]);self.assertEqual(rows[0]["role"],"reel_allowed")
        self.assertTrue(hook.invasive);self.assertEqual(hub.snapshot(now=2.0)["reel allowed"]["value"],0)

    def test_source_exception_is_recorded_not_raised(self):
        class Broken(CallbackHookSource):
            def poll(self,now):raise RuntimeError("boom")
        hub=SignalHub();b=hub.add(Broken("broken"))
        self.assertEqual(hub.poll(0.),[]);self.assertIn("RuntimeError: boom",b.errors)
        hub.close();self.assertEqual(hub.sources,[])


if __name__=="__main__":unittest.main()
