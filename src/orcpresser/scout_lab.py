"""Scout Lab: supervised visual + read-only process/memory telemetry collection.

The Lab is deliberately observational. It records cursor/crosshair visual probes,
ordinary process metadata and explicitly configured read-only memory watches on
the same Scout timeline. It never writes game memory and never moves the mouse.
"""
from __future__ import annotations
from pathlib import Path
import ctypes, json, math, os, queue, struct, sys, threading, time

WATCH_TYPES={"u8":("B",1),"u16":("H",2),"u32":("I",4),"i32":("i",4),"f32":("f",4),"f64":("d",8)}

def parse_watch(spec):
    """Parse MODULE+0xOFFSET:TYPE or 0xABSOLUTE:TYPE into a normalized watch."""
    s=(spec or "").strip()
    if ":" not in s:raise ValueError("Use MODULE+0xOFFSET:type or 0xADDRESS:type")
    addr,typ=[x.strip() for x in s.rsplit(":",1)]
    typ=typ.lower()
    if typ not in WATCH_TYPES:raise ValueError("Type must be one of: "+", ".join(WATCH_TYPES))
    if "+" in addr:
        module,off=[x.strip() for x in addr.rsplit("+",1)]
        if not module:raise ValueError("Module name is empty")
        offset=int(off,0)
        if offset<0:raise ValueError("Offset must be non-negative")
        return {"spec":s,"module":module.lower(),"offset":offset,"address":None,"type":typ}
    absolute=int(addr,0)
    if absolute<=0:raise ValueError("Address must be positive")
    return {"spec":s,"module":None,"offset":None,"address":absolute,"type":typ}

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
        self.k.ReadProcessMemory.argtypes=[w.HANDLE,w.LPCVOID,w.LPVOID,w.SIZE_T,ctypes.POINTER(w.SIZE_T)];self.k.ReadProcessMemory.restype=w.BOOL
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

    def read(self,watch):
        address=self.resolve(watch)
        if not address:return {"ok":False,"error":"module_not_found"}
        fmt,size=WATCH_TYPES[watch["type"]];buf=(ctypes.c_ubyte*size)();got=self.w.SIZE_T()
        ok=self.k.ReadProcessMemory(self.handle,ctypes.c_void_p(address),ctypes.byref(buf),size,ctypes.byref(got))
        if not ok or got.value!=size:return {"ok":False,"address":address,"error":"read_failed"}
        value=struct.unpack("<"+fmt,bytes(buf))[0]
        if isinstance(value,float) and not math.isfinite(value):value=str(value)
        return {"ok":True,"address":address,"value":value}

class ScoutLabSession:
    def __init__(self,io,target,event_cb,folder,watches=(),save_crops=False,interval=.10):
        self.io=io;self.target=target;self.event_cb=event_cb;self.folder=Path(folder)
        self.watches=[parse_watch(x) if isinstance(x,str) else x for x in watches]
        self.save_crops=bool(save_crops);self.interval=max(.05,float(interval));self.closed=threading.Event()
        self.latest=queue.Queue(maxsize=1);self.started=time.monotonic();self.last_process=0.;self.last_crop=0.;self.memory=None
        self.thread=threading.Thread(target=self._run,daemon=True,name="scout-lab");self.thread.start()

    def close(self):
        self.closed.set()
        if self.memory:self.memory.close();self.memory=None

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
        if not self.watches:return []
        if self.memory is None:
            try:self.memory=ReadOnlyMemory(self.io.pid(self.target))
            except Exception as e:
                self.event_cb("memory","backend_error",type(e).__name__+": "+str(e),mono=now,stream="memory");return []
        out=[]
        for watch in self.watches:
            try:r=self.memory.read(watch)
            except Exception as e:r={"ok":False,"error":type(e).__name__+": "+str(e)}
            row={"spec":watch["spec"],**r};out.append(row)
            self.event_cb("memory","watch",row,mono=now,stream="memory")
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
                             "crosshair_features":cross,"memory":mem,"process":proc})
                self.closed.wait(max(0.,self.interval-(time.monotonic()-tick)))
        except Exception as e:self._offer({"error":type(e).__name__+": "+str(e)})

