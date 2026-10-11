"""Scout Lab: supervised visual + read-only process/memory telemetry collection.

The Lab is deliberately observational. It records cursor/crosshair visual probes,
ordinary process metadata and explicitly configured read-only memory watches on
the same Scout timeline. It never writes game memory and never moves the mouse.
"""
from __future__ import annotations
from pathlib import Path
import ctypes, csv, json, math, os, queue, struct, sys, threading, time
import numpy as np
from internal_telemetry import InternalTelemetryHub, parse_function_hook, parse_bridge_paths, FridaFunctionProvider
from research_setup import default_bridge_paths
from pointer_chain import is_pointer_expr, parse_pointer_expr, resolve_ops
from ce_table import parse_cheat_table
from game_signals import CANDIDATE_ROLES, infer_role, MemoryCandidateSource, SignalHub
from scan_assistant import ScanAssistant, ScanPlanner, VAR_TYPES
import research_setup

WATCH_TYPES={"u8":("B",1),"u16":("H",2),"u32":("I",4),"i32":("i",4),"u64":("Q",8),"i64":("q",8),"ptr":("Q",8),"f32":("f",4),"f64":("d",8)}

def parse_candidate(value):
    """Normalize persisted candidate dict into {name,domain,role,spec,...watch fields}."""
    if not isinstance(value,dict):raise ValueError("Candidate must be an object")
    name=str(value.get("name") or "").strip()
    domain=str(value.get("domain") or "general").strip()
    role=str(value.get("role") or "unknown").strip()
    spec=str(value.get("spec") or "").strip()
    if not name:raise ValueError("Candidate name is required")
    if domain not in CANDIDATE_ROLES:raise ValueError("Candidate domain must be fishing, auto_picker or general")
    watch=parse_watch(spec)
    return {"name":name,"domain":domain,"role":role,"spec":spec,**watch}


def merge_ce_candidates(existing,records,domain):
    """Add Cheat Engine records as candidates of one domain; same domain+name is replaced.

    The role is taken from the description when it names a known role for the domain
    (e.g. 'pull_direction' or 'pull direction'), otherwise 'unknown'. Returns (candidates, added).
    """
    out=list(existing);added=0
    for r in records:
        value={"name":r["name"],"domain":domain,"role":infer_role(r["name"],domain),"spec":r["spec"]}
        try:parse_candidate(value)
        except ValueError:continue
        out=[x for x in out if not (x.get("domain")==domain and x.get("name")==r["name"])]
        out.append(value);added+=1
    return out,added

def parse_watch(spec):
    """Parse MODULE+0xOFFSET:TYPE, 0xABSOLUTE:TYPE or a [pointer]+0xOFFSET chain into a normalized watch."""
    s=(spec or "").strip()
    if ":" not in s:raise ValueError("Use MODULE+0xOFFSET:type, [[MODULE+0xOFFSET]+0x10]+0x8:type or 0xADDRESS:type")
    addr,typ=[x.strip() for x in s.rsplit(":",1)]
    typ=typ.lower()
    if typ not in WATCH_TYPES:raise ValueError("Type must be one of: "+", ".join(WATCH_TYPES))
    if is_pointer_expr(addr):
        return {"spec":s,"module":None,"offset":None,"address":None,"type":typ,"chain":parse_pointer_expr(addr)}
    if "+" in addr:
        module,off=[x.strip() for x in addr.rsplit("+",1)]
        if not module:raise ValueError("Module name is empty")
        offset=int(off,0)
        if offset<0:raise ValueError("Offset must be non-negative")
        return {"spec":s,"module":module.lower(),"offset":offset,"address":None,"type":typ}
    absolute=int(addr,0)
    if absolute<=0:raise ValueError("Address must be positive")
    return {"spec":s,"module":None,"offset":None,"address":absolute,"type":typ}

def format_trail(trail):
    """'0xAT->0xPOINTER' per pointer level ('?' where the read failed) for failure diagnostics."""
    return [f"0x{x['at']:X}->"+("?" if x["pointer"] is None else f"0x{x['pointer']:X}") for x in trail]

def visual_features(frame):
    """Small numeric descriptor for a cursor/crosshair patch; suitable for JSONL."""
    if frame is None or getattr(frame,"size",0)==0:return None
    import numpy as np
    a=frame.astype("float32")
    h,w=a.shape[:2];cy,cx=h//2,w//2
    center=a[cy,cx,:3] if a.ndim==3 else [a[cy,cx]]*3
    mean=a[:,:,:3].mean(axis=(0,1)) if a.ndim==3 else [float(a.mean())]*3
    std=float(a[:,:,:3].std()) if a.ndim==3 else float(a.std())
    return {"size":[int(w),int(h)],"center_bgr":[round(float(x),2) for x in center],
            "mean_bgr":[round(float(x),2) for x in mean],"std":round(std,2)}

