"""Cheat Engine scan assistant: state timeline -> bounded differential scan plan."""
import tempfile, unittest
from pathlib import Path
from scan_assistant import ScanAssistant, ScanPlanner, format_command


class Planner(unittest.TestCase):
    def feed(self,p,state,t0,t1,step=.1):
        out=[];t=t0
        while t<=t1+1e-9:
            out+=p.observe(state,t);t=round(t+step,6)
        return out

    def test_first_scan_waits_for_a_settled_phase(self):
        p=ScanPlanner()
        self.assertEqual(self.feed(p,"WAIT_BITE",0,1.4),[])
        cmds=self.feed(p,"WAIT_BITE",1.5,1.6)
        self.assertEqual([(c["cmd"],c["arg"],c["phase"]) for c in cmds],[("first","-","waiting")])
        self.assertEqual(cmds[0]["var_type"],"4 Bytes")

    def test_full_round_trip_changed_unchanged_then_dump(self):
        p=ScanPlanner(min_results=64)
        first=self.feed(p,"WAIT_BITE",0,1.6)[0]
        self.assertEqual(self.feed(p,"WAIT_BITE",1.7,3.0),[])          # waiting for the ack
        self.assertEqual(p.ack(first["seq"],now=3.0),[])
        cmds=self.feed(p,"WAIT_BITE",3.1,12.0)
        self.assertEqual([(c["cmd"],c["arg"]) for c in cmds],[("next","unchanged")])   # ack gates the second
        self.assertEqual(p.ack(cmds[0]["seq"],count=5_000_000,now=12.0),[])
        cmds=self.feed(p,"WAIT_BITE",12.1,30.0)
        self.assertEqual([(c["cmd"],c["arg"]) for c in cmds],[("next","unchanged")])   # at most two per visit
        p.ack(cmds[0]["seq"],count=900_000,now=30.0)
        self.assertEqual(self.feed(p,"WAIT_BITE",30.1,40.0),[])
        self.assertEqual(self.feed(p,"BITE_PENDING",40.1,41.0),[])                    # not a scan phase
        changed=self.feed(p,"FIGHT",41.1,43.0)
        self.assertEqual([(c["cmd"],c["arg"],c["phase"]) for c in changed],[("next","changed","fight")])
        follow=p.ack(changed[0]["seq"],count=40,now=43.0)
        self.assertEqual([(c["cmd"],c["arg"]) for c in follow],[("dump","64")])
        self.assertEqual(p.ack(follow[0]["seq"],count=40,now=43.5),[])
        self.assertTrue(p.done);self.assertIn("40",p.done_reason)
        self.assertEqual(self.feed(p,"WAIT_CAST",44,50),[])
        self.assertEqual(p.scans,4)

    def test_reel_and_short_phases_never_scan(self):
        p=ScanPlanner()
        self.assertEqual(self.feed(p,"REEL",0,5),[]);self.assertEqual(self.feed(p,"CAST",5,8),[])

    def test_lost_ack_times_out_and_planning_continues(self):
        p=ScanPlanner(ack_timeout_s=25.0)
        first=self.feed(p,"WAIT_BITE",0,1.6)[0]
        self.assertEqual(self.feed(p,"FIGHT",10,20),[])
        cmds=self.feed(p,"FIGHT",26.7,27.0)
        self.assertEqual([(c["cmd"],c["arg"]) for c in cmds],[("next","changed")])
        self.assertTrue(any(x.get("cmd")=="timeout" and x["seq"]==first["seq"] for x in p.log))

    def test_stale_or_unknown_ack_is_ignored(self):
        p=ScanPlanner();first=self.feed(p,"WAIT_BITE",0,1.6)[0]
        self.assertEqual(p.ack(99,count=1,now=2.0),[]);self.assertIsNotNone(p.pending)
        self.assertEqual(p.ack(first["seq"],count=5,now=2.0),[]);self.assertIsNone(p.pending)

    def test_bridge_error_restarts_the_plan_then_gives_up(self):
        p=ScanPlanner()
        for attempt in range(3):
            t0=attempt*100
            first=self.feed(p,"WAIT_BITE",t0,t0+1.6)[0]
            self.assertEqual(first["cmd"],"first")
            self.assertEqual(p.ack(first["seq"],error="no first scan yet",now=t0+2.0),[])
        self.assertTrue(p.done);self.assertIn("no first scan yet",p.done_reason);self.assertEqual(p.restarts,2)
        self.assertIn("Cheat Engine reported",p.status())

    def test_budget_exhausted_requests_dump(self):
        p=ScanPlanner(max_scans=1)
        first=self.feed(p,"WAIT_BITE",0,1.6)[0];p.ack(first["seq"],now=2.0)
        cmds=self.feed(p,"FIGHT",10,12)
        self.assertEqual([c["cmd"] for c in cmds],["dump"]);self.assertTrue(p.done)

    def test_reset_starts_over(self):
        p=ScanPlanner();first=self.feed(p,"WAIT_BITE",0,1.6)[0];p.ack(first["seq"],now=2.0)
        r=p.reset(3.0)
        self.assertEqual(r[0]["cmd"],"reset");self.assertFalse(p.started);self.assertEqual(p.scans,0)
        self.assertEqual([c["cmd"] for c in self.feed(p,"WAIT_BITE",3.1,5.0)],["first"])

    def test_invalid_var_type_rejected(self):
        with self.assertRaises(ValueError):ScanPlanner(var_type="String")

    def test_command_line_format_is_tab_separated(self):
        p=ScanPlanner();c=self.feed(p,"WAIT_BITE",0,1.6)[0]
        self.assertEqual(format_command(c),"1\tfirst\t-\t4 Bytes\tWAIT_BITE\twaiting")


class Assistant(unittest.TestCase):
    def test_commands_are_appended_and_replies_drive_follow_ups(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"telemetry"/"cheat_engine_commands.tsv";events=[];clock=[0.]
            a=ScanAssistant(path,lambda *x,**k:events.append((x[1],x[2])),ScanPlanner(min_results=10),clock=lambda:clock[0])
            for t in range(0,17):
                clock[0]=t/10;a.observe("WAIT_BITE")
            lines=path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines,["1\treset\t-\t4 Bytes\t-\t-","2\tfirst\t-\t4 Bytes\tWAIT_BITE\twaiting"])
            a.bridge_event("scan_result",None,{"seq":"2"})
            clock[0]=20.;a.observe("FIGHT");clock[0]=22.;a.observe("FIGHT")
            a.bridge_event("scan_result","7",{"seq":3})           # Cheat Engine numbers may arrive as strings
            lines=path.read_text(encoding="utf-8").splitlines()
            self.assertEqual([l.split("\t")[1:3] for l in lines],[["reset","-"],["first","-"],["next","changed"],["dump","10"]])
            self.assertEqual([e[0] for e in events],["scan_command"]*4)
            a.bridge_event("heartbeat",1,{"seq":4})                 # not a reply: ignored
            a.bridge_event("scan_dump",7,{"seq":4})
            self.assertIn("done",a.status());self.assertEqual(a.summary()["commands"],4)
            a.reset()
            self.assertEqual(path.read_text(encoding="utf-8").splitlines()[-1].split("\t")[1],"reset")
            # A second session appends after the first one; the bridge tails by offset.
            b=ScanAssistant(path,None,ScanPlanner(),clock=lambda:clock[0])
            self.assertEqual(path.read_text(encoding="utf-8").splitlines()[-1].split("\t")[1:2],["reset"]);self.assertEqual(b.written,1)


if __name__=="__main__":unittest.main()