class ScoutLabPanel:
    def __init__(self,app,parent,colors):
        import tkinter as tk
        self.app=app;self.tk=tk;self.c=colors;self.session=None
        self.status=tk.StringVar(value="Idle — bind the game, configure optional watches, then START RECORDING.")
        self.live=tk.StringVar(value="No samples yet.")
        self.watch_var=tk.StringVar(value="")
        self.watches=list(app.settings.get("scout_memory_watches",[]) or [])
        self.save_crops=tk.BooleanVar(value=bool(app.settings.get("scout_save_cursor_crops",False)))
        self._build(parent)

    def _build(self,p):
        tk=self.tk;c=self.c
        tk.Label(p,text="SCOUT LAB · DATA ACQUISITION",bg=c["PANEL"],fg=c["GOLD"],font=("Segoe UI",12,"bold"),anchor="w").pack(fill="x")
        tk.Label(p,text="Visual cursor/crosshair probes + OS telemetry + optional read-only module-relative memory watches. No aiming or memory writes.",
                 bg=c["PANEL"],fg=c["MUTED"],wraplength=410,justify="left",anchor="w",font=("Segoe UI",9)).pack(fill="x",pady=(2,8))
        row=tk.Frame(p,bg=c["PANEL"]);row.pack(fill="x",pady=3)
        tk.Button(row,text="START RECORDING",command=self.start).pack(side="left")
        tk.Button(row,text="STOP",command=self.stop).pack(side="left",padx=6)
        row=tk.Frame(p,bg=c["PANEL"]);row.pack(fill="x",pady=3)
        for label,title in (("target","MARK TARGET"),("head","MARK HEAD"),("inventory","MARK INVENTORY"),("hit","MARK HIT"),("miss","MARK MISS")):
            tk.Button(row,text=title,command=lambda x=label:self.mark(x)).pack(side="left",padx=(0,4))
        tk.Checkbutton(p,text="Save 96×64 cursor crop once/second",variable=self.save_crops,
                       command=lambda:self.app.persist("scout_save_cursor_crops",self.save_crops.get()),
                       bg=c["PANEL"],fg=c["BONE"],selectcolor="#15200e",activebackground=c["PANEL"],activeforeground=c["GREEN"],anchor="w").pack(fill="x")
        tk.Label(p,text="Memory watch · MODULE+0xOFFSET:type or 0xADDRESS:type",bg=c["PANEL"],fg=c["GOLD"],anchor="w").pack(fill="x",pady=(10,2))
        entry=tk.Entry(p,textvariable=self.watch_var,bg="#12170f",fg=c["BONE"],insertbackground=c["GREEN"],relief="flat");entry.pack(fill="x")
        row=tk.Frame(p,bg=c["PANEL"]);row.pack(fill="x",pady=4)
        tk.Button(row,text="ADD WATCH",command=self.add_watch).pack(side="left")
        tk.Button(row,text="CLEAR WATCHES",command=self.clear_watches).pack(side="left",padx=6)
        self.watch_text=tk.StringVar();tk.Label(p,textvariable=self.watch_text,bg=c["PANEL"],fg=c["MUTED"],justify="left",anchor="w",wraplength=410,font=("Consolas",8)).pack(fill="x")
        self._refresh_watches()
        tk.Label(p,textvariable=self.status,bg=c["PANEL"],fg=c["GREEN"],justify="left",anchor="w",wraplength=410,font=("Segoe UI",9,"bold")).pack(fill="x",pady=(8,2))
        tk.Label(p,textvariable=self.live,bg="#10150e",fg=c["BONE"],justify="left",anchor="nw",wraplength=410,font=("Consolas",8),height=8).pack(fill="x")

    def _refresh_watches(self):
        self.watch_text.set("Memory watches: none" if not self.watches else "Memory watches:\n"+"
".join("  "+x for x in self.watches[:8]))

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
            self.session=ScoutLabSession(self.app.io,self.app.target,self.app.scout_event,folder,self.watches,self.save_crops.get())
            self.status.set("RECORDING — move the cursor/crosshair over useful objects; use MARK TARGET / MARK HEAD for labels.")
        except Exception as e:
            self.app.scout_stop("Scout Lab start failed");self.session=None;self.status.set("Start failed: "+str(e))

    def stop(self):
        s=self.session;self.session=None
        if s:s.close()
        if getattr(self.app,"scout",None):self.app.scout_stop("Scout Lab stopped")
        if s:self.status.set("Stopped. Raw Scout Lab logs preserved in data/scout_sessions.")

    def mark(self,label):
        if not self.session:self.status.set("Start recording before adding labels.");return
        now=time.monotonic();self.app.scout_event("annotation","mark",label,mono=now,stream="annotations")
        self.status.set("Marked: "+label)

    def tick(self):
        if not self.session:return
        latest=None
        while True:
            try:latest=self.session.latest.get_nowait()
            except queue.Empty:break
        if latest is None:return
        if latest.get("error"):self.live.set("ERROR: "+latest["error"]);return
        if not latest.get("foreground"):self.live.set("Game not foreground — sampling paused.");return
        cur=latest.get("cursor");rel=latest.get("client");feat=latest.get("cursor_features") or {}
        mem=latest.get("memory") or []
        lines=[f"cursor screen={cur}  client={None if not rel else rel[:2]}",
               f"cursor center BGR={feat.get('center_bgr')}  patch σ={feat.get('std')}",
               f"crosshair BGR={(latest.get('crosshair_features') or {}).get('center_bgr')}",
               f"memory watches={len(mem)}"]
        for m in mem[:4]:
            lines.append(f"  {m.get('spec')}: {m.get('value') if m.get('ok') else m.get('error')}")
        self.live.set("\n".join(lines))
