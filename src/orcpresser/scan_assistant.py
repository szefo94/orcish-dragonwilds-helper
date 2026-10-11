"""Cheat Engine scan assistant: turn the Fishing controller's state timeline into a differential
memory-scan plan, so finding the fishing phase address no longer needs hand-driven scans.

    Fishing controller states  ->  ScanPlanner  ->  command lines  ->  Cheat Engine bridge (Lua)
    WAIT_BITE / FIGHT / ...         first / next      data\\telemetry\\      runs memscan, writes
                                    changed/unchanged cheat_engine_        scan_result / scan_dump
                                                      commands.tsv          back into the stream

The planner is pure logic (tested); the writer only appends lines. Cheat Engine executes the scans
with its own memscan API inside tools/cheat-engine/orcish_scout_ce.lua. Nothing here touches the
game process from Orcish. The plan follows docs/RESEARCH_DATA_GUIDE.md Part C2:

    first scan: unknown initial value, once a phase has settled
    phase changes  -> "changed"   (after the new phase settled, so a scan never straddles a flip)
    stable phase   -> "unchanged" (at most twice per visit, spaced out)
    survivors <= min_results -> "dump": addresses go back on the Scout timeline and into the table

Command line format (tab separated, trivial to parse in Lua):

    <seq>\t<cmd>\t<arg>\t<var_type>\t<state>\t<phase>

    cmd: first | next | dump | reset        arg: changed | unchanged | <dump limit> | -
"""
from __future__ import annotations
from pathlib import Path
import json, threading, time

PHASES={"READY":"idle","WAIT_CAST":"idle","WAIT_BITE":"waiting","FIGHT":"fight","REEL":"reel"}
SCAN_PHASES=("idle","waiting","fight")      # long enough for a scan; REEL and BITE_PENDING are not
VAR_TYPES=("4 Bytes","Byte","2 Bytes","Float")


class ScanPlanner:
    def __init__(self,var_type="4 Bytes",settle_s=1.5,unchanged_every_s=4.0,unchanged_per_visit=2,
                 min_results=64,max_scans=60,ack_timeout_s=25.0):
        if var_type not in VAR_TYPES:raise ValueError("var_type must be one of: "+", ".join(VAR_TYPES))
        self.var_type=var_type;self.settle_s=float(settle_s);self.unchanged_every_s=float(unchanged_every_s)
        self.unchanged_per_visit=int(unchanged_per_visit);self.min_results=int(min_results);self.max_scans=int(max_scans)
        self.ack_timeout_s=float(ack_timeout_s)
        self.seq=0;self.scans=0;self.state=None;self.phase=None;self.phase_since=None
        self.pending=None        # command awaiting an ack: dict with seq, cmd, sent, phase
        self.started=False;self.done=False;self.done_reason="";self.restarts=0;self.max_restarts=2
        self.last_scan_phase=None;self.last_scan_at=None;self.unchanged_in_visit=0;self.last_count=None
        self.log=[]

    def _emit(self,cmd,arg,now):
        self.seq+=1
        c={"seq":self.seq,"cmd":cmd,"arg":arg,"var_type":self.var_type,"state":self.state or "-",
           "phase":self.phase or "-","mono":now}
        self.log.append(c)
        if cmd in ("first","next"):
            self.pending=dict(c,sent=now);self.scans+=1;self.last_scan_phase=self.phase;self.last_scan_at=now
        elif cmd=="dump":self.pending=dict(c,sent=now)
        return c

    def reset(self,now):
        """Forget scan progress (the bridge starts a new memscan on the next 'first')."""
        self.seq+=1;c={"seq":self.seq,"cmd":"reset","arg":"-","var_type":self.var_type,"state":self.state or "-","phase":self.phase or "-","mono":now}
        self.log.append(c);self.scans=0;self.pending=None;self.started=False;self.done=False;self.done_reason=""
        self.last_scan_phase=None;self.last_scan_at=None;self.unchanged_in_visit=0;self.last_count=None
        return [c]

    def ack(self,seq,count=None,error=None,now=None):
        """Bridge reply for a command; returns follow-up commands to send. Unknown/stale seqs are ignored."""
        now=time.monotonic() if now is None else now
        if not self.pending or int(seq)!=self.pending["seq"]:return []
        p=self.pending;self.pending=None
        if error:
            # Typical cause: the table was opened after Orcish sent 'first', so Cheat Engine has no scan.
            # Start the plan over from the next settled phase; give up only after repeated failures.
            self.log.append({"seq":p["seq"],"cmd":"error","error":str(error),"mono":now})
            if self.restarts<self.max_restarts:
                self.restarts+=1;self.started=False;self.scans=0;self.last_scan_phase=None;self.last_scan_at=None
                self.unchanged_in_visit=0;self.last_count=None;return []
            self.done=True;self.done_reason=f"Cheat Engine reported: {error}";return []
        if p["cmd"]=="dump":
            self.done=True;self.done_reason=f"dumped {count if count is not None else '?'} survivor(s)";return []
        if count is not None:
            self.last_count=int(count)
            if p["cmd"]=="next" and self.last_count<=self.min_results:
                return [self._emit("dump",str(max(1,self.min_results)),now)]
        return []

    def observe(self,state,now):
        """Feed the controller state each tick; returns the commands to send (usually none)."""
        if self.done:return []
        phase=PHASES.get(state)
        if phase!=self.phase:
            self.phase=phase;self.phase_since=now;self.unchanged_in_visit=0
        self.state=state
        if self.pending:
            if now-self.pending["sent"]>self.ack_timeout_s:
                self.log.append({"seq":self.pending["seq"],"cmd":"timeout","mono":now});self.pending=None
            else:return []
        if self.scans>=self.max_scans:
            self.done=True;self.done_reason=f"scan budget of {self.max_scans} used; dump requested"
            return [self._emit("dump",str(max(1,self.min_results)),now)]
        if phase not in SCAN_PHASES or self.phase_since is None or now-self.phase_since<self.settle_s:return []
        if not self.started:
            self.started=True;return [self._emit("first","-",now)]
        if phase!=self.last_scan_phase:return [self._emit("next","changed",now)]
        if (self.unchanged_in_visit<self.unchanged_per_visit and self.last_scan_at is not None
                and now-self.last_scan_at>=self.unchanged_every_s):
            self.unchanged_in_visit+=1;return [self._emit("next","unchanged",now)]
        return []

    def status(self):
        if self.done:return "done — "+self.done_reason
        if not self.started:
            return "waiting for a settled fishing phase to take the first scan"+(f" (restart {self.restarts})" if self.restarts else "")
        waiting=f" · waiting for Cheat Engine (#{self.pending['seq']} {self.pending['cmd']} {self.pending['arg']})" if self.pending else ""
        left="?" if self.last_count is None else str(self.last_count)
        return f"scans={self.scans}/{self.max_scans} · survivors={left} · phase={self.phase or '-'}{waiting}"


