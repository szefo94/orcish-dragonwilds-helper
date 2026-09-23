"""Optional game-internal telemetry providers for Scout.

Providers are observational at the Scout data-model level: they do not intentionally
change gameplay state, function arguments or return values. Frida's Interceptor is an
invasive instrumentation mechanism inside the target process, so it is opt-in and is
not equivalent to the project's ordinary read-only ReadProcessMemory watches. The
JSONL bridge consumes events produced by external tools such as UE4SS Lua mods.
"""
from __future__ import annotations
from pathlib import Path
import json, threading, time


def parse_function_hook(spec):
    """Parse label=MODULE+0xOFFSET or MODULE+0xOFFSET into a normalized hook."""
    s=(spec or "").strip()
    if not s:raise ValueError("Hook cannot be empty")
    label,expr=(s.split("=",1)+[None])[:2] if "=" in s else (None,s)
    if "+" not in expr:raise ValueError("Use label=MODULE+0xOFFSET")
    module,off=[x.strip() for x in expr.rsplit("+",1)]
    if not module:raise ValueError("Module name is empty")
    offset=int(off,0)
    if offset<0:raise ValueError("Offset must be non-negative")
    return {"spec":s,"label":(label or f"{module}+0x{offset:X}").strip(),"module":module,"offset":offset}


class JsonlBridgeProvider:
    """Tail newline-delimited JSON emitted by an external telemetry producer."""

    def __init__(self,path,event_cb,provider="external_bridge",from_end=True):
        self.path=Path(path);self.event_cb=event_cb;self.provider=provider
        self.from_end=bool(from_end);self.closed=threading.Event();self.ready=threading.Event();self.thread=None
        self.error=None;self.events=0

    def start(self):
        if self.thread:return
        existed=self.path.exists()
        self.thread=threading.Thread(target=self._run,daemon=True,name="scout-jsonl-bridge");self.thread.start()
        if existed:self.ready.wait(.5)

    def close(self,wait=True):
        self.closed.set()
        if wait and self.thread and self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=1.5)

    def _emit(self,obj):
        now=time.monotonic()
        provider=str(obj.get("provider") or self.provider)
        signal=str(obj.get("signal") or "event")
        value=obj.get("value")
        details=dict(obj.get("details") or {})
        for key in ("function","object","property","args","producer_time","producer_seq"):
            if key in obj and key not in details:details[key]=obj[key]
        details["provider"]=provider;details["bridge_path"]=str(self.path)
        self.event_cb("game_internal",signal,value,mono=now,details=details,stream="process")
        self.events+=1

    def _run(self):
        try:
            # Wait for the producer to create its file.
            while not self.closed.is_set() and not self.path.exists():self.closed.wait(.20)
            if self.closed.is_set():return
            with self.path.open("r",encoding="utf-8",errors="replace") as f:
                if self.from_end:f.seek(0,2)
                self.ready.set()
                while not self.closed.is_set():
                    line=f.readline()
                    if not line:
                        self.closed.wait(.05);continue
                    try:self._emit(json.loads(line))
                    except Exception as e:
                        self.event_cb("game_internal","bridge_parse_error",str(e),mono=time.monotonic(),
                                      details={"provider":self.provider,"line":line[:500]},stream="process")
        except Exception as e:
            self.ready.set()
            self.error=type(e).__name__+": "+str(e)
            self.event_cb("game_internal","bridge_error",self.error,mono=time.monotonic(),
                          details={"provider":self.provider,"bridge_path":str(self.path)},stream="process")


