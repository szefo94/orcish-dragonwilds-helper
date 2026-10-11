"""Game signal sources: one interface for every way Orcish can learn game state besides vision.

A *signal source* is observational. It never writes game memory, never sends input and never
decides anything. Sources only produce `SignalSample`s on the Scout timeline; the `SignalHub`
keeps the latest sample per (domain, role, name) so the Fishing/Auto Picker controllers can be
*compared* against them (shadow mode) without consuming them. Promotion of a signal into live
control is a separate, manual engineering decision gated by docs/SCOUT_CANDIDATES.md.

Source kinds (see docs/GAME_SIGNALS.md):

    memory   read-only ReadProcessMemory candidates (MemoryCandidateSource)
    bridge   JSONL lines from an external producer: Cheat Engine, UE4SS, ... (hub.ingest_bridge)
    hook     in-process instrumentation (Frida, a UE4SS Lua mod, a custom DLL): push samples
             from the hook's own thread through a CallbackHookSource; the main thread polls.

The hub and the sources are pure Python: tests drive them with fake readers and fake clocks.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import queue, threading, time

CANDIDATE_ROLES={
    "fishing":["phase","hooked","reel_allowed","pull_direction","tension","progress","spot_state",
               "widget_stop","widget_pull_left","widget_pull_right","widget_reel","result"],
    "auto_picker":["focused_actor","actor_class_id","interaction_action","can_interact","distance","required_range",
                   "prompt_state","item_id","item_quantity","inventory_free","interaction_cooldown"],
    "general":["state","bool","enum","counter","distance","progress","pointer","unknown"]
}
DOMAINS=tuple(CANDIDATE_ROLES)


def infer_role(name,domain):
    """Role implied by a free-text name: 'fishing phase' -> 'phase', 'pull direction' -> 'pull_direction'.

    Longest role names are tried first so 'widget_pull_left' wins over 'pull_direction' substrings."""
    roles=CANDIDATE_ROLES.get(domain,CANDIDATE_ROLES["general"])
    key=str(name or "").strip().lower().replace(" ","_").replace("-","_")
    return next((x for x in sorted(roles,key=len,reverse=True) if x in key),"unknown")


@dataclass
class SignalSample:
    source:str          # memory | cheat_engine | ue4ss | frida | <producer name>
    domain:str          # fishing | auto_picker | general
    role:str            # a CANDIDATE_ROLES entry or 'unknown'
    name:str            # candidate / record / hook label
    value:object        # None when the read failed
    mono:float
    ok:bool=True
    error:str|None=None
    details:dict=field(default_factory=dict)

    def row(self):
        return asdict(self)


class SignalSource:
    """Base contract. Subclasses override start/poll/close; poll runs on the Scout sampling thread."""
    kind="abstract"
    invasive=False      # True for anything that runs code inside the game process (hooks)

    def __init__(self,name=None):
        self.name=name or self.kind;self.samples=0;self.errors=[]

    def start(self):return self
    def poll(self,now):return []
    def close(self):return None
    def status(self):
        return {"kind":self.kind,"name":self.name,"invasive":self.invasive,"samples":self.samples,"errors":list(self.errors)[-3:]}


class MemoryCandidateSource(SignalSource):
    """Reads semantic candidates through a read-only memory backend.

    `open_reader()` returns an object with `read(candidate) -> {"ok","value"|"error",...}`; it is
    opened lazily and retried with a backoff instead of logging the same failure ten times per second.
    Event emission (memory/candidate, memory/candidate_transition, memory/backend_error) keeps the
    exact format older sessions used, so scout_analysis.py stays compatible."""
    kind="memory"

    def __init__(self,candidates,open_reader,event_cb=None,retry_s=5.0,clock=time.monotonic):
        super().__init__("memory")
        self.candidates=list(candidates);self.open_reader=open_reader;self.event_cb=event_cb
        self.retry_s=float(retry_s);self.clock=clock;self.reader=None;self.next_open=0.;self.last_error=None
        self.last_values={}

    def _ensure_reader(self,now):
        if self.reader is not None:return True
        if now<self.next_open:return False
        try:
            self.reader=self.open_reader();self.last_error=None;return True
        except Exception as e:
            err=type(e).__name__+": "+str(e);self.next_open=now+self.retry_s
            if err!=self.last_error:
                self.last_error=err;self.errors.append(err)
                if self.event_cb:self.event_cb("memory","backend_error",err,mono=now,stream="memory")
            return False

    def poll(self,now):
        if not self.candidates or not self._ensure_reader(now):return []
        out=[]
        for cand in self.candidates:
            try:r=self.reader.read(cand)
            except Exception as e:r={"ok":False,"error":type(e).__name__+": "+str(e)}
            row={"name":cand["name"],"domain":cand["domain"],"role":cand["role"],"spec":cand["spec"],**r}
            if self.event_cb:self.event_cb("memory","candidate",row,mono=now,stream="memory")
            key=(cand["domain"],cand["name"])
            current=r.get("value") if r.get("ok") else None
            seen=key in self.last_values;previous=self.last_values.get(key)
            if seen and previous!=current and self.event_cb:
                self.event_cb("memory","candidate_transition",
                              {"name":cand["name"],"domain":cand["domain"],"role":cand["role"],"spec":cand["spec"],
                               "from":previous,"to":current,"ok":bool(r.get("ok"))},mono=now,stream="memory")
            self.last_values[key]=current
            self.samples+=1
            out.append(SignalSample("memory",cand["domain"],cand["role"],cand["name"],current,now,bool(r.get("ok")),
                                    None if r.get("ok") else str(r.get("error")),{"spec":cand["spec"],"row":row}))
        return out

    def close(self):
        r=self.reader;self.reader=None
        if r is not None and hasattr(r,"close"):
            try:r.close()
            except Exception:pass


class CallbackHookSource(SignalSource):
    """Thread-safe inbox for in-process hooks (Frida, UE4SS mods, custom DLLs).

    The hook's callback thread calls `push(...)`; the Scout thread drains it in `poll()`. This keeps
    the project invariant that workers only capture and the main thread owns every decision. Any
    adapter built on it must stay opt-in and observational (see docs/GAME_SIGNALS.md)."""
    kind="hook"
    invasive=True

    def __init__(self,name,domain="general",max_pending=2000):
        super().__init__(name);self.domain=domain;self.inbox=queue.Queue(maxsize=max_pending);self.dropped=0

    def push(self,label,value,role=None,mono=None,ok=True,details=None):
        s=SignalSample(self.name,self.domain,role or infer_role(label,self.domain),str(label),value,
                       time.monotonic() if mono is None else float(mono),ok,None,dict(details or {}))
        try:self.inbox.put_nowait(s)
        except queue.Full:self.dropped+=1

    def poll(self,now):
        out=[]
        while True:
            try:out.append(self.inbox.get_nowait())
            except queue.Empty:break
        self.samples+=len(out)
        return out

    def status(self):
        s=super().status();s["dropped"]=self.dropped;return s


class SignalHub:
    """Registry of sources plus the latest value per signal for shadow comparison."""
    BRIDGE_SIGNALS=("property_change","state_change","function_call","event")

    def __init__(self,domain=None,max_signals=64):
        self.domain=domain or "general";self.sources=[];self.latest={};self.lock=threading.Lock();self.max_signals=max_signals

    def add(self,source):
        self.sources.append(source);return source

    def start(self):
        for s in self.sources:
            try:s.start()
            except Exception as e:s.errors.append(type(e).__name__+": "+str(e))
        return self

    def observe(self,sample):
        key=(sample.domain,sample.role,sample.name)
        with self.lock:
            if key not in self.latest and len(self.latest)>=self.max_signals:return
            self.latest[key]=sample

    def poll(self,now):
        rows=[]
        for s in self.sources:
            try:samples=s.poll(now)
            except Exception as e:
                s.errors.append(type(e).__name__+": "+str(e));continue
            for sample in samples:
                self.observe(sample)
                rows.append(sample.details.get("row") or sample.row())
        return rows

    def ingest_bridge(self,signal,value,details=None,mono=None,provider=None):
        """Map an external-bridge event (Cheat Engine record change, UE4SS call, ...) to a sample."""
        if signal not in self.BRIDGE_SIGNALS:return None
        d=dict(details or {});name=str(d.get("property") or d.get("function") or d.get("label") or signal)
        source=str(provider or d.get("provider") or "bridge")
        s=SignalSample(source,self.domain,infer_role(name,self.domain),name,value,
                       time.monotonic() if mono is None else float(mono),value is not None,None,{"signal":signal})
        self.observe(s);return s

    def snapshot(self,now=None,max_age=5.0,domains=None):
        """Compact JSON-friendly view of fresh, successful signals: {name: {role,value,source,age_ms}}."""
        now=time.monotonic() if now is None else now
        allowed=set(domains) if domains else {self.domain,"general"}
        out={}
        with self.lock:items=list(self.latest.items())
        for (domain,role,name),s in items:
            if domain not in allowed or not s.ok:continue
            age=now-s.mono
            if max_age is not None and age>max_age:continue
            out[name]={"role":role,"value":s.value,"source":s.source,"age_ms":round(age*1000,1)}
        return out

    def status(self):
        return {"domain":self.domain,"signals":len(self.latest),"sources":[s.status() for s in self.sources]}

    def close(self):
        for s in reversed(self.sources):
            try:s.close()
            except Exception:pass
        self.sources=[]