class ReadOnlyMemory:
    PROCESS_VM_READ=0x0010
    PROCESS_QUERY_INFORMATION=0x0400
    TH32CS_SNAPMODULE=0x00000008
    TH32CS_SNAPMODULE32=0x00000010

    def __init__(self,pid):
        if sys.platform!="win32":raise OSError("ReadOnlyMemory requires Windows")
        from ctypes import wintypes as w
        self.w=w;self.k=ctypes.windll.kernel32;self.pid=int(pid)
        self.k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];self.k.OpenProcess.restype=w.HANDLE
        self.k.CloseHandle.argtypes=[w.HANDLE];self.k.CloseHandle.restype=w.BOOL
        self.k.ReadProcessMemory.argtypes=[w.HANDLE,w.LPCVOID,w.LPVOID,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)];self.k.ReadProcessMemory.restype=w.BOOL
        self.k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];self.k.CreateToolhelp32Snapshot.restype=w.HANDLE
        self.handle=self.k.OpenProcess(self.PROCESS_VM_READ|self.PROCESS_QUERY_INFORMATION,False,self.pid)
        if not self.handle:raise OSError(ctypes.get_last_error(),"OpenProcess failed")
        self.modules=self._modules()

    def close(self):
        if getattr(self,"handle",None):
            ctypes.windll.kernel32.CloseHandle(self.handle);self.handle=None

    def _modules(self):
        w=self.w
        class MODULEENTRY32W(ctypes.Structure):
            _fields_=[("dwSize",w.DWORD),("th32ModuleID",w.DWORD),("th32ProcessID",w.DWORD),
                      ("GlblcntUsage",w.DWORD),("ProccntUsage",w.DWORD),("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),
                      ("modBaseSize",w.DWORD),("hModule",w.HMODULE),("szModule",w.WCHAR*256),("szExePath",w.WCHAR*260)]
        snap=self.k.CreateToolhelp32Snapshot(self.TH32CS_SNAPMODULE|self.TH32CS_SNAPMODULE32,self.pid)
        invalid=ctypes.c_void_p(-1).value
        if snap==invalid:return {}
        out={}
        try:
            e=MODULEENTRY32W();e.dwSize=ctypes.sizeof(e)
            ok=self.k.Module32FirstW(snap,ctypes.byref(e))
            while ok:
                base=ctypes.cast(e.modBaseAddr,ctypes.c_void_p).value or 0
                out[e.szModule.lower()]={"base":base,"size":int(e.modBaseSize),"path":e.szExePath}
                ok=self.k.Module32NextW(snap,ctypes.byref(e))
        finally:self.k.CloseHandle(snap)
        return out

    def resolve(self,watch):
        if watch["module"] is None:return watch["address"]
        m=self.modules.get(watch["module"])
        if not m:return None
        return int(m["base"])+int(watch["offset"])

    def _module_base(self,name):
        m=self.modules.get(name)
        return int(m["base"]) if m else None

    def _read_raw(self,address,size):
        buf=(ctypes.c_ubyte*size)();got=ctypes.c_size_t()
        ok=self.k.ReadProcessMemory(self.handle,ctypes.c_void_p(address),ctypes.byref(buf),size,ctypes.byref(got))
        return bytes(buf) if ok and got.value==size else None

    def _read_pointer(self,address):
        raw=self._read_raw(address,8) if address and address>0 else None
        return struct.unpack("<Q",raw)[0] if raw else None

    def read(self,watch):
        chain=watch.get("chain")
        if chain:
            # Re-walked on every read: the objects behind a pointer chain move when the game rebuilds them.
            r=resolve_ops(chain,self._module_base,self._read_pointer)
            if not r["ok"]:return {"ok":False,"error":r["error"],"chain":format_trail(r["trail"])}
            address=r["address"]
        else:
            address=self.resolve(watch)
            if not address:return {"ok":False,"error":"module_not_found"}
        fmt,size=WATCH_TYPES[watch["type"]]
        raw=self._read_raw(address,size)
        if raw is None:return {"ok":False,"address":address,"error":"read_failed"}
        value=struct.unpack("<"+fmt,raw)[0]
        if isinstance(value,float) and not math.isfinite(value):value=str(value)
        return {"ok":True,"address":address,"value":value}

class ScoutLabSession:
    SAMPLE_DELAYS=(0,.25,.60,1.00,1.50)

    def __init__(self,io,target,event_cb,folder,watches=(),save_crops=False,capture_lmb=True,interval=.10,focus_mode="auto",candidates=(),active_domain=None,internal_config=None,on_bridge_event=None):
        self.io=io;self.target=target;self.event_cb=event_cb;self.folder=Path(folder)
        self.watches=[parse_watch(x) if isinstance(x,str) else x for x in watches]
        self.active_domain=active_domain
        parsed=[parse_candidate(x) for x in (candidates or [])]
        self.candidates=[x for x in parsed if not active_domain or x["domain"] in (active_domain,"general")]
        self.save_crops=bool(save_crops);self.capture_lmb=bool(capture_lmb);self.interval=max(.05,float(interval));self.closed=threading.Event()
        self.focus_mode=focus_mode if focus_mode in ("auto","crosshair","cursor") else "auto"
        self.last_cursor=None;self.last_cursor_move=0.
        self.latest=queue.Queue(maxsize=1);self.started=time.monotonic();self.last_process=0.;self.last_crop=0.;self.memory=None
        self.pending_samples=[];self.sample_seq=0;self.sample_count=0
        # Every non-visual signal goes through one hub: memory candidates now, bridge records as they
        # arrive, in-process hooks later. Controllers never read it; it feeds shadow comparison only.
        self.hub=SignalHub(active_domain or "general")
        self.hub.add(MemoryCandidateSource(self.candidates,self._open_memory,self.event_cb)).start()
        self.on_bridge_event=on_bridge_event
        self.internal=InternalTelemetryHub(self.io.pid(self.target),self._internal_event,internal_config).start() if internal_config else None
        self.sample_dir=self.folder/"samples";self.context_dir=self.folder/"sample_context";self.labels_path=self.folder/"labels.csv"
        if self.capture_lmb:self._prepare_labels()
        self.thread=threading.Thread(target=self._run,daemon=True,name="scout-lab");self.thread.start()

    def close(self,wait=True):
        """Stop Scout sampling and release the process handle before returning."""
        self.closed.set()
        if wait:
            t=getattr(self,"thread",None)
            if t and t is not threading.current_thread() and t.is_alive():t.join(timeout=2.0)
        if self.memory:self.memory.close();self.memory=None
        if self.internal:self.internal.close();self.internal=None
        self.hub.close()

    def _open_memory(self):
        """Shared read-only backend for anonymous watches and the memory candidate source."""
        if self.memory is None:self.memory=ReadOnlyMemory(self.io.pid(self.target))
        return self.memory

    def _internal_event(self,source,signal,value=None,**kw):
        """Record a bridge/hook event, mirror it into the hub, and hand Cheat Engine replies to the UI."""
        self.event_cb(source,signal,value,**kw)
        details=kw.get("details") or {}
        if source=="game_internal":
            try:self.hub.ingest_bridge(signal,value,details,kw.get("mono"),details.get("provider"))
            except Exception:pass
            if self.on_bridge_event:
                try:self.on_bridge_event(signal,value,details)
                except Exception as e:self.event_cb("system","bridge_event_error",type(e).__name__+": "+str(e),stream="system")

    def snapshot(self,now=None):
        """Latest fresh non-visual signals for the active domain (for shadow comparison)."""
        return self.hub.snapshot(now)

    def _offer(self,value):
        try:self.latest.put_nowait(value)
        except queue.Full:
            try:self.latest.get_nowait()
            except queue.Empty:pass
            try:self.latest.put_nowait(value)
            except queue.Full:pass

    def _cursor(self):
        from ctypes import wintypes as w
        p=w.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(p)):return None
        return int(p.x),int(p.y)

    def _prepare_labels(self):
        self.sample_dir.mkdir(parents=True,exist_ok=True)
        self.context_dir=getattr(self,"context_dir",self.folder/"sample_context")
        self.context_dir.mkdir(parents=True,exist_ok=True)
        if not self.labels_path.exists():
            with self.labels_path.open("w",newline="",encoding="utf-8") as f:
                csv.writer(f).writerow(["sample_id","delay_ms","mono","image","focus_source","focus_x","focus_y","label","notes"])
        guide=self.folder/"LABELING_README.txt"
        if not guide.exists():
            guide.write_text(
                "Scout LMB sample labeling\n\n"
                "Every left-click while the bound game is foreground creates a short screenshot burst.\n"
                "Aim mode always centers on the game crosshair. Auto mode uses the free cursor only after recent cursor movement; otherwise it uses the crosshair.\n"
                "samples contains clean raw crops. sample_context contains a full-game review image at t+0 with the sampled rectangle drawn on the original screen.\n"
                "Open labels.csv and fill only the label / notes columns; keep IDs/timestamps/image paths unchanged.\n"
                "Suggested labels: target, head, item_pickup, hit, crit, miss, inventory, other.\n"
                "A click can produce several delayed frames so projectile impact can appear after the shot.\n",
                encoding="utf-8")

    def _lmb_edge(self):
        if not self.capture_lmb:return False
        try:return bool(ctypes.windll.user32.GetAsyncKeyState(0x01)&1)
        except Exception:return False

    def _sample_focus(self,client,cursor,now=None):
        x,y,w,h=client;sx=x+w//2;sy=y+h//2
        if self.focus_mode=="crosshair":return "crosshair",sx,sy
        if self.focus_mode=="cursor" and cursor:
            cx,cy=cursor
            if x<=cx<x+w and y<=cy<y+h:return "cursor",cx,cy
        now=time.monotonic() if now is None else now
        if cursor:
            cx,cy=cursor
            if self.last_cursor is None or math.hypot(cx-self.last_cursor[0],cy-self.last_cursor[1])>=3:
                self.last_cursor_move=now
            self.last_cursor=cursor
            recent=(now-self.last_cursor_move)<=.80
            inside=x<=cx<x+w and y<=cy<y+h
            # A free inventory/UI cursor is actively moving away from centre.
            # A stale/hidden Windows cursor is ignored so aiming samples stay on the crosshair.
            if self.focus_mode=="auto" and inside and recent and math.hypot(cx-sx,cy-sy)>45:
                return "cursor",cx,cy
        return "crosshair",sx,sy

    def _queue_lmb_sample(self,client,cursor,now):
        self.sample_seq+=1
        sid=f"{self.sample_seq:05d}-{int((now-self.started)*1000):09d}"
        source,fx,fy=self._sample_focus(client,cursor,now)
        for delay in self.SAMPLE_DELAYS:
            self.pending_samples.append({"due":now+delay,"sample_id":sid,"delay_ms":int(delay*1000),
                                         "focus_source":source,"focus_x":fx,"focus_y":fy})
        mem=self._memory(now)
        self.event_cb("annotation","lmb_sample_trigger",
                      {"sample_id":sid,"focus_source":source,"screen":[fx,fy],"delays_ms":[int(x*1000) for x in self.SAMPLE_DELAYS],
                       "memory":mem},mono=now,stream="annotations")

    def _capture_due_samples(self,grab,client,now):
        if not self.pending_samples:return
        x,y,w,h=client;remaining=[]
        for s in self.pending_samples:
            if s["due"]>now:
                remaining.append(s);continue
            fx=max(x,min(x+w-1,int(s["focus_x"])));fy=max(y,min(y+h-1,int(s["focus_y"])))
            cw=min(640,w);ch=min(360,h)
            left=max(x,min(x+w-cw,fx-cw//2));top=max(y,min(y+h-ch,fy-ch//2))
            try:
                frame=grab.grab({"left":left,"top":top,"width":cw,"height":ch})
                import cv2
                name=f"{s['sample_id']}_t+{s['delay_ms']:04d}.png";path=self.sample_dir/name
                cv2.imwrite(str(path),frame)
                rel=str(Path("samples")/name)
                review_name=None
                # One review image per click: the original game screen with the actual probe rectangle marked.
                # Raw training crops stay untouched in samples/.
                if s["delay_ms"]==0:
                    full=grab.grab({"left":x,"top":y,"width":w,"height":h})
                    scale=min(1.0,1280.0/max(1,w))
                    rw=max(1,int(w*scale));rh=max(1,int(h*scale))
                    review=cv2.resize(full,(rw,rh),interpolation=cv2.INTER_AREA) if scale<1.0 else full.copy()
                    rx1=int((left-x)*scale);ry1=int((top-y)*scale)
                    rx2=int((left-x+cw)*scale);ry2=int((top-y+ch)*scale)
                    cv2.rectangle(review,(rx1,ry1),(rx2,ry2),(0,255,255),2)
                    cv2.drawMarker(review,(int((fx-x)*scale),int((fy-y)*scale)),(0,255,255),
                                   cv2.MARKER_CROSS,18,2)
                    banner=f"{name} | probe={s['focus_source']} | yellow box = saved 640x360 sample"
                    cv2.rectangle(review,(0,0),(rw,min(34,rh)),(0,0,0),-1)
                    cv2.putText(review,banner,(8,min(24,rh-5)),cv2.FONT_HERSHEY_SIMPLEX,.52,(0,255,255),1,cv2.LINE_AA)
                    review_name=f"{s['sample_id']}_probe_area.jpg"
                    cv2.imwrite(str(self.context_dir/review_name),review,[int(cv2.IMWRITE_JPEG_QUALITY),84])
                with self.labels_path.open("a",newline="",encoding="utf-8") as f:
                    csv.writer(f).writerow([s["sample_id"],s["delay_ms"],f"{now:.6f}",rel,s["focus_source"],
                                            fx-x,fy-y,"",""])
                self.sample_count+=1
                self.event_cb("vision","lmb_sample_frame",
                              {"sample_id":s["sample_id"],"delay_ms":s["delay_ms"],"image":rel,
                               "context_image":str(Path("sample_context")/review_name) if review_name else None,
                               "focus_source":s["focus_source"],"focus_client":[fx-x,fy-y],
                               "capture_rect":[left-x,top-y,cw,ch]},mono=now,stream="vision")
            except Exception as e:
                self.event_cb("vision","lmb_sample_error",type(e).__name__+": "+str(e),mono=now,stream="vision")
        self.pending_samples=remaining

    def _process(self,now):
        import psutil
        try:
            p=psutil.Process(self.io.pid(self.target))
            with p.oneshot():
                value={"pid":p.pid,"name":p.name(),"rss":p.memory_info().rss,"threads":p.num_threads(),"cpu_percent":p.cpu_percent(None)}
            self.event_cb("process","lab_process",value,mono=now,stream="process")
            return value
        except Exception as e:
            self.event_cb("process","lab_process_error",type(e).__name__+": "+str(e),mono=now,stream="process")
            return {"error":str(e)}

    def _memory(self,now):
        out=[]
        if self.watches:
            try:self._open_memory()
            except Exception as e:
                # One backend_error per distinct failure, not ten per second. With candidates configured
                # the MemoryCandidateSource reports the same backend failure (with its retry backoff).
                err=type(e).__name__+": "+str(e)
                if not self.candidates and getattr(self,"_watch_error",None)!=err:
                    self._watch_error=err;self.event_cb("memory","backend_error",err,mono=now,stream="memory")
            else:
                for watch in self.watches:
                    try:r=self.memory.read(watch)
                    except Exception as e:r={"ok":False,"error":type(e).__name__+": "+str(e)}
                    row={"spec":watch["spec"],**r};out.append(row)
                    self.event_cb("memory","watch",row,mono=now,stream="memory")
        out+=self.hub.poll(now)
        return out

    def _run(self):
        try:
            from capture import Grabber
            grab=Grabber()
            while not self.closed.is_set():
                tick=time.monotonic()
                if self.io.foreground()!=self.target:
                    self._offer({"foreground":False});self.closed.wait(self.interval);continue
                client=self.io.rect(self.target);x,y,w,h=client
                cursor=self._cursor();visual=None;cross=None;inside=False;rel=None
                if self._lmb_edge():self._queue_lmb_sample(client,cursor,tick)
                self._capture_due_samples(grab,client,tick)
                try:
                    if cursor:
                        cx,cy=cursor;inside=x<=cx<x+w and y<=cy<y+h
                        rel=[cx-x,cy-y,(cx-x)/w if w else None,(cy-y)/h if h else None]
                        if inside:
                            patch=grab.grab({"left":cx-4,"top":cy-4,"width":9,"height":9});visual=visual_features(patch)
                            self.event_cb("vision","cursor_probe",{"screen":[cx,cy],"client":rel[:2],"normalized":rel[2:],"features":visual},
                                          mono=tick,details={"client_rect":[x,y,w,h]},stream="vision")
                            if self.save_crops and tick-self.last_crop>=1.0:
                                crop=grab.grab({"left":cx-48,"top":cy-32,"width":96,"height":64})
                                import cv2
                                d=self.folder/"scout_lab_crops";d.mkdir(parents=True,exist_ok=True)
                                name=f"{tick-self.started:09.3f}-cursor.png";cv2.imwrite(str(d/name),crop);self.last_crop=tick
                                self.event_cb("vision","cursor_crop",name,mono=tick,stream="vision")
                    sx=x+w//2;sy=y+h//2
                    center=grab.grab({"left":sx-4,"top":sy-4,"width":9,"height":9});cross=visual_features(center)
                    self.event_cb("vision","crosshair_probe",{"screen":[sx,sy],"client":[w//2,h//2],"features":cross},
                                  mono=tick,details={"client_rect":[x,y,w,h]},stream="vision")
                except Exception as e:
                    self.event_cb("vision","probe_error",type(e).__name__+": "+str(e),mono=tick,stream="vision")
                proc=None
                if tick-self.last_process>=1.0:proc=self._process(tick);self.last_process=tick
                mem=self._memory(tick)
                self._offer({"foreground":True,"cursor":cursor,"inside":inside,"client":rel,"cursor_features":visual,
                             "crosshair_features":cross,"memory":mem,"process":proc,"sample_frames":self.sample_count,
                             "pending_sample_frames":len(self.pending_samples),
                             "internal":None if not self.internal else self.internal.status()})
                self.closed.wait(max(0.,self.interval-(time.monotonic()-tick)))
        except Exception as e:self._offer({"error":type(e).__name__+": "+str(e)})

class ScoutLabPanel:
    def __init__(self,app,parent,colors,extra=None,output=None):
        import tkinter as tk
        self.app=app;self.tk=tk;self.c=colors;self.session=None;self.sidecar=None
        self.status=tk.StringVar(value="Idle — bind the game, configure optional watches, then START RECORDING.")
        self.live=tk.StringVar(value="No samples yet.")
        self.watch_var=tk.StringVar(value="")
        self.watches=list(app.settings.get("scout_memory_watches",[]) or [])
        self.candidates=list(app.settings.get("scout_memory_candidates",[]) or [])
        self.candidate_name=tk.StringVar(value="");self.candidate_domain=tk.StringVar(value="fishing")
        self.candidate_role=tk.StringVar(value="phase");self.candidate_spec=tk.StringVar(value="")
        self.save_crops=tk.BooleanVar(value=bool(app.settings.get("scout_save_cursor_crops",False)))
        self.capture_lmb=tk.BooleanVar(value=bool(app.settings.get("scout_capture_lmb_samples",True)))
        self.background=tk.BooleanVar(value=bool(app.settings.get("scout_background_probes",True)))
        # Research edition: read the UE4SS and Cheat Engine JSONL files unless the user chose otherwise.
        self.bridge_enabled=tk.BooleanVar(value=bool(app.settings.get("scout_internal_bridge_enabled",True)))
        self.bridge_path=tk.StringVar(value=str(app.settings.get("scout_internal_bridge_path","") or "; ".join(default_bridge_paths())))
        self.frida_enabled=tk.BooleanVar(value=bool(app.settings.get("scout_frida_enabled",False)))
        self.frida_hook_var=tk.StringVar(value="")
        self.frida_hooks=list(app.settings.get("scout_frida_hooks",[]) or [])
        # Research data gathering: pick up the user's Cheat Engine table automatically and let the
        # Fishing state timeline drive Cheat Engine's differential scans (experimental, opt-in).
        self.auto_import=tk.BooleanVar(value=bool(app.settings.get("scout_ce_auto_import",True)))
        self.scan_assist=tk.BooleanVar(value=bool(app.settings.get("scout_ce_scan_assistant",False)))
        var_type=str(app.settings.get("scout_ce_scan_var_type","4 Bytes"))
        self.scan_var_type=tk.StringVar(value=var_type if var_type in VAR_TYPES else "4 Bytes")
        self.assistant=None;self.sources_text=tk.StringVar(value="Data sources: checking…")
        self.last_sources_check=0.;self.analysis_thread=None;self.analysis_result=None
        self._build(parent,extra or parent,output or parent)

    def _build(self,p,extra,out):
        """p: settings column 1 · extra: settings column 2 (Cheat Engine, research data) · out: TOOL OUTPUT column."""
        import ui_theme as T
        tk=self.tk;persist=self.app.persist
        T.heading(p,'SAMPLING',pady=(0,4)).pack(fill='x')
        T.caption(p,'Cursor / crosshair probes, process stats and read-only memory reads on one timeline. Scout never writes memory and never moves the mouse.').pack(fill='x',pady=(0,4))
        T.check(p,'Save a 96×64 cursor crop once per second',self.save_crops,lambda:persist("scout_save_cursor_crops",self.save_crops.get())).pack(fill='x')
        T.check(p,'LMB sample burst → screenshots + editable labels.csv',self.capture_lmb,lambda:persist("scout_capture_lmb_samples",self.capture_lmb.get())).pack(fill='x')
        T.check(p,'Run independent Scout probes alongside Auto / Fishing / Aim',self.background,lambda:persist("scout_background_probes",self.background.get()),accent=True).pack(fill='x')
        f,_=T.button_row(p,[(title,lambda x=label:self.mark(x)) for label,title in (("target","MARK TARGET"),("head","HEAD"),("inventory","INVENTORY"),("hit","HIT"),("miss","MISS"))],height=30);f.pack(fill='x',pady=(6,0))
        T.heading(p,'MEMORY WATCH').pack(fill='x',pady=(12,4))
        T.caption(p,'MODULE+0xOFFSET:type · [[MODULE+0xOFFSET]+0x10]+0x8:type · 0xADDRESS:type').pack(fill='x')
        T.entry(p,self.watch_var).pack(fill='x',pady=(2,4))
        f,_=T.button_row(p,[('ADD WATCH',self.add_watch),('CLEAR WATCHES',self.clear_watches)],height=30);f.pack(fill='x')
        self.watch_text=tk.StringVar();T.label(p,var=self.watch_text,color=T.MUTED,font=('Consolas',8),wrap=400).pack(fill='x',pady=(4,0))
        self._refresh_watches()
        T.heading(p,'SEMANTIC CANDIDATES').pack(fill='x',pady=(12,4))
        T.caption(p,'Name · domain · role, then the address or pointer chain. A table saved in Cheat Engine is imported for you when a session starts.').pack(fill='x')
        row=tk.Frame(p,bg=p['bg']);row.pack(fill='x',pady=(2,0))
        T.entry(row,self.candidate_name,12).pack(side='left')
        T.combo(row,self.candidate_domain,("fishing","auto_picker","general"),width=11).pack(side='left',padx=4)
        self.role_box=T.combo(row,self.candidate_role,CANDIDATE_ROLES["fishing"],width=18,state='normal');self.role_box.pack(side='left')
        T.entry(p,self.candidate_spec).pack(fill='x',pady=(3,4))
        f,_=T.button_row(p,[('ADD CANDIDATE',self.add_candidate),('CLEAR CANDIDATES',self.clear_candidates)],height=30);f.pack(fill='x')
        f,_=T.button_row(p,[('IMPORT CE TABLE…',self.import_ce_table),('RELOAD OrcishScout.CT',self.import_default_table)],height=30);f.pack(fill='x',pady=(5,0))
        T.check(p,'Auto-import data\\cheat-engine\\OrcishScout.CT when a session starts',self.auto_import,lambda:persist("scout_ce_auto_import",self.auto_import.get()),wrap=400).pack(fill='x',pady=(4,0))
        self.candidate_text=tk.StringVar();T.label(p,var=self.candidate_text,color=T.MUTED,font=('Consolas',8),wrap=400).pack(fill='x',pady=(4,0))
        self._refresh_candidates()
        self.candidate_domain.trace_add("write",lambda *_:self._sync_roles())
        # --- column 2: external data sources
        T.heading(extra,'CHEAT ENGINE',pady=(0,4)).pack(fill='x')
        T.check(extra,'Read JSONL bridges (Cheat Engine + UE4SS); several paths separated by ;',self.bridge_enabled,self._persist_internal,wrap=400).pack(fill='x')
        T.entry(extra,self.bridge_path).pack(fill='x',pady=(2,8))
        T.caption(extra,'Scan assistant · experimental',color=T.GOLD).pack(fill='x')
        T.check(extra,'Let Fishing states drive Cheat Engine scans (first / changed / unchanged) while OrcishScout.CT is open',self.scan_assist,lambda:persist("scout_ce_scan_assistant",self.scan_assist.get()),wrap=400).pack(fill='x')
        row=tk.Frame(extra,bg=extra['bg']);row.pack(fill='x',pady=4)
        T.label(row,'Value type',color=T.MUTED,font=T.FONT_SMALL).pack(side='left')
        box=T.combo(row,self.scan_var_type,VAR_TYPES,width=9);box.pack(side='left',padx=6)
        box.bind("<<ComboboxSelected>>",lambda *_:persist("scout_ce_scan_var_type",self.scan_var_type.get()))
        T.RuneButton(row,'RESET SCAN',self.reset_scan,height=30).pack(side='left',padx=6)
        T.heading(extra,'RESEARCH DATA').pack(fill='x',pady=(12,4))
        T.label(extra,var=self.sources_text,color=T.MUTED,font=('Consolas',8),wrap=400).pack(fill='x')
        f,_=T.button_row(extra,[('ANALYZE LATEST SESSION',self.analyze_latest),('OPEN REPORTS',self.open_reports)],height=30);f.pack(fill='x',pady=(6,0))
        T.heading(extra,'PARKED · FRIDA HOOKS').pack(fill='x',pady=(12,4))
        T.caption(extra,'Native function-entry telemetry (optional package). Kept for research; not needed for the Cheat Engine path.').pack(fill='x')
        T.check(extra,'Observe native function entry with Frida',self.frida_enabled,self._persist_internal).pack(fill='x')
        T.caption(extra,'Hook · label=MODULE+0xOFFSET').pack(fill='x')
        T.entry(extra,self.frida_hook_var).pack(fill='x',pady=(2,4))
        f,_=T.button_row(extra,[('ADD FUNCTION HOOK',self.add_frida_hook),('CLEAR HOOKS',self.clear_frida_hooks)],height=30);f.pack(fill='x')
        self.frida_text=tk.StringVar();T.label(extra,var=self.frida_text,color=T.MUTED,font=('Consolas',8),wrap=400).pack(fill='x',pady=(4,0))
        self._refresh_frida()
        # --- output column
        T.card_text(out,self.status,color=T.GREEN,font=T.FONT_SMALL,wrap=330,height=3).pack(fill='x')
        T.card_text(out,self.live,font=('Consolas',8),wrap=330,height=7).pack(fill='x',pady=(6,0))

    def _refresh_watches(self):
        self.watch_text.set("Memory watches: none" if not self.watches else "Memory watches:\n"+"\n".join("  "+x for x in self.watches[:8]))

    def _sync_roles(self):
        roles=CANDIDATE_ROLES.get(self.candidate_domain.get(),CANDIDATE_ROLES["general"])
        if hasattr(self,"role_box"):self.role_box.configure(values=roles)
        if self.candidate_role.get() not in roles:self.candidate_role.set(roles[0])

    def _refresh_candidates(self):
        if not self.candidates:self.candidate_text.set("Semantic candidates: none");return
        lines=[]
        for x in self.candidates[:10]:
            lines.append(f"  [{x.get('domain','?')}] {x.get('name','?')} → {x.get('role','?')} · {x.get('spec','?')}")
        self.candidate_text.set("Semantic candidates:\n"+"\n".join(lines))

    def _persist_internal(self,*_):
        self.app.persist("scout_internal_bridge_enabled",self.bridge_enabled.get())
        self.app.persist("scout_internal_bridge_path",self.bridge_path.get().strip())
        self.app.persist("scout_frida_enabled",self.frida_enabled.get())

    def _internal_config(self):
        self._persist_internal()
        paths=parse_bridge_paths(self.bridge_path.get()) or default_bridge_paths()
        return {"bridge_enabled":self.bridge_enabled.get(),"bridge_paths":paths,
                "frida_enabled":self.frida_enabled.get(),"frida_hooks":list(self.frida_hooks)}

    def _refresh_frida(self):
        avail="installed" if FridaFunctionProvider.available() else "not installed"
        if not self.frida_hooks:self.frida_text.set(f"Frida: {avail} · hooks: none");return
        self.frida_text.set(f"Frida: {avail} · hooks:\n"+"\n".join("  "+x for x in self.frida_hooks[:8]))

    def add_frida_hook(self):
        try:h=parse_function_hook(self.frida_hook_var.get())
        except Exception as e:self.status.set(str(e));return
        if h["spec"] not in self.frida_hooks:self.frida_hooks.append(h["spec"])
        self.app.persist("scout_frida_hooks",self.frida_hooks);self.frida_hook_var.set("");self._refresh_frida()
        self.status.set("Function hook saved. Restart recording/feature to apply it.")

    def clear_frida_hooks(self):
        self.frida_hooks=[];self.app.persist("scout_frida_hooks",[]);self._refresh_frida()
        self.status.set("Frida function hooks cleared.")

    def add_candidate(self):
        value={"name":self.candidate_name.get(),"domain":self.candidate_domain.get(),
               "role":self.candidate_role.get(),"spec":self.candidate_spec.get()}
        try:parse_candidate(value)
        except Exception as e:self.status.set(str(e));return
        self.candidates=[x for x in self.candidates if not (x.get("domain")==value["domain"] and x.get("name")==value["name"])]
        self.candidates.append(value);self.app.persist("scout_memory_candidates",self.candidates)
        self.candidate_name.set("");self.candidate_spec.set("");self._refresh_candidates()
        self.status.set("Candidate saved. Restart recording/feature to apply it.")

    def import_ce_table(self):
        from tkinter import filedialog
        start=research_setup.ce_table().parent
        path=filedialog.askopenfilename(title="Import Cheat Engine table",filetypes=[("Cheat Engine table","*.CT"),("All files","*.*")],
                                        initialdir=str(start if start.is_dir() else start.parent))
        if not path:return
        added,skipped,error=self._import_table(path,self.candidate_domain.get())
        if error:self.status.set("Import failed: "+error);return
        note=f" Skipped {len(skipped)}: "+"; ".join(f"{s['name']} ({s['reason']})" for s in skipped[:3]) if skipped else ""
        self.status.set(f"Imported {added} Cheat Engine record(s) as {self.candidate_domain.get()} candidates. Restart recording to apply.{note}")

    def import_default_table(self):
        p=research_setup.ce_table()
        if not p.is_file():self.status.set(f"No table yet: {p} (Setup.cmd → 7 or D creates it).");return
        added,skipped,error=self._import_table(p,self.candidate_domain.get())
        if error:self.status.set("Import failed: "+error);return
        self.status.set(f"Reloaded {p.name}: {added} record(s) as {self.candidate_domain.get()} candidates, {len(skipped)} skipped. Restart recording to apply.")

    def _import_table(self,path,domain):
        """Merge a .CT into the saved candidates; returns (added, skipped, error)."""
        try:
            with open(path,encoding="utf-8",errors="replace") as f:records,skipped=parse_cheat_table(f.read())
        except Exception as e:return 0,[],str(e)
        self.candidates,added=merge_ce_candidates(self.candidates,records,domain)
        self.app.persist("scout_memory_candidates",self.candidates);self._refresh_candidates()
        return added,skipped,None

    def auto_import_for(self,domain):
        """Session start: pick up the user's saved table without a dialog (opt-out checkbox)."""
        if not self.auto_import.get() or domain not in CANDIDATE_ROLES:return None
        p=research_setup.ce_table()
        if not p.is_file():return None
        added,skipped,error=self._import_table(p,domain)
        result={"table":str(p),"domain":domain,"added":added,"skipped":len(skipped),"error":error}
        self.app.scout_event("system","ce_table_auto_import",result,stream="system")
        return result

    def reset_scan(self):
        if not self.assistant:self.status.set("Scan assistant runs during a Fishing session with the option enabled.");return
        self.assistant.reset();self.status.set("Scan assistant reset: the next settled fishing phase starts a new first scan.")

    def _bridge_event(self,signal,value,details):
        if self.assistant:self.assistant.bridge_event(signal,value,details)

    def observe_fishing_state(self,state,now):
        """Called by the Fishing panel after each controller decision (UI thread)."""
        if self.assistant:self.assistant.observe(state,now)

    def _start_assistant(self,domain):
        self.assistant=None
        if domain!="fishing" or not self.scan_assist.get():return
        try:
            self.assistant=ScanAssistant(research_setup.ce_commands(),self.app.scout_event,ScanPlanner(var_type=self.scan_var_type.get()))
            self.app.scout_event("system","scan_assistant_started",{"var_type":self.scan_var_type.get(),"path":str(self.assistant.path)},stream="system")
        except Exception as e:
            self.assistant=None;self.app.scout_event("system","scan_assistant_error",type(e).__name__+": "+str(e),stream="system")

    def _stop_assistant(self):
        a=self.assistant;self.assistant=None
        if a and getattr(self.app,"scout",None):self.app.scout_event("system","scan_assistant_stopped",a.summary(),stream="system")

    def refresh_sources(self,now):
        if now-self.last_sources_check<2.0:return
        self.last_sources_check=now
        try:
            s=research_setup.status(quick=True);ce=s["cheat_engine"]
            if not ce["exists"]:stream="CE stream: none yet"
            else:
                age=ce["age_s"];stream=f"CE stream: {'live' if age is not None and age<120 else 'stale'} · last '{ce['last_signal']}' {age:.0f}s ago"
            by={}
            for c in self.candidates:by[c.get("domain","?")]=by.get(c.get("domain","?"),0)+1
            cands=", ".join(f"{k} {v}" for k,v in sorted(by.items())) or "none"
            lines=[stream,f"table: {'yes' if s['cheat_table'] else 'no'} · candidates: {cands} · auto-import {'on' if self.auto_import.get() else 'off'}"]
            if self.assistant:lines.append("scan assistant: "+self.assistant.status())
            elif self.scan_assist.get():lines.append("scan assistant: armed (starts with a Fishing session)")
            self.sources_text.set("\n".join(lines))
        except Exception as e:self.sources_text.set("Data sources: "+type(e).__name__+": "+str(e))

    def analyze_latest(self):
        if self.analysis_thread and self.analysis_thread.is_alive():self.status.set("Analysis already running…");return
        from scout_analysis import latest_session, write_report
        try:latest=latest_session(str(self.app.folder))
        except (FileNotFoundError,OSError):self.status.set("No Scout session recorded yet.");return
        def run():
            try:jp,mp,_=write_report(latest,str(self.app.folder));self.analysis_result=(True,f"Report written: {mp}")
            except Exception as e:self.analysis_result=(False,"Analysis failed: "+type(e).__name__+": "+str(e))
        self.analysis_thread=threading.Thread(target=run,daemon=True,name="scout-analysis");self.analysis_thread.start()
        self.status.set(f"Analyzing {Path(latest).name}…")

    def open_reports(self):
        d=Path(self.app.folder)/"scout_reports";d.mkdir(parents=True,exist_ok=True)
        try:os.startfile(str(d))
        except Exception as e:self.status.set("Cannot open folder: "+str(e))

    def clear_candidates(self):
        self.candidates=[];self.app.persist("scout_memory_candidates",[]);self._refresh_candidates()
        self.status.set("Semantic candidates cleared.")

    def add_watch(self):
        try:w=parse_watch(self.watch_var.get())
        except Exception as e:self.status.set(str(e));return
        if w["spec"] not in self.watches:self.watches.append(w["spec"])
        self.app.persist("scout_memory_watches",self.watches);self.watch_var.set("");self._refresh_watches()
        self.status.set("Watch saved. Restart recording to apply the updated watch list.")

    def clear_watches(self):
        self.watches=[];self.app.persist("scout_memory_watches",[]);self._refresh_watches()
        self.status.set("Memory watches cleared.")

    def start(self):
        if self.session:self.stop()
        if self.app.visual:self.status.set("Scout Lab requires a real Windows game target.");return
        if not self.app.target:self.status.set("Bind the game first.");return
        self.app.scout_start("scout_lab","Research")
        try:
            folder=self.app.scout.folder if getattr(self.app,"scout",None) else self.app.folder
            self.auto_import_for(self.candidate_domain.get())
            self.session=ScoutLabSession(self.app.io,self.app.target,self.app.scout_event,folder,self.watches,self.save_crops.get(),self.capture_lmb.get(),focus_mode="auto",candidates=self.candidates,active_domain=None,internal_config=self._internal_config(),on_bridge_event=self._bridge_event)
            self.status.set("RECORDING — LMB creates screenshot bursts; label them later in this session's labels.csv.")
        except Exception as e:
            self.app.scout_stop("Scout Lab start failed");self.session=None;self.status.set("Start failed: "+str(e))

    def stop(self):
        s=self.session;self.session=None
        if s:s.close()
        # Stop a sidecar even if its recorder was already closed elsewhere.
        self.stop_sidecar()
        if s and getattr(self.app,"scout",None):self.app.scout_stop("Scout Lab stopped")
        self.live.set("No samples yet.")
        if s:self.status.set("Stopped. Raw Scout Lab logs preserved in data/scout_sessions.")

    def shutdown(self):
        self.stop()

    def start_sidecar(self,domain=None):
        if self.sidecar or not self.background.get() or self.app.visual or not self.app.target or not getattr(self.app,"scout",None):return
        try:
            focus_mode="crosshair" if domain=="aim" else "auto"
            # Fishing has its own calibrated BAR/STOP/REEL/result diagnostics. Generic
            # cursor crops and LMB 640x360 bursts only capture unrelated HUD/terrain.
            fishing_specific=domain=="fishing"
            save_crops=False if fishing_specific else self.save_crops.get()
            capture_lmb=False if fishing_specific else self.capture_lmb.get()
            self.auto_import_for(domain)
            self._start_assistant(domain)
            self.sidecar=ScoutLabSession(self.app.io,self.app.target,self.app.scout_event,self.app.scout.folder,self.watches,save_crops,capture_lmb,focus_mode=focus_mode,candidates=self.candidates,active_domain=domain,internal_config=self._internal_config(),on_bridge_event=self._bridge_event)
            self.app.scout_event("system","sidecar_started",{"watches":len(self.watches),"cursor_crops":save_crops,
                                 "lmb_samples":capture_lmb,"focus_mode":focus_mode,"semantic_candidates":len(self.candidates),
                                 "internal_bridge":self.bridge_enabled.get(),"frida":self.frida_enabled.get(),
                                 "frida_hooks":len(self.frida_hooks),"scan_assistant":bool(self.assistant)},stream="system")
        except Exception as e:
            self.sidecar=None;self._stop_assistant()
            self.app.scout_event("system","sidecar_error",type(e).__name__+": "+str(e),stream="system")

    def stop_sidecar(self):
        s=self.sidecar;self.sidecar=None
        self._stop_assistant()
        if s:
            s.close()
            self.app.scout_event("system","sidecar_stopped",True,stream="system")

    def mark(self,label):
        if not self.session:self.status.set("Start recording before adding labels.");return
        now=time.monotonic();self.app.scout_event("annotation","mark",label,mono=now,stream="annotations")
        self.status.set("Marked: "+label)

    def tick(self):
        now=time.monotonic();self.refresh_sources(now)
        if self.analysis_result:
            ok,msg=self.analysis_result;self.analysis_result=None;self.status.set(msg)
        active=self.session or self.sidecar
        if not active:return
        latest=None
        while True:
            try:latest=active.latest.get_nowait()
            except queue.Empty:break
        if latest is None:return
        if latest.get("error"):self.live.set("ERROR: "+latest["error"]);return
        if not latest.get("foreground"):self.live.set("Game not foreground — sampling paused.");return
        cur=latest.get("cursor");rel=latest.get("client");feat=latest.get("cursor_features") or {}
        mem=latest.get("memory") or []
        lines=[f"cursor screen={cur}  client={None if not rel else rel[:2]}",
               f"cursor center BGR={feat.get('center_bgr')}  patch σ={feat.get('std')}",
               f"crosshair BGR={(latest.get('crosshair_features') or {}).get('center_bgr')}",
               f"memory reads={len(mem)} · candidates={len(self.candidates)}",
               f"LMB sample frames={latest.get('sample_frames',0)}  pending={latest.get('pending_sample_frames',0)}"]
        internal=latest.get("internal") or {}
        if internal:lines.append(f"internal sources={', '.join(internal.get('providers',[])) or 'none'} · events={internal.get('events',0)} · errors={len(internal.get('errors',[]))}")
        for m in mem[:4]:
            lines.append(f"  {m.get('spec')}: {m.get('value') if m.get('ok') else m.get('error')}")
        self.live.set("\n".join(lines))