class FridaFunctionProvider:
    """Optional native function entry telemetry using Frida.

    Hook specifications are module-relative and are resolved inside the target process.
    This provider observes onEnter only and does not alter arguments or return values.
    Attaching/intercepting is still invasive instrumentation and should remain opt-in.
    """

    def __init__(self,pid,hooks,event_cb):
        self.pid=int(pid);self.hooks=[parse_function_hook(x) if isinstance(x,str) else x for x in hooks]
        self.event_cb=event_cb;self.session=None;self.script=None;self.error=None;self.events=0

    @staticmethod
    def available():
        try:
            import frida  # noqa:F401
            return True
        except Exception:return False

    def start(self):
        if not self.hooks:return
        try:
            import frida
        except Exception as e:
            raise RuntimeError("Frida Python package is not installed. Install optional dependency: pip install frida") from e
        self.session=frida.attach(self.pid)
        js_hooks=json.dumps(self.hooks)
        source=f"""
const hooks = {js_hooks};
for (const h of hooks) {{
  try {{
    const mod = Process.findModuleByName(h.module);
    if (mod === null) {{ send({{kind:'hook_error', label:h.label, error:'module_not_found', module:h.module}}); continue; }}
    const address = mod.base.add(h.offset);
    Interceptor.attach(address, {{
      onEnter(args) {{
        const a=[]; for (let i=0;i<4;i++) {{ try {{ a.push(args[i].toString()); }} catch(e) {{ a.push(null); }} }}
        send({{kind:'function_call', label:h.label, module:h.module, offset:h.offset,
              address:address.toString(), thread_id:this.threadId, args:a}});
      }}
    }});
    send({{kind:'hook_ready', label:h.label, module:h.module, offset:h.offset, address:address.toString()}});
  }} catch(e) {{ send({{kind:'hook_error', label:h.label, module:h.module, offset:h.offset, error:String(e)}}); }}
}}
"""
        self.script=self.session.create_script(source)
        self.script.on("message",self._on_message);self.script.load()
        self.event_cb("game_internal","provider_started",{"provider":"frida","hooks":len(self.hooks)},
                      mono=time.monotonic(),stream="process")

    def _on_message(self,message,data):
        now=time.monotonic()
        if message.get("type")!="send":
            self.event_cb("game_internal","frida_error",message,mono=now,details={"provider":"frida"},stream="process");return
        p=message.get("payload") or {};kind=p.get("kind","event")
        details={k:v for k,v in p.items() if k not in ("kind","label")}
        details["provider"]="frida"
        self.event_cb("game_internal",kind,p.get("label"),mono=now,details=details,stream="process")
        if kind=="function_call":self.events+=1

    def close(self,wait=True):
        try:
            if self.script:self.script.unload()
        except Exception:pass
        self.script=None
        try:
            if self.session:self.session.detach()
        except Exception:pass
        self.session=None


class InternalTelemetryHub:
    def __init__(self,pid,event_cb,config=None):
        self.pid=int(pid);self.event_cb=event_cb;self.config=dict(config or {});self.providers=[];self.errors=[]

    def start(self):
        if self.config.get("bridge_enabled") and self.config.get("bridge_path"):
            p=JsonlBridgeProvider(self.config["bridge_path"],self.event_cb,provider="ue4ss_bridge",from_end=True)
            p.start();self.providers.append(p)
            self.event_cb("game_internal","provider_started",
                          {"provider":"ue4ss_bridge","path":str(self.config["bridge_path"])},
                          mono=time.monotonic(),stream="process")
        if self.config.get("frida_enabled") and self.config.get("frida_hooks"):
            try:
                p=FridaFunctionProvider(self.pid,self.config["frida_hooks"],self.event_cb);p.start();self.providers.append(p)
            except Exception as e:
                self.errors.append(str(e))
                self.event_cb("game_internal","provider_error",str(e),mono=time.monotonic(),
                              details={"provider":"frida"},stream="process")
        return self

    def close(self):
        for p in reversed(self.providers):
            try:p.close()
            except Exception:pass
        self.providers=[]

    def status(self):
        return {"providers":[type(p).__name__ for p in self.providers],
                "events":sum(int(getattr(p,"events",0)) for p in self.providers),
                "errors":list(self.errors)}
