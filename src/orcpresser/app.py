"""Orc Presser — Windows desktop controller. All recognition stays on this PC."""
import os, sys, time, threading, queue, ctypes, atexit, logging, importlib.util
from collections import deque
from pathlib import Path
import tkinter as tk
import numpy as np
import cv2, psutil
from PIL import Image, ImageTk
from engine import Controller, ReactionMeter
from vision import Detector, ACTIONS, exclusions, SPAN
from capture import dxgi_available
from game_profile import PROFILE
from settings import Settings
from paths import CODE, DATA, migrate_data, ensure_data
from version import VERSION
from scout import ScoutRecorder
import bench as benchmod
import keys as keymap
from tkinter import ttk

SCAN_GAP=.12  # min seconds between scan starts; one scan in flight at a time
BG='#171b14'; PANEL='#24281d'; GOLD='#b49758'; BONE='#e6d8b0'; GREEN='#98c657'; MUTED='#9ba087'

class WinIO:
    def __init__(self):
        from ctypes import wintypes as w
        self.u=ctypes.windll.user32
        self.u.GetForegroundWindow.restype=w.HWND
        self.u.GetAncestor.argtypes=[w.HWND,w.UINT];self.u.GetAncestor.restype=w.HWND
        self.u.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
        self.u.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
        self.u.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
        self.u.GetClientRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
        self.u.ClientToScreen.argtypes=[w.HWND,ctypes.POINTER(w.POINT)]
        self.u.VkKeyScanW.argtypes=[w.WCHAR];self.u.VkKeyScanW.restype=ctypes.c_short
        self.lock=threading.RLock();self.held=None;self.target=0;self.heartbeat=time.monotonic();self.tripped=False
        self.used=set()   # every key/button pressed this session; F8, close and exit send key-up for all
        threading.Thread(target=self.watchdog,daemon=True).start()
        atexit.register(self.release_all)
    def foreground(self):return self.u.GetForegroundWindow()
    def title(self,h):
        b=ctypes.create_unicode_buffer(512);self.u.GetWindowTextW(h,b,512);return b.value
    def own(self,h):
        from ctypes import wintypes as w
        pid=w.DWORD();self.u.GetWindowThreadProcessId(h,ctypes.byref(pid));return pid.value==os.getpid()
    def pid(self,h):
        from ctypes import wintypes as w
        pid=w.DWORD();self.u.GetWindowThreadProcessId(h,ctypes.byref(pid));return pid.value
    def game(self,h):
        try:name=psutil.Process(self.pid(h)).name()
        except psutil.Error:name=''
        return PROFILE.matches_window(self.title(h),name)
    def rect(self,h):
        from ctypes import wintypes as w
        r=w.RECT();p=w.POINT()
        self.u.GetClientRect(h,ctypes.byref(r));self.u.ClientToScreen(h,ctypes.byref(p))
        return p.x,p.y,r.right,r.bottom
    def pressed(self,vk):return bool(self.u.GetAsyncKeyState(vk)&0x8000)
    def key(self,name):
        """Validate a key name (dropdown, alias, letter, digit, F-key). Raises ValueError."""
        return keymap.resolve(name)
    def event(self,key,down):
        k=keymap.resolve(key)
        if k.kind=='mouse':self.u.mouse_event(k.down if down else k.up,0,0,k.data,0)
        else:
            scan=self.u.MapVirtualKeyW(k.vk,0)
            self.u.keybd_event(k.vk,scan,(1 if k.extended else 0)|(0 if down else 2),0)
    def move(self,dx,dy=0):
        """Relative mouse move (camera turn in most 3D games). Only while the bound game is in front."""
        with self.lock:
            if dx or dy:
                if self.tripped or not self.target or self.foreground()!=self.target:return False
                self.u.mouse_event(0x0001,int(dx),int(dy),0,0)
            return True
    def output(self,key,down):
        with self.lock:
            if down:
                if self.tripped or not self.target or self.foreground()!=self.target:return
                self.held=key;self.used.add(key);self.event(key,True)
            else:self.event(key,False);self.held=None
    def release(self):
        with self.lock:
            if self.held:self.event(self.held,False);self.held=None
    def release_all(self):
        """Key-up for everything this session touched plus the mouse buttons. An extra key-up is
        harmless; a missing one leaves a button stuck down system-wide."""
        with self.lock:
            self.held=None
            for k in set(self.used)|{'LBUTTON','RBUTTON','MBUTTON'}:
                try:self.event(k,False)
                except Exception:pass
    def watchdog(self):
        while True:
            time.sleep(.025)
            if self.pressed(0x77):self.tripped=True;self.release_all()   # F8: panic, release everything
            elif self.held and (self.foreground()!=self.target or time.monotonic()-self.heartbeat>1.2):
                self.tripped=True;self.release()

class RuneButton(tk.Canvas):
    def __init__(self,parent,text,command,width=140,height=46):
        super().__init__(parent,width=width,height=height,bg=BG,highlightthickness=0,cursor='hand2')
        self.label=text;self.command=command;self.active=False;self.hover=False;self.enabled=True;self.w=width;self.h=height
        self.bind('<Button-1>',lambda e:command())
        self.bind('<Enter>',lambda e:self.set_hover(True));self.bind('<Leave>',lambda e:self.set_hover(False))
        self.bind('<Return>',lambda e:command());self.configure(takefocus=True)
        self.draw()
    def set_hover(self,v):self.hover=v;self.draw()
    def draw(self):
        self.delete('all');w,h=self.w,self.h
        edge=GREEN if self.active else (GOLD if self.enabled else '#5a513c')
        self.create_polygon(8,1,w-8,1,w-1,8,w-1,h-8,w-8,h-1,8,h-1,1,h-8,1,8,fill='#384829' if self.active else '#302c22',outline=edge,width=2)
        self.create_line(10,5,w-10,5,fill='#748752' if self.hover or self.active else '#63563b')
        for x in (8,w-8):self.create_oval(x-2,h/2-2,x+2,h/2+2,fill=GOLD,outline='')
        self.create_text(w/2,h/2,text=self.label,fill=GREEN if self.active else (BONE if self.enabled else '#77705c'),font=('Georgia',10,'bold'))