def format_command(c):
    return "\t".join(str(c.get(k,"-")) for k in ("seq","cmd","arg","var_type","state","phase"))


class ScanAssistant:
    """Glue: planner + command file + Scout annotations. Owned by the UI thread."""

    def __init__(self,path,event_cb=None,planner=None,clock=time.monotonic):
        self.path=Path(path);self.event_cb=event_cb;self.planner=planner or ScanPlanner();self.clock=clock
        # observe() runs on the UI thread, bridge_event() on the JSONL tail thread: one lock guards the planner and the file.
        self.lock=threading.RLock()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.written=0;self.error=None
        # The file is append-only (the bridge tails it by offset). A 'reset' line opens every session so a
        # bridge that is already running drops the previous session's scan instead of continuing it.
        self.reset()

    def _write(self,commands):
        if not commands:return
        try:
            with self.path.open("a",encoding="utf-8") as f:
                for c in commands:f.write(format_command(c)+"\n")
            self.written+=len(commands);self.error=None
        except OSError as e:self.error=str(e)
        if self.event_cb:
            for c in commands:self.event_cb("annotation","scan_command",c,mono=c.get("mono"),stream="annotations")

    def observe(self,state,now=None):
        now=self.clock() if now is None else now
        with self.lock:self._write(self.planner.observe(state,now))

    def reset(self):
        with self.lock:self._write(self.planner.reset(self.clock()))

    def bridge_event(self,signal,value,details=None):
        """Route Cheat Engine replies (scan_result / scan_error / scan_dump) to the planner."""
        d=details or {};seq=d.get("seq")
        if seq is None or signal not in ("scan_result","scan_error","scan_dump"):return
        try:seq=int(seq)
        except (TypeError,ValueError):return
        count=value if signal!="scan_error" else None
        if isinstance(count,str):
            try:count=int(float(count))
            except ValueError:count=None
        with self.lock:self._write(self.planner.ack(seq,count=count,error=value if signal=="scan_error" else None,now=self.clock()))

    def status(self):
        with self.lock:s=self.planner.status()
        return s+(f" · command file error: {self.error}" if self.error else "")

    def summary(self):
        return {"commands":self.written,"scans":self.planner.scans,"done":self.planner.done,"reason":self.planner.done_reason,
                "last_count":self.planner.last_count,"path":str(self.path)}