class App:
    def __init__(self,root,visual=False):
        self.root=root;self.visual=visual;self.io=None if visual else WinIO()
        self.ctrl=Controller(lambda k,d:None) if visual else Controller(self.io.output)
        self.target=0;self.region=(.25,.2,.65,.6);self.mode='Auto';self.generation=0
        self.jobs=queue.Queue(maxsize=1);self.results=queue.Queue();self.busy=False;self.ready=False
        self.previous_hot=False;self.previous_reacquire=False;self.last_scan=0;self.scan_ms=0;self.history=deque(maxlen=90)
        self.proc=psutil.Process();self.proc.cpu_percent();self.thumb=None;self.selecting=False;self.last_focused=True
        self.run='Preview';self.last_run='Preview';self.reads=deque(maxlen=5);self.last_read=None;self.scout=None
        self.meter=ReactionMeter();self.bench=None;self.benchproc=psutil.Process();self.optboxes={};self.geo=deque(maxlen=40);self.pending_clear=False;self.capture_backend='mss';self.engine='CPU'
        # No heavy imports in the UI thread: GPU support is reported by the worker once loaded.
        self.gpu_ok=False   # the worker reports DirectML availability after loading onnxruntime
        self.dxgi_ok=dxgi_available()
        self.stage='starting';self.stage_since=time.monotonic();self.load_started=time.monotonic()
        root.title(f'Orcish Dragonwilds Helper {VERSION} | {PROFILE.name} | Ashenfall command post');root.configure(bg=BG);root.attributes('-topmost',True)
        root.minsize(900,560)
        self.folder=ensure_data()   # user data: <root>/data (settings, learned data, notes, log)
        self.settings=Settings(self.folder/'settings.json',PROFILE.name);self.save_job=None
        saved_region=self.settings.get('capture_region')
        if isinstance(saved_region,list) and len(saved_region)==4 and all(isinstance(n,(int,float)) for n in saved_region):self.region=tuple(saved_region)
        # "Zero point": if the previous start never reached a ready engine, or was forced with
        # ORC_SAFE=1 (Setup.cmd → 4), start clean: default window, no learned data, no speed options.
        self.safe=os.environ.get('ORC_SAFE')=='1' or self.settings.get('engine_ok') is False
        if self.safe:
            for k in ('geometry','zoomed'):self.settings.data.pop(k,None)
        self.unclean=self.settings.get('clean_exit') is False
        self.settings.set('engine_ok',False);self.settings.set('clean_exit',False);self.settings.save()
        log.info('start %s safe=%s unclean_previous_exit=%s',VERSION,self.safe,self.unclean)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.build();self.place_window()
        root.report_callback_exception=self.error
        self.thread=None
        if not visual:self.thread=threading.Thread(target=self.worker,daemon=True);self.thread.start()
        else:
            self.status.set('PREVIEW — UI demonstration; no input sent')
            self.timetext.set('Collect E  142 ms · 2 scans @ 4 ms · memory\nAvg 6: 188 ms · best 142 · worst 311')
            for l,s in [('none · Stone | Collect',0),('Collect → TAP E  (97%)',1),('Excluded: Collect E ("stone")',0),('Harvest → HOLD F  (94%)',1)]:self.log_read(l,s)
        if self.io and self.unclean:self.io.release_all()   # a crash may have left a button down
        if self.safe:self.status.set('SAFE START — defaults, learned data not loaded. Normal start next time.')
        root.after(25,self.tick);root.after(1000,self.metrics)
    def text(self,parent,text,size=10,color=BONE):
        return tk.Label(parent,text=text,bg=parent['bg'],fg=color,font=('Segoe UI',size),anchor='w')
    def build(self):
        header=tk.Canvas(self.root,height=82,bg=BG,highlightthickness=0);header.pack(fill='x',padx=20,pady=(10,0))
        header.create_polygon(6,70,20,13,34,48,48,8,62,48,76,13,90,70,fill='#405831',outline=GOLD,width=2)
        header.create_text(110,32,text='ORCISH HELPER',anchor='w',fill=BONE,font=('Georgia',25,'bold'))
        header.create_text(112,62,text='DRAGONWILDS  /  ASHENFALL COMMAND POST',anchor='w',fill=GREEN,font=('Segoe UI',10,'bold'))
        # Original tusk-and-iron ornament, drawn locally (no game assets).
        for cx,flip in [(710,1),(815,-1)]:
            header.create_polygon(cx,65,cx+flip*8,26,cx+flip*22,8,cx+flip*14,39,cx+flip*15,65,fill=BONE,outline=GOLD)
        header.create_polygon(743,20,782,20,797,37,788,67,762,76,736,59,731,36,fill='#455536',outline=GOLD,width=2)
        header.create_polygon(741,38,757,43,751,48,fill='#cc5933')
        header.create_polygon(785,38,769,43,775,48,fill='#cc5933')
        header.create_line(751,59,775,59,fill='#11160f',width=4)
        header.create_line(0,80,4000,80,fill=GOLD,width=2)
        modes=tk.Frame(self.root,bg=BG);modes.pack(fill='x',padx=24,pady=12)
        self.modebuttons={}
        for mode,title in [('Repeat','REPEAT'),('Hold','HOLD'),('Auto','AUTO PRESSER'),('Fishing','FISHING · EXP'),('Stats','STATS')]:
            b=RuneButton(modes,title,lambda m=mode:self.choose_mode(m),170,48);b.pack(side='left',padx=(0,9));self.modebuttons[mode]=b
        self.modebuttons['Auto'].active=True;self.modebuttons['Auto'].draw()
        body=tk.Frame(self.root,bg=BG);body.pack(fill='both',expand=True,padx=24)
        settings=tk.Frame(body,bg=PANEL);settings.pack(side='left',fill='both',expand=True,padx=(0,12))
        scroll=tk.Scrollbar(settings,orient='vertical');scroll.pack(side='right',fill='y')
        settings_canvas=tk.Canvas(settings,bg=PANEL,highlightthickness=0,width=400,yscrollcommand=scroll.set)
        settings_canvas.pack(side='left',fill='both',expand=True);scroll.configure(command=settings_canvas.yview)
        inner=tk.Frame(settings_canvas,bg=PANEL,padx=14,pady=12)
        settings_window=settings_canvas.create_window(0,0,window=inner,anchor='nw')
        self.cols=(tk.Frame(inner,bg=PANEL),tk.Frame(inner,bg=PANEL));self.inner=inner;self.twocol=None
        self.scrollbar=scroll;self.settings_canvas=settings_canvas;self.settings_window=settings_window
        inner.bind('<Configure>',lambda e:self.fit_settings())
        settings_canvas.bind('<Configure>',lambda e:self.fit_settings())
        settings_canvas.bind_all('<MouseWheel>',self.wheel,add='+')
        left=self.cols[0]
        right=tk.Frame(body,bg=PANEL,padx=14,pady=12,width=370);right.pack(side='right',fill='both');right.pack_propagate(False)
        self.vis={}      # widget -> modes where it is shown (or a callable(mode)->bool); others always shown
        def show(w,modes):self.vis[w]=modes;return w
        MAN=('Repeat','Hold','Auto')
        show(self.text(left,'01  /  ORDERS',12,GOLD),MAN).pack(fill='x')
        self.key=tk.StringVar(value=self.settings.get('key','LMB'));self.interval=tk.StringVar(value=str(self.settings.get('interval_ms',100)));self.duration=tk.StringVar(value=str(self.settings.get('duration_ms',50)))
        self.timed=tk.BooleanVar(value=bool(self.settings.get('timed',False)))
        ttk.Style(self.root).theme_use('clam')
        ttk.Style(self.root).configure('Orc.TCombobox',fieldbackground='#12170f',background=PANEL,foreground=BONE,arrowcolor=GOLD,bordercolor='#4c5035')
        row=show(tk.Frame(left,bg=PANEL),('Repeat','Hold'));row.pack(fill='x',pady=4)
        self.text(row,'Key · pick or type').pack(side='left')
        self.keybox=ttk.Combobox(row,textvariable=self.key,values=keymap.dropdown(),width=14,style='Orc.TCombobox',font=('Segoe UI',11))
        self.keybox.pack(side='right')
        self.key.trace_add('write',lambda *_:(self.stop('Key changed'),self.persist('key',self.key.get())))
        tb=show(tk.Checkbutton(left,text='Timed hold · release after Hold duration',variable=self.timed,
            command=lambda:(self.stop('Hold type changed'),self.persist('timed',self.timed.get()),self.apply_visibility()),
            bg=PANEL,fg=GREEN,selectcolor='#15200e',activebackground=PANEL,activeforeground=GREEN,anchor='w',font=('Segoe UI',9)),('Hold',))
        tb.pack(fill='x',pady=(2,2))
        self.fieldlabels={}
        for name,title,var,vmodes in [('interval','Repeat interval · ms',self.interval,('Repeat','Auto')),
                                     ('duration','Hold duration · ms',self.duration,lambda m:m in ('Repeat','Auto') or (m=='Hold' and self.timed.get()))]:
            row=show(tk.Frame(left,bg=PANEL),vmodes);row.pack(fill='x',pady=4)
            self.fieldlabels[name]=self.text(row,title);self.fieldlabels[name].pack(side='left')
            tk.Entry(row,textvariable=var,width=12,bg='#12170f',fg=BONE,insertbackground=GREEN,relief='flat',font=('Segoe UI',11)).pack(side='right')
            setting_key='interval_ms' if name=='interval' else 'duration_ms'
            var.trace_add('write',lambda *_,v=var,k=setting_key:(self.stop('Settings changed'),self.persist(k,v.get())))
        self.repeat=tk.BooleanVar(value=bool(self.settings.get('repeat_prompts',False)))
        self.repeatbox=show(tk.Checkbutton(left,text='Repeat persistent tap prompts (uses interval + tap length above)',variable=self.repeat,command=lambda:(self.stop('Options changed'),self.persist('repeat_prompts',self.repeat.get())),bg=PANEL,fg=GREEN,selectcolor='#15200e',activebackground=PANEL,activeforeground=GREEN,disabledforeground='#737765',anchor='w',font=('Segoe UI',9)),('Auto',))
        self.repeatbox.pack(fill='x',pady=(2,0))
        show(self.text(left,'Allowed actions · priority from top to bottom',10,GOLD),('Auto',)).pack(fill='x',pady=(12,4))
        self.allowed={};saved_allowed=self.settings.get('allowed_actions',{})
        if not isinstance(saved_allowed,dict):saved_allowed={}
        for name in getattr(PROFILE,'ui_order',PROFILE.action_names):
            default=name in PROFILE.default_allowed and name not in PROFILE.opt_in
            v=tk.BooleanVar(value=bool(saved_allowed.get(name,default)));self.allowed[name]=v
            show(tk.Checkbutton(left,text=name+(' (opt in)' if name in PROFILE.opt_in else ''),variable=v,command=lambda n=name,v=v:(self.stop('Action selection changed'),self.persist('allowed_actions',{k:x.get() for k,x in self.allowed.items()})),bg=PANEL,fg=BONE,selectcolor='#15200e',activebackground=PANEL,activeforeground=GREEN,font=('Segoe UI',10),anchor='w'),('Auto',)).pack(fill='x')
        show(self.text(left,'Exclude · comma separated, e.g. Stone,Cabbage',10,GOLD),('Auto',)).pack(fill='x',pady=(10,2))
        self.exclude=tk.StringVar(value=self.settings.get('exclude',''))
        ex=show(tk.Entry(left,textvariable=self.exclude,bg='#12170f',fg=BONE,insertbackground=GREEN,relief='flat',font=('Segoe UI',11)),('Auto',));ex.pack(fill='x')
        for k in ('<Return>','<Escape>','<KP_Enter>'):ex.bind(k,lambda e:self.root.focus_set())
        self.exclude.trace_add('write',lambda *_:(self.stop('Exclusions changed'),self.persist('exclude',self.exclude.get())))
        self.build_fishing(left,show)
        self.build_stats_controls(left,show)
        left=self.cols[1]
        show(self.text(left,'02  /  TARGET & CAPTURE',12,GOLD),MAN).pack(fill='x',pady=(0,5))
        row=show(tk.Frame(left,bg=PANEL),MAN);row.pack(fill='x');self.bindrow=row
        RuneButton(row,'BIND GAME · 3s',self.bind_game,177,38).pack(side='left')
        show(RuneButton(row,'SELECT REGION',self.select_region,177,38),('Auto',)).pack(side='right')
        self.targettext=tk.StringVar(value='Bind game, then select the prompt area.')
        show(tk.Label(left,textvariable=self.targettext,bg=PANEL,fg=MUTED,wraplength=360,justify='left',anchor='w',font=('Segoe UI',9)),MAN).pack(fill='x',pady=6)
        self.text(left,'Unfocused opacity · 0 = minimize on focus loss',10,GOLD).pack(fill='x',pady=(4,0))
        self.opacity=tk.IntVar(value=int(self.settings.get('opacity',60)))
        tk.Scale(left,from_=0,to=100,orient='horizontal',variable=self.opacity,command=lambda *_:self.persist('opacity',self.opacity.get()),bg=PANEL,fg=BONE,troughcolor='#10150e',highlightthickness=0,activebackground=GREEN).pack(fill='x')
        before=set(left.pack_slaves());self.build_speed(left)
        for w in left.pack_slaves():
            if w not in before:self.vis[w]=('Auto',)
        self.build_stats_charts(left,show)
        before=set(right.pack_slaves())
        self.text(right,'04  /  SCOUT VISION',12,GOLD).pack(fill='x')
        self.previewbox=tk.Label(right,text='Capture preview appears here\nGold = keycap · Green = OCR\nBlue = learned · Red = excluded',bg='#10150e',fg=MUTED,width=42,height=7,font=('Segoe UI',10));self.previewbox.pack(fill='x',pady=8)
        self.detected=tk.StringVar(value='Loading local recognition engine…')
        tk.Label(right,textvariable=self.detected,bg=PANEL,fg=GREEN,wraplength=330,justify='left',anchor='w',font=('Segoe UI',11,'bold'),height=2).pack(fill='x')
        self.raw=tk.StringVar(value='Only English prompts with a visible keycap are eligible.')
        tk.Label(right,textvariable=self.raw,bg=PANEL,fg=MUTED,wraplength=330,justify='left',anchor='nw',height=2,font=('Segoe UI',9)).pack(fill='x')
        self.text(right,'Last 5 reads · newest first · ▶ = key sent',9,GOLD).pack(fill='x',pady=(6,0))
        self.readtext=tk.StringVar(value='—')
        tk.Label(right,textvariable=self.readtext,bg='#10150e',fg=BONE,justify='left',anchor='nw',height=5,font=('Consolas',9)).pack(fill='x')
        self.text(right,'Action timing · first seen → key sent',9,GOLD).pack(fill='x',pady=(6,0))
        self.timetext=tk.StringVar(value='No action yet')
        tk.Label(right,textvariable=self.timetext,bg='#10150e',fg=GREEN,justify='left',anchor='nw',height=2,font=('Consolas',9)).pack(fill='x')
        for w in right.pack_slaves():
            if w not in before:self.vis[w]=('Auto',)
        show(self.text(right,'04  /  OUTPUT',12,GOLD),('Repeat','Hold')).pack(fill='x')
        self.outtext=tk.StringVar(value='Idle')
        self.outlabel=show(tk.Label(right,textvariable=self.outtext,bg='#10150e',fg=GREEN,justify='left',anchor='nw',height=4,wraplength=330,font=('Consolas',11)),('Repeat','Hold'))
        self.outlabel.pack(fill='x',pady=6)
        show(self.text(right,'04  /  FISHING BOT',12,GOLD),('Fishing',)).pack(fill='x')
        self.modehelp=tk.StringVar()
        show(tk.Label(right,textvariable=self.modehelp,bg=PANEL,fg=MUTED,justify='left',anchor='nw',wraplength=330,font=('Segoe UI',9)),('Repeat','Hold','Fishing')).pack(fill='x',pady=(4,0))
        self.build_stats_sets(right,show)
        self.text(right,'05  /  RESOURCE CONSUMPTION',12,GOLD).pack(fill='x',pady=(12,4))
        self.metrictext=tk.StringVar(value='Measuring this app: CPU, RAM, scan time')
        tk.Label(right,textvariable=self.metrictext,bg=PANEL,fg=BONE,justify='left',anchor='w',font=('Consolas',10)).pack(fill='x')
        self.chart=tk.Canvas(right,height=90,bg='#10150e',highlightthickness=1,highlightbackground='#4c5035');self.chart.pack(fill='x',pady=6)
        self.text(right,'CPU %  /  RAM MiB · separate scales · last 90 s',8,MUTED).pack(fill='x')
        footer=tk.Frame(self.root,bg=BG);footer.pack(fill='x',padx=24,pady=12)
        self.runbuttons={}
        for run in ('Preview','Live'):
            b=RuneButton(footer,run.upper(),lambda r=run:self.launch(r),150,48);b.pack(side='left',padx=(0,9));self.runbuttons[run]=b
        self.status=tk.StringVar(value='STOPPED — PREVIEW detects only, LIVE presses keys')
        tk.Label(footer,textvariable=self.status,bg=BG,fg=GREEN,anchor='w',wraplength=520,font=('Segoe UI',10,'bold')).pack(side='left',padx=16)
        self.hint=tk.StringVar();self.hintlabel=tk.Label(self.root,textvariable=self.hint,bg=BG,fg=MUTED,font=('Segoe UI',9));self.hintlabel.pack(pady=(0,10))
        self.chrome=(header,modes,footer,self.hintlabel);self.rightpanel=right;self.layout(True);self.apply_visibility()
        self.update_mode_fields()
        # Clicking anywhere that is not a text field takes keyboard focus off the entries ("click-off").
        self.root.bind_all('<Button-1>',self.defocus,add='+')
    COLW=440   # settings column width (px)
    def layout(self,two):
        """Settings in two columns when there is room (wide / maximized window), else stacked."""
        if two==self.twocol:return
        self.twocol=two;a,b=self.cols
        for c in self.cols:c.grid_forget()
        if two:
            a.grid(row=0,column=0,sticky='new',padx=(0,18));b.grid(row=0,column=1,sticky='new')
            self.inner.columnconfigure(0,weight=1,uniform='c');self.inner.columnconfigure(1,weight=1,uniform='c')
        else:
            a.grid(row=0,column=0,sticky='new');b.grid(row=1,column=0,sticky='new',pady=(14,0))
            self.inner.columnconfigure(0,weight=1,uniform='');self.inner.columnconfigure(1,weight=0,uniform='')
    def fit_settings(self):
        """Pick column layout by available width; show the scrollbar only when content is taller than the view."""
        c=self.settings_canvas;w=c.winfo_width()
        if w>1 and not getattr(self,'measuring',False):self.layout(w>=2*self.COLW-40 if not self.twocol else w>=2*self.COLW-80)   # hysteresis
        c.itemconfigure(self.settings_window,width=max(1,w))
        c.configure(scrollregion=(0,0,w,self.inner.winfo_reqheight()))
        need=self.inner.winfo_reqheight()>c.winfo_height()+1
        shown=bool(self.scrollbar.winfo_ismapped())
        if need and not shown:self.scrollbar.pack(side='right',fill='y',before=c)
        elif not need and shown:self.scrollbar.pack_forget();c.yview_moveto(0)
    def wheel(self,e):
        if self.scrollbar.winfo_ismapped() and str(e.widget).startswith(str(self.settings_canvas)):
            self.settings_canvas.yview_scroll(int(-e.delta/120),'units')
    def natural_size(self):
        """Window size that shows every option without scrolling (two-column settings)."""
        self.measuring=True;self.layout(True)
        try:
            for _ in range(3):self.root.update_idletasks()   # grid/wrap settle over a few passes
        finally:self.measuring=False
        chrome=sum(w.winfo_reqheight() for w in self.chrome)+10+24+24+10
        right=sum(ch.winfo_reqheight() for ch in self.rightpanel.winfo_children())+60
        h=chrome+max(self.inner.winfo_reqheight(),right)+4
        w=24+self.inner.winfo_reqwidth()+12+370+24+4
        return max(w,2*self.COLW+450),h
    def work_area(self):
        """(left, top, right, bottom) of the usable desktop (taskbar excluded)."""
        if sys.platform=='win32':
            from ctypes import wintypes
            r=wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x30,0,ctypes.byref(r),0):return r.left,r.top,r.right,r.bottom
        return 0,0,self.root.winfo_screenwidth(),self.root.winfo_screenheight()-60
    def on_screen(self,x,y):
        if sys.platform!='win32':
            return 0<=x<self.root.winfo_screenwidth() and 0<=y<self.root.winfo_screenheight()
        from ctypes import wintypes
        return bool(ctypes.windll.user32.MonitorFromPoint(wintypes.POINT(x,y),0))   # 0 = NULL if off-screen
    def place_window(self):
        """Restore last size/position (if still on a connected monitor), else fit all options on screen."""
        g=self.settings.get('geometry');import re as _re
        m=_re.fullmatch(r'(\d+)x(\d+)([+-]\d+)([+-]\d+)',g or '')
        if m and int(m[1])>=300 and int(m[2])>=200 and self.on_screen(int(m[3])+40,int(m[4])+15):self.root.geometry(g)
        else:
            L,T,R,B=self.work_area();w,h=self.natural_size()
            w,h=min(w,R-L),min(h,B-T-32)               # 32 ≈ title bar
            g=f'{w}x{h}+{max(L,R-w-8)}+{T}'                    # right edge: keeps the screen centre (prompts) free
            self.root.geometry(g)
        if self.settings.get('zoomed'):
            try:self.root.state('zoomed')
            except tk.TclError:pass
        self.normal_geometry=g
        self.root.bind('<Configure>',self.track_window,add='+')
    def track_window(self,e):
        if e.widget is not self.root:return
        st=self.root.state()
        if st=='normal' and self.root.winfo_width()>=300:self.normal_geometry=self.root.geometry();self.win_zoomed=False
        elif st=='zoomed':self.win_zoomed=True
    def save_window(self):
        self.settings.set('geometry',getattr(self,'normal_geometry',None) or self.root.geometry())
        self.settings.set('zoomed',bool(getattr(self,'win_zoomed',False)))
    def defocus(self,e):
        w=e.widget
        if isinstance(w,tk.Misc) and not isinstance(w,tk.Entry) and w.winfo_toplevel() is self.root:self.root.focus_set()
    def draw_run(self):
        for r,b in self.runbuttons.items():
            b.active=self.ctrl.running and self.run==r
            b.enabled=self.mode!='Stats' and (r=='Live' or self.mode in ('Auto','Fishing'))
            b.label=('■ STOP ' if b.active else '')+r.upper();b.draw()
        run='TEST' if self.mode=='Stats' else ('LIVE' if self.mode not in ('Auto','Fishing') else self.last_run.upper())
        self.hint.set(f'\\  START / STOP {run}     •     F8  RELEASE & STOP     •     Switching windows stops output')
    def persist(self,key,value):
        """Remember a setting across restarts; writes are batched 400 ms after the last change."""
        self.settings.set(key,value)
        if self.save_job:self.root.after_cancel(self.save_job)
        self.save_job=self.root.after(400,self.settings.save)
    def check(self,parent,text,var,enabled=True,note=''):
        b=tk.Checkbutton(parent,text=text+(note if not enabled else ''),variable=var,command=lambda:(self.stop('Speed options changed'),self.persist('speed_options',{k:v.get() for k,v in self.opt.items()})),bg=PANEL,fg=BONE,selectcolor='#15200e',activebackground=PANEL,activeforeground=GREEN,disabledforeground='#737765',anchor='w',font=('Segoe UI',9),state='normal' if enabled else 'disabled')
        b.pack(fill='x');b.basetext=b.cget('text');return b
    def build_speed(self,left):
        self.text(left,'03  /  SPEED & LEARNING',12,GOLD).pack(fill='x',pady=(12,4))
        saved_opts={} if self.safe else self.settings.get('speed_options',{})
        if not isinstance(saved_opts,dict):saved_opts={}
        self.opt={k:tk.BooleanVar(value=bool(saved_opts.get(k,False))) for k in ('fast_det','rec_only','memory','templates','single','dxgi','gpu')}
        self.optboxes['fast_det']=self.check(left,'Fast detection · native-size text finding (extra, ~2× faster OCR)',self.opt['fast_det'])
        self.optboxes['rec_only']=self.check(left,'Recognition only · skip text finding when no exclusions',self.opt['rec_only'])
        self.optboxes['memory']=self.check(left,'Learned memory · skip OCR for prompts seen before',self.opt['memory'])
        self.optboxes['templates']=self.check(left,'Templates · learned words + key letters (no exclusions)',self.opt['templates'])
        self.optboxes['single']=self.check(left,'Single-scan confirm · faster, less safe',self.opt['single'])
        self.optboxes['dxgi']=self.check(left,'DXGI capture',self.opt['dxgi'],self.dxgi_ok,'  (dxcam missing: Setup.cmd → 1)')
        self.gpucheck=self.optboxes['gpu']=self.check(left,'GPU · DirectML',self.opt['gpu'],self.gpu_ok,'  (Setup.cmd → 2 first)')
        row=tk.Frame(left,bg=PANEL);row.pack(fill='x',pady=(6,0))
        self.text(row,'Learned data limit · MB').pack(side='left')
        self.limit=tk.StringVar(value=str(self.settings.get('learned_limit_mb','4')))
        tk.Entry(row,textvariable=self.limit,width=6,bg='#12170f',fg=BONE,insertbackground=GREEN,relief='flat',font=('Segoe UI',11)).pack(side='right')
        self.limit.trace_add('write',lambda *_:(self.stop('Learned data limit changed'),self.persist('learned_limit_mb',self.limit.get())))
        row=tk.Frame(left,bg=PANEL);row.pack(fill='x',pady=4)
        self.learntext=tk.StringVar(value='Learned: —')
        tk.Label(row,textvariable=self.learntext,bg=PANEL,fg=MUTED,anchor='w',font=('Segoe UI',9)).pack(side='left')
        RuneButton(row,'CLEAR LEARNED',self.clear_learned,165,32).pack(side='right')
        self.text(left,'Text span · keycap widths left of the keycap',10,GOLD).pack(fill='x',pady=(6,0))
        self.span=tk.IntVar(value=int(self.settings.get('text_span',SPAN)))
        tk.Scale(left,from_=4,to=30,orient='horizontal',variable=self.span,command=lambda *_:(self.stop('Text span changed'),self.persist('text_span',self.span.get())),bg=PANEL,fg=BONE,troughcolor='#10150e',highlightthickness=0,activebackground=GREEN).pack(fill='x')
        row=tk.Frame(left,bg=PANEL);row.pack(fill='x',pady=(2,8))
        RuneButton(row,'SUGGEST CROP',self.suggest_crop,177,38).pack(side='left')
        self.croptext=tk.StringVar(value='Scan a few prompts in PREVIEW first.')
        tk.Label(row,textvariable=self.croptext,bg=PANEL,fg=MUTED,wraplength=170,justify='left',anchor='w',font=('Segoe UI',8)).pack(side='left',padx=8)
    def opts(self):
        o={k:v.get() for k,v in self.opt.items()}
        if getattr(self,'bench',None):o.update(self.bench.config['opts'])   # the configuration under test
        o['gpu']=o['gpu'] and self.gpu_ok;o['dxgi']=o['dxgi'] and self.dxgi_ok;o['span']=float(self.span.get())
        try:o['limit']=min(256.,max(.25,float(self.limit.get())))
        except ValueError:o['limit']=4.
        return o
    def clear_learned(self):
        self.stop('Clearing learned data…');self.pending_clear=True
    def observe_geo(self,info,rect):
        """Store where prompts were seen, in game-client pixels, for the crop advisor."""
        x,y,w,h=self.io.rect(self.target);ox,oy=rect['left']-x,rect['top']-y
        for (cx,cy,cw,ch),left in info.get('geo',[]):self.geo.append((cx+ox,cy+oy,cw,ch,left+ox,w,h))
    def suggest_crop(self):
        if not self.target or self.visual:self.status.set('Bind the game first.');return
        if len(self.geo)<3:self.status.set(f'Need 3+ recognized prompts for a suggestion ({len(self.geo)} so far). Run PREVIEW over a few.');return
        W,H=self.geo[-1][5],self.geo[-1][6]
        above=4.5 if exclusions(self.exclude.get()) else 1.5
        l=min(g[4]-.5*g[3] for g in self.geo);r=max(g[0]+2*g[2] for g in self.geo)
        t=min(g[1]-above*g[3] for g in self.geo);b=max(g[1]+2.5*g[3] for g in self.geo)
        l,t,r,b=max(0,l),max(0,t),min(W,r),min(H,b)
        span=max((g[0]-g[4])/g[2] for g in self.geo)*1.2+1
        self.span.set(int(min(30,max(4,round(span)))))
        self.croptext.set(f'From {len(self.geo)} prompts: text span {self.span.get()}×. Adjust the box, ENTER applies.')
        self.select_region(suggested=(l/W,t/H,(r-l)/W,(b-t)/H))
    MODEHELP={'Repeat':'Presses the key again and again: each press lasts "Press length", a new press starts every "Repeat interval". Start with LIVE or \\ in the game.',
              'Hold':'Holds the key down. Timed ticked: releases after "Hold duration" and stops. Unticked: holds until you stop (\\, F8, or switching windows).',
              'Stats':'',
              'Fishing':'Bot 101: BAR + REEL region, manual cast/movement. F7 = New spot / Reacquire, F8 = emergency release. Advanced mode is staged and never requires an online LLM.'}
    # ---------------------------------------------------------------- STATS tab: automated tests
    METRICS=(('scan_ms','Scan time · ms',False),('detect_pct','Detection %',True),('agree_pct','Agreement with baseline %',True),
             ('confirm_ms','Time to decision · ms',False),('changes_per_min','Label changes / min (camera · info only)',None),('cpu_pct','CPU % (this app)',False))
    def build_stats_controls(self,left,show):
        S=('Stats',)
        show(self.text(left,'01  /  AUTOMATED TEST',12,GOLD),S).pack(fill='x')
        show(tk.Label(left,text='1. AUTO tab: bind the game, select the region.\n'
            '2. Stand still in the water facing a prompt, e.g. Collect Water.\n'
            '3. RUN TEST (or \\ in the game), then click into the game and let go of mouse and keyboard.\n'
            'RUN TEST ticks off every speed option in section 03 itself and tests the whole set: Baseline, each option '
            'alone, then all of them together. Each configuration runs a STATIC phase (default 5 s), then a CAMERA phase '
            '(default 5 s): the app sweeps the camera left/right the same way every time and brings it back. PREVIEW '
            'only: no keys are sent. F8 or leaving the game aborts.',
            bg=PANEL,fg=MUTED,justify='left',anchor='w',wraplength=410,font=('Segoe UI',9)),S).pack(fill='x',pady=(2,6))
        self.bphase=tk.IntVar(value=int(self.settings.get('bench_phase',5)));self.bamp=tk.IntVar(value=int(self.settings.get('bench_amp',250)))
        self.bperiod=tk.IntVar(value=int(self.settings.get('bench_period',4)))
        for title,var,lo,hi,key in (('Seconds per phase',self.bphase,5,60,'bench_phase'),('Camera sweep · px each side',self.bamp,40,1200,'bench_amp'),
                                    ('Camera sweep period · s',self.bperiod,2,10,'bench_period')):
            show(self.text(left,title,9,GOLD),S).pack(fill='x')
            show(tk.Scale(left,from_=lo,to=hi,orient='horizontal',variable=var,command=lambda v,k=key,var=var:(self.persist(k,var.get()),self.update_plan()),
                bg=PANEL,fg=BONE,troughcolor='#10150e',highlightthickness=0,activebackground=GREEN),S).pack(fill='x')
        self.plantext=tk.StringVar()
        show(tk.Label(left,textvariable=self.plantext,bg='#10150e',fg=BONE,justify='left',anchor='nw',wraplength=410,font=('Consolas',9)),S).pack(fill='x',pady=6)
        row=show(tk.Frame(left,bg=PANEL),S);row.pack(fill='x')
        RuneButton(row,'RUN TEST',self.start_bench,150,40).pack(side='left')
        RuneButton(row,'STOP',lambda:self.stop('Test stopped'),110,40).pack(side='left',padx=8)
        self.benchtext=tk.StringVar(value='No test running.')
        show(tk.Label(left,textvariable=self.benchtext,bg=PANEL,fg=GREEN,justify='left',anchor='w',wraplength=410,font=('Segoe UI',9,'bold')),S).pack(fill='x',pady=6)
        show(self.text(left,'Results table',9,GOLD),S).pack(fill='x')
        self.tabletext=tk.StringVar(value='—')
        show(tk.Label(left,textvariable=self.tabletext,bg='#10150e',fg=BONE,justify='left',anchor='nw',font=('Consolas',8)),S).pack(fill='x')
    def build_stats_charts(self,left,show):
        S=('Stats',)
        show(self.text(left,'02  /  CHARTS · static (solid) vs camera (outlined)',12,GOLD),S).pack(fill='x',pady=(0,4))
        self.benchcanvas=show(tk.Canvas(left,height=560,bg='#10150e',highlightthickness=1,highlightbackground='#4c5035'),S)
        self.benchcanvas.pack(fill='x');self.benchcanvas.bind('<Configure>',lambda e:self.draw_charts())
        show(tk.Label(left,text='Colours compare each bar with Baseline in the same phase: green = better by more than 10 %, '
            'red = worse by more than 10 %, gold = Baseline, grey = about the same (or info only). ★ / ✕ in AUTO → 03 mark suggested / worse options.',bg=PANEL,fg=MUTED,justify='left',anchor='w',
            wraplength=410,font=('Segoe UI',8)),S).pack(fill='x',pady=4)
    def build_stats_sets(self,right,show):
        S=('Stats',)
        show(self.text(right,'04  /  DATA SETS',12,GOLD),S).pack(fill='x')
        self.runlist=show(tk.Listbox(right,height=6,bg='#10150e',fg=BONE,selectbackground='#384829',relief='flat',font=('Consolas',9),exportselection=False),S)
        self.runlist.pack(fill='x',pady=4);self.runlist.bind('<<ListboxSelect>>',lambda e:self.select_run())
        self.rectext=tk.StringVar(value='Run a test to get suggestions.')
        show(tk.Label(right,textvariable=self.rectext,bg=PANEL,fg=BONE,justify='left',anchor='nw',wraplength=330,font=('Segoe UI',9)),S).pack(fill='x')
        row=show(tk.Frame(right,bg=PANEL),S);row.pack(fill='x',pady=6)
        RuneButton(row,'APPLY SUGGESTED',self.apply_suggested,170,36).pack(side='left')
        self.runs=[];self.shown=None;self.suggestions={}
        self.root.after_idle(self.refresh_runs)
    def available_options(self):
        """Every speed option the test can use on this setup (GPU/DXGI only if actually available)."""
        return [k for k in benchmod.OPTION_LABELS if (k!='gpu' or self.gpu_ok) and (k!='dxgi' or self.dxgi_ok)]
    def update_plan(self):
        try:
            cfg=benchmod.plan(self.available_options());b=benchmod.Benchmark(cfg,self.bphase.get(),2.,self.bamp.get(),self.bperiod.get())
            codes=', '.join(c['name'] for c in cfg)
            self.plantext.set(f'Pending tests ({len(cfg)}): {codes}\n'
                              f'Each: static {b.phase_s:.0f} s + camera {b.camera_s:.0f} s + settle. '
                              f'Total pending time ≈ {benchmod.fmt_time(b.total_s())}')
        except Exception:log.exception('plan')
    def start_bench(self):
        if self.visual or self.bench:return
        if not self.target:self.status.set('Bind the game first (AUTO tab).');return
        if not self.io.game(self.target):self.status.set(f'The bound window is not {PROFILE.name}.');return
        if not self.ready:self.status.set('Recognition engine is not ready yet.');return
        available=self.available_options()
        for k in available:self.opt[k].set(True)   # RUN TEST ticks off every option it is about to cover
        self.stop('Starting test…')
        self.bench=benchmod.Benchmark(benchmod.plan(available),self.bphase.get(),2.,self.bamp.get(),self.bperiod.get())
        self.bench_config(0);self.armed=True;self.draw_run()
        self.benchtext.set('ARMED — click into the game; the test starts when it has focus.')
        self.status.set('TEST ARMED — switch to the game, then hands off')
        log.info('benchmark start: %s',[c['id'] for c in self.bench.configs])
    def bench_config(self,i):
        c=self.bench.configs[i];self.generation+=1          # drop scans of the previous configuration
        self.ctrl.start('Auto','E',.1,.05,True,False,1 if c['opts'].get('single') else 2)
    def bench_tick(self,now):
        b=self.bench
        dx=b.step(now,lambda:self.benchproc.cpu_percent()/max(1,psutil.cpu_count()))
        if dx:self.io.move(dx)
        for kind,val in b.events:
            if kind=='config' and val>0:self.bench_config(val)
        b.events.clear()
        if b.done:self.finish_bench();self.stop('TEST FINISHED — see the STATS tab');return
        self.benchtext.set(f'Running: {b.progress(now)} · {"settling" if b.settling else "measuring"} · {benchmod.fmt_time(b.remaining(now))} pending')
    def finish_bench(self):
        b,self.bench=self.bench,None
        if b is None:return
        res=b.results({'app':VERSION,'profile':PROFILE.name,'region':list(self.region)})
        if any('static' in c for c in res['configs']):
            f=benchmod.save(res,self.folder/'benchmarks');log.info('benchmark saved: %s',f.name)
            self.benchtext.set(('Aborted: '+b.aborted+' — partial results saved.') if b.aborted else f'Finished — saved {f.name}.')
        else:self.benchtext.set('Aborted before any measurement: '+(b.aborted or ''))
        self.refresh_runs()
    def refresh_runs(self):
        try:
            self.runs=benchmod.load_all(self.folder/'benchmarks');self.runlist.delete(0,'end')
            for f,r in self.runs:
                self.runlist.insert('end',f"{r['started'][5:16]}  {len(r['configs'])} cfg"+('  (partial)' if r.get('aborted') else ''))
            if self.runs:self.runlist.selection_clear(0,'end');self.runlist.selection_set(0);self.select_run()
            else:self.draw_charts()
            self.update_plan()
        except Exception:log.exception('refresh runs')
    def select_run(self):
        sel=self.runlist.curselection()
        if not sel or sel[0]>=len(self.runs):return
        self.shown=self.runs[sel[0]][1];self.draw_charts();self.fill_table()
        # suggestions always come from the newest complete run
        latest=next((r for _,r in self.runs if not r.get('aborted')),None)
        self.suggestions=benchmod.recommend(latest) if latest else {}
        self.show_suggestions()
    def fill_table(self):
        r=self.shown
        if not r:self.tabletext.set('—');return
        lines=[f"{r['started']}  ref: {r.get('reference') or 'none seen in Baseline static!'}",
               f"{'cfg':7} {'phase':6} {'scan':>6} {'p95':>6} {'det%':>5} {'agr%':>5} {'dec ms':>6} {'chg/m':>5} {'cpu%':>5} {'lrn%':>5}"]
        for c in r['configs']:
            for ph in benchmod.PHASES:
                m=c.get(ph)
                if not m:continue
                f=lambda k,w:(f"{m[k]:>{w}}" if m.get(k) is not None else ' '*(w-1)+'-')
                lines.append(f"{c.get('name',c['id'])[:7]:7} {ph:6} {f('scan_ms',6)} {f('scan_p95',6)} {f('detect_pct',5)} {f('agree_pct',5)} {f('confirm_ms',6)} {f('changes_per_min',5)} {f('cpu_pct',5)} {f('learned_pct',5)}")
        self.tabletext.set('\n'.join(lines))
    def draw_charts(self):
        c=getattr(self,'benchcanvas',None)
        if c is None:return
        c.delete('all');W=max(300,c.winfo_width());H=int(c.cget('height'));r=self.shown
        if not r or not r.get('configs'):
            c.create_text(W/2,H/2,text='No test data yet.\nRun a test to see charts here.',fill=MUTED,font=('Segoe UI',10));return
        cfgs=r['configs'];cols,rows=2,3;cw,ch=W/cols,H/rows
        base={ph:cfgs[0].get(ph,{}) for ph in benchmod.PHASES} if cfgs[0]['id']=='baseline' else {}
        for n,(key,title,higher) in enumerate(self.METRICS):
            x0,y0=(n%cols)*cw,(n//cols)*ch
            c.create_text(x0+8,y0+10,text=title,anchor='w',fill=GOLD,font=('Segoe UI',9,'bold'))
            vals=[(cf,ph,cf.get(ph,{}).get(key)) for cf in cfgs for ph in benchmod.PHASES]
            top=max([v for *_,v in vals if v is not None] or [1]) or 1
            gx,gy,gw,gh=x0+10,y0+26,cw-20,ch-52;slot=gw/max(1,len(cfgs));bw=min(22,slot/2-3)
            c.create_line(gx,gy+gh,gx+gw,gy+gh,fill='#4c5035')
            for i,cf in enumerate(cfgs):
                cx=gx+slot*i+slot/2
                c.create_text(cx,gy+gh+10,text=cf.get('name',cf['id']),fill=MUTED,font=('Segoe UI',7))
                for j,ph in enumerate(benchmod.PHASES):
                    v=cf.get(ph,{}).get(key)
                    if v is None:continue
                    bx=cx+(j-1)*(bw+2)+1;hgt=gh*v/top
                    col=self.bar_colour(cf['id'],v,base.get(ph,{}).get(key),higher)
                    if j==0:c.create_rectangle(bx,gy+gh-hgt,bx+bw,gy+gh,fill=col,outline=col)
                    else:c.create_rectangle(bx,gy+gh-hgt,bx+bw,gy+gh,fill='#10150e',outline=col,width=2)
                    c.create_text(bx+bw/2,gy+gh-hgt-6,text=f'{v:.0f}',fill=BONE,font=('Segoe UI',7))
    @staticmethod
    def bar_colour(cid,v,b,higher):
        if cid=='baseline':return GOLD
        if b in (None,0) or higher is None:return '#8b8f78'
        rel=(v-b)/abs(b);better=rel>.10 if higher else rel<-.10;worse=rel<-.10 if higher else rel>.10
        return GREEN if better else '#d0623f' if worse else '#8b8f78'
    def show_suggestions(self):
        rec=self.suggestions;lines=[]
        for k,box in self.optboxes.items():
            kind,why=rec.get(k,(None,''))
            if kind=='suggest':box.configure(text='★ '+box.basetext,fg=GREEN,font=('Segoe UI',9,'bold'))
            elif kind=='avoid':box.configure(text='✕ '+box.basetext,fg='#d0623f',font=('Segoe UI',9))
            else:box.configure(text=box.basetext,fg=BONE,font=('Segoe UI',9))
            if kind:lines.append(f"{'★' if kind=='suggest' else '✕' if kind=='avoid' else '·'} {benchmod.OPTION_LABELS[k]}: {kind} ({why})")
        latest=next((r for _,r in self.runs if not r.get('aborted')),None)
        if latest and not lines and not benchmod.baseline_ok(latest):
            self.rectext.set('No suggestions: Baseline saw no prompt in its static phase. Stand facing a prompt (e.g. in water) and run again.');return
        self.rectext.set('Suggestions from the newest complete test (highlighted in AUTO → 03):\n'+'\n'.join(lines) if lines else
                         'No suggestions yet: RUN TEST in the STATS tab.')
    def apply_suggested(self):
        if not self.suggestions:self.status.set('No suggestions yet — run a test first.');return
        for k,(kind,_) in self.suggestions.items():
            if kind=='suggest':self.opt[k].set(True)
            elif kind=='avoid':self.opt[k].set(False)
        self.persist('speed_options',{k:v.get() for k,v in self.opt.items()});self.stop('Suggested options applied in AUTO → 03');self.update_plan()
    def build_fishing(self,left,show):
        show(self.text(left,'01  /  FISHING · EXPERIMENTAL',12,GOLD),('Fishing',)).pack(fill='x')
        show(self.text(left,'Bot 101 + staged Advanced fishing · runtime guidance below',9,MUTED),('Fishing',)).pack(fill='x',pady=(2,4))
        from fishing_ui import FishingPanel
        controls=show(tk.Frame(left,bg=PANEL),('Fishing',));controls.pack(fill='x')
        self.fishing_panel=FishingPanel(self,controls)
        show(tk.Label(left,text='Runtime guidance appears above. Detailed instructions are in README.md and docs/FISHING.md.',bg=PANEL,fg=MUTED,justify='left',anchor='w',wraplength=410,font=('Segoe UI',9)),('Fishing',)).pack(fill='x',pady=(4,0))
    def visible(self,w):
        m=self.vis.get(w)
        return True if m is None else (m(self.mode) if callable(m) else self.mode in m)
    def apply_visibility(self):
        """Show only what matters for the current tab. Order is the original packing order."""
        if not hasattr(self,'packorder'):
            self.packorder=[(c,[(w,{k:v for k,v in w.pack_info().items() if k!='in'}) for w in c.pack_slaves()])
                            for c in (*self.cols,self.bindrow,self.rightpanel)]
        for c,items in self.packorder:
            for w,_ in items:w.pack_forget()
            for w,info in items:
                if self.visible(w):w.pack(**info)
        labels={'Repeat':('Repeat interval · ms','Press length · ms'),'Auto':('Repeat interval · ms','Tap length · ms'),'Hold':('','Hold duration · ms')}
        il,dl=labels.get(self.mode,('',''))
        if il:self.fieldlabels['interval'].configure(text=il)
        if dl:self.fieldlabels['duration'].configure(text=dl)
        self.modehelp.set(self.MODEHELP.get(self.mode,''))
        if hasattr(self,'settings_canvas'):self.root.after_idle(self.fit_settings)
    def update_mode_fields(self):
        if hasattr(self,'rightpanel'):self.apply_visibility()
        if getattr(self,'mode','')=='Stats' and hasattr(self,'plantext'):self.update_plan();self.root.after_idle(self.draw_charts)
        if hasattr(self,'hint'):self.draw_run()
    def choose_mode(self,m):
        self.stop('Mode changed');self.mode=m
        if getattr(self.ctrl,'mode','')=='Fishing' and m!='Fishing':self.ctrl=Controller(lambda k,d:None) if self.visual else Controller(self.io.output)
        for key,b in self.modebuttons.items():b.active=key==m;b.draw()
        self.update_mode_fields()
    def stop(self,reason='STOPPED'):
        if getattr(self,'bench',None) and not self.bench.done:
            back=self.bench.abort(reason)
            if back and self.io:self.io.move(back)
            self.finish_bench()
        self.ctrl.stop();self.generation+=1
        if getattr(self,'fishing_panel',None):self.fishing_panel.stop()
        self.scout_stop(reason)
        if hasattr(self,'status'):self.status.set(reason)
        if hasattr(self,'hint'):self.draw_run()
    def scout_start(self,domain,run):
        self.scout_stop('new session')
        try:
            pid=self.io.pid(self.target) if self.io and self.target else None
            meta={'helper_version':VERSION,'game_title':self.io.title(self.target)[:120] if self.io and self.target else '',
                  'capture_region':list(self.region),'mode':self.mode}
            self.scout=ScoutRecorder(self.folder,domain,run,pid,meta)
            self.scout.event('controller','session_start',run,details={'mode':self.mode},stream='controller')
        except Exception:
            self.scout=None;log.exception('Scout session start failed')
    def scout_event(self,*args,**kwargs):
        if self.scout:
            try:self.scout.event(*args,**kwargs)
            except Exception:log.exception('Scout event failed')
    def scout_stop(self,reason='stopped'):
        s=getattr(self,'scout',None);self.scout=None
        if s:
            try:s.close(reason)
            except Exception:log.exception('Scout session close failed')
    def bind_game(self):
        self.stop(f'Switch to {PROFILE.name} now… binding in 3 seconds')
        self.root.after(3000,self.finish_bind)
    def finish_bind(self):
        if self.visual:return
        h=self.io.foreground()
        if self.io.own(h):self.status.set('Switch to the game during the countdown.');return
        self.target=h;self.io.target=h
        self.targettext.set(self.io.title(h)[:70]+'\nSaved capture region loaded; use SELECT REGION to refine.')
        self.status.set('BOUND — choose region, then start in the game with \\')
        if self.mode=='Fishing' and getattr(self,'fishing_panel',None) and self.fishing_panel.show_overlay.get():self.fishing_panel.refresh_overlay()
    def select_region(self,suggested=None):
        """Region editor. Drag edges/corners to widen or narrow, drag inside to move, drag outside for a
        new box. ENTER or double-click applies, ESC cancels. With suggested, starts from the advisor's box."""
        if not self.target or self.visual:self.status.set('Bind the game first.');return
        self.stop('Adjust the capture box. ENTER applies, ESC cancels.')
        x,y,w,h=self.io.rect(self.target)
        if w<100 or h<100:self.status.set('Restore the game window before selecting.');return
        self.selecting=True
        overlay=tk.Toplevel(self.root);overlay.overrideredirect(True);overlay.geometry(f'{w}x{h}{x:+d}{y:+d}');overlay.attributes('-topmost',True);overlay.attributes('-alpha',.4)
        c=tk.Canvas(overlay,bg='#143510',cursor='crosshair',highlightthickness=0);c.pack(fill='both',expand=True)
        c.create_text(w/2,35,text='DRAG EDGES TO WIDEN / NARROW  •  DRAG INSIDE TO MOVE  •  DRAG OUTSIDE FOR NEW BOX  •  ENTER APPLY  •  ESC CANCEL',fill='white',font=('Segoe UI',13,'bold'))
        cur=self.region
        c.create_rectangle(cur[0]*w,cur[1]*h,(cur[0]+cur[2])*w,(cur[1]+cur[3])*h,outline='#b49758',dash=(4,4))
        src=suggested or cur
        box=[src[0]*w,src[1]*h,(src[0]+src[2])*w,(src[1]+src[3])*h]
        if suggested:c.create_text(w/2,62,text='SUGGESTED BOX FROM RECENT PROMPTS (green) · current region dashed gold',fill='#98c657',font=('Segoe UI',11,'bold'))
        state={'mode':None,'at':(0,0),'orig':list(box)};shape=[None]
        def draw():
            if shape[0]:c.delete(shape[0])
            shape[0]=c.create_rectangle(*box,outline='#98c657' if suggested else '#e9ce70',width=3)
            c.delete('size');c.create_text(box[0]+4,box[3]+14,text=f'{int(box[2]-box[0])} × {int(box[3]-box[1])} px',fill='white',anchor='w',tags='size')
        def close():self.selecting=False;overlay.destroy()
        def down(e):
            tol=10;l,t,r,b=box;edges=''
            if t-tol<e.y<b+tol:
                if abs(e.x-l)<tol:edges+='l'
                if abs(e.x-r)<tol:edges+='r'
            if l-tol<e.x<r+tol:
                if abs(e.y-t)<tol:edges+='t'
                if abs(e.y-b)<tol:edges+='b'
            inside=l<e.x<r and t<e.y<b
            state.update(mode=edges or ('move' if inside else 'new'),at=(e.x,e.y),orig=list(box))
            if state['mode']=='new':box[:]=[e.x,e.y,e.x,e.y]
        def move(e):
            m,(sx,sy),o=state['mode'],state['at'],state['orig'];dx,dy=e.x-sx,e.y-sy
            if m=='new':box[2],box[3]=e.x,e.y
            elif m=='move':box[:]=[o[0]+dx,o[1]+dy,o[2]+dx,o[3]+dy]
            elif m:
                if 'l' in m:box[0]=o[0]+dx
                if 'r' in m:box[2]=o[2]+dx
                if 't' in m:box[1]=o[1]+dy
                if 'b' in m:box[3]=o[3]+dy
            draw()
        def apply(e=None):
            l,r=sorted((max(0,min(w,box[0])),max(0,min(w,box[2]))));t,b=sorted((max(0,min(h,box[1])),max(0,min(h,box[3]))))
            if r-l>=100 and b-t>=40:
                self.region=(l/w,t/h,(r-l)/w,(b-t)/h);self.persist('capture_region',list(self.region));self.targettext.set(f'Capture region: {int(r-l)} × {int(b-t)} px. Tracks game window.');self.status.set('REGION SET — saved for next launch; keep the panel outside this area')
            else:self.status.set('Region too small (min 100 × 40 px); unchanged.')
            close()
        c.bind('<Button-1>',down);c.bind('<B1-Motion>',move);c.bind('<Double-Button-1>',apply)
        overlay.bind('<Return>',apply);overlay.bind('<KP_Enter>',apply);overlay.bind('<Escape>',lambda e:close());overlay.focus_force();draw()
    def launch(self,run):
        """PREVIEW/LIVE buttons: same button stops; the other one switches."""
        if self.ctrl.running:
            same=self.run==run;self.stop()
            if same:return
        if self.mode=='Fishing':self.fishing_panel.start(run);return
        if self.mode=='Stats':self.status.set('Use RUN TEST in the STATS tab (or \\ in the game).');return
        if run=='Preview' and self.mode!='Auto':self.status.set('PREVIEW applies to Auto Presser only — use LIVE.');return
        self.last_run=run;self.draw_run();self.start(run)
    def toggle(self):
        """Backslash hotkey: start/stop with the last used PREVIEW/LIVE choice."""
        if self.ctrl.running:self.stop();return
        if self.mode=='Fishing':self.fishing_panel.start(self.last_run);return
        if self.mode=='Stats':self.start_bench();return
        self.start('Live' if self.mode!='Auto' else self.last_run)
    def start(self,run):
        if self.mode=='Fishing':self.fishing_panel.start(run);return
        if self.visual:return
        if not self.target:self.status.set('Bind the game first.');return
        if self.mode=='Auto' and not self.io.game(self.target):self.status.set(f'Auto mode requires a {PROFILE.name} target.');return
        if self.mode=='Auto' and not self.ready:self.status.set('Recognition engine is not ready yet.');return
        try:
            key=keymap.canonical(self.key.get()) if self.mode!='Auto' else 'E';self.io.key(key)
            interval=float(self.interval.get())/1000 if self.mode in ('Repeat','Auto') else .1
            timed=self.mode=='Hold' and self.timed.get()
            hold=float(self.duration.get())/1000 if self.mode in ('Repeat','Auto') or timed else .05
            if not .01<=hold<=60 or not .01<=interval<=60:raise ValueError('Timings must be 10–60000 ms.')
            if self.mode in ('Repeat','Auto') and interval<hold+.01:raise ValueError('Interval must exceed hold by at least 10 ms.')
            if self.mode=='Auto' and not .02<=hold<=1:raise ValueError('Auto tap (hold duration) must be 20–1000 ms; prompts marked Hold are held separately.')
            if self.mode=='Auto' and interval<.05:raise ValueError('Auto interval must be at least 50 ms.')
        except ValueError as e:self.status.set(str(e));return
        self.generation+=1;self.io.tripped=False
        self.run=run
        cmode=('Timed' if self.timed.get() else 'Hold') if self.mode=='Hold' else self.mode
        self.ctrl.start(cmode,key,interval,hold,run=='Preview',self.repeat.get(),1 if self.opt['single'].get() else 2)
        if self.mode=='Auto':self.scout_start('auto_picker',run)
        self.armed=True;self.draw_run()
        self.status.set('ARMED — switch to the bound game')
    def capture_rect(self):
        x,y,w,h=self.io.rect(self.target);l,t,r,b=self.region
        return {'left':x+int(l*w),'top':y+int(t*h),'width':int(r*w),'height':int(b*h)}
    def worker(self):
        """Owns OCR engine, screen grabber and learned data. Reports each start-up stage so a stall
        is visible, and falls back to empty learned data if loading it fails."""
        def stage(name):self.results.put(('stage',name,time.monotonic()));log.info('stage: %s',name)
        try:
            stage('importing OCR libraries')
            from learn import Learner, Memory, Templates
            from capture import Grabber
            stage('loading OCR models')
            detector=Detector()
            try:
                import onnxruntime;gpu_ok='DmlExecutionProvider' in onnxruntime.get_available_providers()
            except Exception:gpu_ok=False
            stage('loading learned data')
            folder=self.folder/PROFILE.data_dir
            # Safe start: empty in-memory data that is never saved (existing file stays untouched).
            learner=Learner(folder,load=not self.safe,persist=not self.safe)
            if learner.load_error:
                bad=folder/'learned.npz'
                try:bad.replace(folder/'learned.bad.npz')
                except OSError:pass
                log.warning('learned data unreadable (%s); moved to learned.bad.npz, starting empty',learner.load_error)
            stage('starting screen capture')
            grab=Grabber()
            self.results.put(('ready',detector.gpu,learner.stats(),gpu_ok))
        except Exception as e:
            log.exception('engine start failed');self.results.put(('fatal',f'{type(e).__name__}: {e}'));return
        while True:
            job=self.jobs.get()
            if job is None:learner.save();return
            if job[0]=='clear':learner.clear();self.results.put(('cleared',learner.stats()));continue
            gen,rect,allowed,exclude,opts,stamp=job
            try:
                if opts['gpu']!=detector.gpu:detector=Detector(gpu=opts['gpu'])
                learner.set_limit(opts['limit']);grab.set_dxgi(opts['dxgi'])
                capture_mono=time.monotonic();frame=grab.grab(rect)
                use=learner if opts['memory'] or opts['templates'] else None
                prompts,debug,raw,rejected,info=detector.detect(frame,allowed,exclude,opts,use)
                info['backend']=grab.last_backend;info['stats']=learner.stats();info['rect']=rect;info['gpu']=detector.gpu;info['queue_mono']=stamp;info['capture_mono']=capture_mono
                self.results.put(('scan',gen,prompts,debug,raw,rejected,info,stamp,time.monotonic()))
            except Exception as e:self.results.put(('error',gen,str(e)))
    def drain(self,now):
        while True:
            try:r=self.results.get_nowait()
            except queue.Empty:return
            if r[0]=='stage':self.stage,self.stage_since=r[1],r[2];continue
            if r[0]=='ready':
                self.ready=True;self.detected.set(f'Scout ready ({time.monotonic()-self.load_started:.1f} s). Start with PREVIEW first.');self.show_stats(r[2])
                self.settings.set('engine_ok',True);self.settings.save();log.info('engine ready')
                if r[3] and not self.gpu_ok:self.gpu_ok=True;self.gpucheck.configure(state='normal',text='GPU · DirectML')
                continue
            if r[0]=='cleared':self.busy=False;self.show_stats(r[1]);self.status.set('Learned data cleared.');continue
            if r[0]=='fatal':
                self.ready=False;self.detected.set('Recognition engine failed to start');self.stop('Engine error: '+r[1][:120]+' — details in data\\orcpresser.log');continue
            self.busy=False
            if r[1]!=self.generation:continue
            if r[0]=='error':self.stop('Recognition error: '+r[2]);continue
            _,gen,prompts,debug,raw,rejected,info,stamp,finished=r
            self.scan_ms=(finished-stamp)*1000;self.capture_backend=info['backend'];self.engine='GPU' if info['gpu'] else 'CPU'
            info['detected_mono']=finished;info['consumed_mono']=now
            self.show_stats(info['stats'])
            if not self.ctrl.running or self.io.foreground()!=self.target or now-stamp>1.2:
                self.ctrl.release();self.detected.set('Scan discarded: focus changed or image too old.');continue
            p=prompts[0] if prompts else None
            self.scout_event('vision','prompt',None if p is None else {'action':p.action,'key':p.key,'hold':p.hold,'source':p.source},
                confidence=None if p is None else p.confidence,mono=info.get('capture_mono',stamp),
                latency_ms=(finished-info.get('capture_mono',stamp))*1000,fresh_ms=(now-info.get('capture_mono',stamp))*1000,
                details={'raw':raw[:240],'rejected':[(a,k,t) for a,k,t,_ in rejected[:4]],'queue_mono':info.get('queue_mono'),
                         'capture_mono':info.get('capture_mono'),'detected_mono':finished,'consumed_mono':now,'rect':info.get('rect'),'backend':info.get('backend')},
                stream='vision')
            self.observe_geo(info,info['rect'])
            self.meter.scan(p.identity if p else None,stamp)
            sent=self.ctrl.count;self.ctrl.observation(p,now);sent=self.ctrl.count>sent
            self.scout_event('controller','decision',{'sent':sent,'held':self.ctrl.held,'running':self.ctrl.running},mono=now,
                details={'prompt':None if p is None else p.identity,'preview':self.ctrl.preview,'stable':getattr(self.ctrl,'stable',None),'confirm':getattr(self.ctrl,'confirm',None)},stream='controller')
            decided=sent or (p is not None and self.ctrl.preview and self.ctrl.stable==self.ctrl.confirm)
            if getattr(self,'bench',None):self.bench.scan(self.scan_ms,p.identity if p else None,p.source if p else None,stamp,decided)
            if decided and self.meter.fired(time.monotonic(),f'{p.action} {p.key}',self.scan_ms,
                    {'memory':'memory','template':'template'}.get(p.source,'OCR')+(' prev' if self.ctrl.preview else '')):
                self.timetext.set(self.meter.summary())
            if p:line=f'{p.action} → {"HOLD" if p.hold else "TAP"} {p.key}  ({p.confidence:.0%}){" [M]" if p.source=="memory" else " [T]" if p.source=="template" else ""}'
            elif rejected:line='Excluded: '+', '.join(f'{a} {k} ("{t}")' for a,k,t,_ in rejected[:2])
            else:line='No approved prompt'
            self.detected.set(line);self.log_read(line if p or rejected else 'none · '+raw[:32],sent)
            self.raw.set(raw[:160])
            im=Image.fromarray(cv2.cvtColor(debug,cv2.COLOR_BGR2RGB));im.thumbnail((330,125));self.thumb=ImageTk.PhotoImage(im)
            self.previewbox.configure(image=self.thumb,text='',width=330,height=125)
    def show_output(self,now):
        """Live state for Repeat/Hold so you can see it working: held key, elapsed / target time, presses."""
        try:
            if getattr(self,'mode','Auto') not in ('Repeat','Hold') or not hasattr(self,'outtext'):return
            c=self.ctrl
            if not c.running:
                f=getattr(c,'finished',None)
                if f is not None:self.outtext.set(f'Done — held {f:.2f} s, released');c.finished=None
                elif not self.outtext.get().startswith('Done'):self.outtext.set('Idle — press LIVE, then \\ in the game')
                return
            if getattr(self,'armed',False):self.outtext.set('Armed — switch to the game');return
            held=f'● HOLDING {c.held}' if c.held else '○ released'
            el=now-getattr(c,'down_at',now)
            if c.mode=='Hold':self.outtext.set(f'{held}\n{el:5.1f} s · until stopped')
            elif c.mode=='Timed':self.outtext.set(f'{held}\n{min(el,c.hold):5.1f} / {c.hold:.1f} s')
            else:self.outtext.set(f'{held}\n{c.count-getattr(c,"base_count",0)} presses · every {c.interval*1000:.0f} ms, {c.hold*1000:.0f} ms each')
        except Exception:log.exception('output display')
    def loading_progress(self,now):
        """Show which start-up stage the engine is in; flag a stall. Never lets tick() fail."""
        try:
            if getattr(self,'ready',True) or not hasattr(self,'stage_since'):return
            took=now-self.stage_since
            self.detected.set(f'Loading local recognition engine… {self.stage} ({now-self.load_started:.0f} s)')
            if took>45 and not getattr(self,'stall_reported',False):
                self.stall_reported=True;log.warning('engine stalled at stage %r for %.0f s',self.stage,took)
                self.stop(f'Engine seems stuck at "{self.stage}" ({took:.0f} s). Close, run Setup.cmd → 4, and send data\\orcpresser.log.')
        except Exception:log.exception('progress display')
    def show_stats(self,st):
        n,t,kb=st;self.learntext.set(f'Learned: {n} memory · {t} templates · {kb:.0f} KB')
    def log_read(self,line,sent=False):
        """Keep the last 5 distinct readings. Consecutive repeats only refresh the time, so the
        label is rebuilt a few times per second at most: negligible CPU."""
        stamp=time.strftime('%H:%M:%S')+f'.{int(time.time()*10)%10}'
        entry=(('▶ ' if sent else '  ')+line)[:44]
        if line==self.last_read and self.reads and not sent:self.reads[0]=(stamp,self.reads[0][1])
        else:self.reads.appendleft((stamp,entry));self.last_read=line
        self.readtext.set('\n'.join(f'{t} {e}' for t,e in self.reads))
    def tick(self):
        try:
            now=time.monotonic()
            if not self.visual:
                self.io.heartbeat=now
                self.loading_progress(now)
                self.show_output(now)
                fg=self.io.foreground();focused=self.io.own(fg);level=self.opacity.get()
                if focused:self.root.attributes('-alpha',1.)
                elif level>0:self.root.attributes('-alpha',level/100)
                elif getattr(self,'last_focused',False) and not self.selecting:
                    # A 0 % window would still be topmost and swallow clicks, so minimize instead,
                    # once per focus loss; restoring it from the taskbar focuses it again.
                    self.root.iconify()
                self.last_focused=focused
                hot=self.io.pressed(0xDC)
                if self.previous_hot and not hot and not self.selecting:self.toggle()
                self.previous_hot=hot
                reacquire=self.io.pressed(0x76)  # F7
                if getattr(self,'previous_reacquire',False) and not reacquire and not self.selecting and self.mode=='Fishing':self.fishing_panel.reacquire()
                self.previous_reacquire=reacquire
                if self.io.tripped and self.ctrl.running:self.stop('STOPPED — focus lost or F8 pressed')
                self.drain(now)
                if self.ctrl.running:
                    if self.armed:
                        if fg==self.target:self.armed=False;self.status.set('TEST RUNNING — hands off mouse and keyboard; F8 aborts' if getattr(self,'bench',None) else 'SCOUTING — PREVIEW, no keys sent' if self.mode=='Auto' and self.run=='Preview' else 'LIVE — '+self.mode)
                    else:
                        # Foreground focus controls stopping; pointer position does not.
                        self.ctrl.tick(now,fg==self.target)
                        if not self.ctrl.running:self.stop(getattr(self.ctrl,'reason','STOPPED — finished or target lost focus'))
                    if self.ctrl.running and not self.armed and self.mode=='Fishing':self.fishing_panel.tick(now,fg)
                    if self.ctrl.running and not self.armed and getattr(self,'bench',None):self.bench_tick(now)
                    if self.ctrl.running and not self.armed and (self.mode=='Auto' or getattr(self,'bench',None)) and not self.busy and now-self.last_scan>=SCAN_GAP:
                        # Do not capture an area covered by our own panel.
                        rect=self.capture_rect();iconic=self.root.state()=='iconic';rx=self.root.winfo_rootx();ry=self.root.winfo_rooty();rw=self.root.winfo_width();rh=self.root.winfo_height()
                        overlap=not iconic and rx<rect['left']+rect['width'] and rx+rw>rect['left'] and ry<rect['top']+rect['height'] and ry+rh>rect['top']
                        if overlap and getattr(self,'bench',None):self.stop('TEST ABORTED — this panel covers the capture region; move it aside (or use opacity 0) and run again')
                        elif overlap:self.ctrl.release();self.status.set('Move this panel outside the selected capture region.')
                        elif rect['width']>0 and rect['height']>0:
                            # tests measure recognition of every action (preview only), not just the allowlist
                            allowed=list(ACTIONS) if getattr(self,'bench',None) else [a for a,v in self.allowed.items() if v.get()]
                            self.jobs.put_nowait((self.generation,rect,allowed,exclusions(self.exclude.get()),self.opts(),now));self.busy=True;self.last_scan=now
                if getattr(self,'pending_clear',False) and not self.busy and self.ready:
                    self.pending_clear=False;self.jobs.put_nowait(('clear',));self.busy=True
        except Exception as e:
            log.exception('tick error');self.stop('Error: '+str(e))
        # Manual modes: wake up exactly when the next press/release is due (25 ms otherwise).
        due=None
        try:due=self.ctrl.next_due(time.monotonic()) if not getattr(self,'armed',False) else None
        except Exception:pass
        self.root.after(max(1,min(25,int(due*1000)+1)) if due is not None else 25,self.tick)
    def metrics(self):
        cpu=self.proc.cpu_percent()/max(1,psutil.cpu_count());ram=self.proc.memory_info().rss/1024**2
        self.history.append((cpu,ram));self.metrictext.set(f'CPU {cpu:5.1f}%   RAM {ram:6.1f} MiB   {getattr(self,"engine","CPU")}\nScan {self.scan_ms:5.0f} ms   Inputs {self.ctrl.count}   {getattr(self,"capture_backend","mss")}')
        c=self.chart;c.delete('all');w=max(300,c.winfo_width())
        for y in (22,48,74):c.create_line(0,y,w,y,fill='#303824')
        maxram=max(128,max(r for _,r in self.history)*1.1)
        for col,idx,scale in [(GREEN,0,100),('#c7a45b',1,maxram)]:
            pts=[]
            for i,v in enumerate(self.history):pts.extend((i*(w-8)/89+4,84-min(1,v[idx]/scale)*64))
            if len(pts)>=4:c.create_line(*pts,fill=col,width=2)
        c.create_text(6,10,text='CPU 0–100%',fill=GREEN,anchor='w',font=('Segoe UI',8))
        c.create_text(w-6,10,text=f'RAM 0–{maxram:.0f} MiB',fill=GOLD,anchor='e',font=('Segoe UI',8))
        self.root.after(1000,self.metrics)
    def error(self,typ,value,tb):
        log.error('UI error',exc_info=(typ,value,tb))
        self.stop('UI error: '+str(value))
        import traceback
        traceback.print_exception(typ,value,tb)
    def close(self):
        self.stop()
        if getattr(self,'settings',None):
            try:self.save_window()
            except tk.TclError:pass
            if not getattr(self,'ready',True) and time.monotonic()-getattr(self,'load_started',0)<45:
                self.settings.set('engine_ok',None)   # closed early, not a stall: no safe start next time
            self.settings.set('clean_exit',True);self.settings.save()
        if self.io:self.io.release_all()
        if self.thread:
            # Let the worker save learned data (bounded wait; a running scan finishes first).
            try:self.jobs.put(None,timeout=1)
            except queue.Full:pass
            self.thread.join(timeout=2)
        self.root.destroy()

log=logging.getLogger('orcpresser')
def setup_log(folder):
    from logging.handlers import RotatingFileHandler
    h=RotatingFileHandler(Path(folder)/'orcpresser.log',maxBytes=256*1024,backupCount=1,encoding='utf-8')
    h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(threadName)s %(message)s'))
    log.addHandler(h);log.setLevel(logging.INFO)

if __name__=='__main__':
    moved=migrate_data()             # flat layout (<= 1.9) -> data/, before anything reads settings
    setup_log(ensure_data())
    if moved:log.info('migrated from old layout: %s',', '.join(moved))
    visual='--visual-preview' in sys.argv
    if sys.platform!='win32' and not visual:raise SystemExit('Orcish Dragonwilds Helper runs on Windows 10/11.')
    if sys.platform=='win32':
        try:ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:pass
    if sys.platform=='win32':
        # 1 ms timer resolution instead of Windows' default 15.6 ms, so Repeat/Hold timings are exact.
        try:ctypes.windll.winmm.timeBeginPeriod(1);atexit.register(ctypes.windll.winmm.timeEndPeriod,1)
        except Exception:pass
    root=tk.Tk();app=App(root,visual);root.mainloop()
