"""Aim Lab: supervised visual target tracking for Scout research.

This is observational. It draws target/head-candidate rectangles and records
tracking/impact evidence to Scout. It does not move the mouse or fire weapons.
"""
from __future__ import annotations
import ctypes, math, queue, threading, time
from collections import deque
import tkinter as tk
import cv2
import numpy as np

class AimOverlay:
    def __init__(self,root):
        self.window=tk.Toplevel(root);self.window.withdraw();self.window.overrideredirect(True)
        self.window.configure(bg="#010101");self.window.attributes("-topmost",True);self.window.attributes("-alpha",.55)
        self.canvas=tk.Canvas(self.window,bg="#010101",highlightthickness=0);self.canvas.pack(fill="both",expand=True)
        self.available=False
        try:
            self.window.attributes("-transparentcolor","#010101");self.window.update_idletasks()
            u=ctypes.windll.user32
            from ctypes import wintypes as w
            u.GetAncestor.argtypes=[w.HWND,w.UINT];u.GetAncestor.restype=w.HWND
            hwnd=u.GetAncestor(self.window.winfo_id(),2)
            get=u.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p)==8 else u.GetWindowLongW
            set_=u.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p)==8 else u.SetWindowLongW
            get.argtypes=[w.HWND,ctypes.c_int];get.restype=ctypes.c_ssize_t
            set_.argtypes=[w.HWND,ctypes.c_int,ctypes.c_ssize_t];set_.restype=ctypes.c_ssize_t
            set_(hwnd,-20,get(hwnd,-20)|0x08000000|0x00000020|0x00080000|0x00000080)
            u.SetWindowDisplayAffinity.argtypes=[w.HWND,w.DWORD]
            self.hwnd=hwnd;u.ShowWindow.argtypes=[w.HWND,ctypes.c_int]
            self.available=bool(u.SetWindowDisplayAffinity(hwnd,0x11))
        except Exception:self.available=False

    def _revive(self):
        if not self.available:return False
        try:
            self.window.deiconify();self.window.attributes("-topmost",True);self.window.attributes("-alpha",.55)
            self.window.update_idletasks();ctypes.windll.user32.ShowWindow(self.hwnd,4);return True
        except Exception:return False

    def show(self,client,tracks,motions=None,impact=None,target_huds=None):
        if not self._revive():return
        x,y,w,h=client;self.window.geometry(f"{w}x{h}{x:+d}{y:+d}");self.window.update_idletasks()
        ctypes.windll.user32.ShowWindow(self.hwnd,4)
        c=self.canvas;c.delete("all")
        cx,cy=w/2,h/2
        c.create_line(cx-9,cy,cx+9,cy,fill="#f0d698",width=1);c.create_line(cx,cy-9,cx,cy+9,fill="#f0d698",width=1)
        for t in tracks:
            bx,by,bw,bh=t["bbox"];score=t.get("score",0.0);tid=t["id"]
            # Do not draw weak template matches: these were the source of floating boxes on HUD/background.
            if score<.60:continue
            col="#98c657" if score>=.78 else "#f0d698"
            c.create_rectangle(bx,by,bx+bw,by+bh,outline=col,width=2)
            hh=max(6,int(bh*.28))
            c.create_rectangle(bx,by,bx+bw,by+hh,outline="#d9b55b",dash=(3,2),width=1)
            c.create_text(bx,max(10,by-12),text=f"T{tid} {score:.2f}",anchor="w",fill=col,font=("Consolas",10,"bold"))
            reason=t.get("reason",f"seed template match {score:.2f}")
            c.create_text(bx,min(h-8,by+bh+4),text=reason,anchor="nw",fill=col,font=("Consolas",8),width=max(100,bw+90))
            tx=bx+bw/2;ty=by+hh/2
            c.create_line(cx,cy,tx,ty,fill="#6f7861",dash=(2,3))
        for i,m in enumerate((motions or [])[:6],1):
            bx,by,bw,bh=m["bbox"];score=m.get("score",0.0)
            if score<.22:continue
            col="#35d9ff"
            c.create_rectangle(bx,by,bx+bw,by+bh,outline=col,width=2,dash=(5,3))
            c.create_text(bx,max(10,by-12),text=f"M{i} {score:.2f}",anchor="w",fill=col,font=("Consolas",9,"bold"))
            c.create_text(bx,min(h-8,by+bh+4),text=m.get("reason","localized motion"),anchor="nw",fill=col,font=("Consolas",8),width=max(100,bw+100))
        for hud in (target_huds or [])[:3]:
            bx,by,bw,bh=hud["bbox"];col="#ff5df0"
            c.create_rectangle(bx,by,bx+bw,by+bh,outline=col,width=2)
            c.create_text(bx,min(h-8,by+bh+4),text=hud.get("reason","aimed-target HUD"),anchor="nw",
                          fill=col,font=("Consolas",8,"bold"),width=max(150,bw+100))
        if impact:
            txt=f"impact candidate  Δ={impact.get('change',0):.3f}  bright={impact.get('bright',0):.3f}  warm={impact.get('warm',0):.3f}"
            c.create_text(20,22,text=txt,anchor="nw",fill="#f0d698",font=("Consolas",10,"bold"))

    def hide(self):self.window.withdraw()
    def close(self):
        try:self.window.destroy()
        except Exception:pass


def target_hud_candidates(frame,max_results=3):
    """Detect close/aimed target HP HUD from its horizontal green health segment.

    Strong evidence only: this confirms the crosshair has selected a nearby target.
    It does not imply a body/head bounding box.
    """
    if frame is None or getattr(frame,"size",0)==0:return []
    h,w=frame.shape[:2]
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    green=cv2.inRange(hsv,np.array([35,95,80],dtype=np.uint8),np.array([110,255,255],dtype=np.uint8))
    valid=np.zeros_like(green);valid[int(h*.05):int(h*.68),int(w*.05):int(w*.95)]=255
    green=cv2.bitwise_and(green,valid)
    # Horizontal opening rejects grass/foliage while preserving UI bars.
    green=cv2.morphologyEx(green,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(31,2)),iterations=1)
    contours,_=cv2.findContours(green,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    out=[]
    value=hsv[:,:,2];sat=hsv[:,:,1]
    for cnt in contours:
        x,y,bw,bh=cv2.boundingRect(cnt)
        area=float(cv2.contourArea(cnt));aspect=bw/max(1,bh)
        if bw<35 or bh<2 or bh>24 or aspect<4.0 or area<80:continue
        # Full/healthy targets expose a long green segment. Damaged targets may expose only
        # a short green part followed by a long dark rectangular remainder.
        cy=min(h-1,y+bh//2);scan_end=min(w-1,x+260)
        row_v=value[cy,x:scan_end];row_s=sat[cy,x:scan_end]
        dark=((row_v<70)&(row_s<100)).astype(np.uint8)
        dark_run=0;best_dark=0
        for v in dark:
            dark_run=dark_run+1 if v else 0;best_dark=max(best_dark,dark_run)
        strong_full=bw>=120 and aspect>=6
        strong_partial=bw>=55 and best_dark>=80
        if not (strong_full or strong_partial):continue
        ex=max(8,int(max(bw,120)*.08));ey=max(16,int(bh*2.2))
        bx=max(0,x-ex);by=max(0,y-ey);x2=min(w,x+max(bw,120)+best_dark+ex);y2=min(h,y+bh+ey)
        score=.92 if strong_full else .78
        reason=(f"aimed-target HUD · green HP bar {bw}×{bh}"
                if strong_full else f"aimed-target HUD · partial HP {bw}px + dark remainder {best_dark}px")
        out.append({"bbox":[bx,by,x2-bx,y2-by],"bar_bbox":[x,y,bw,bh],"score":score,
                    "source":"target_hud","reason":reason})
    out.sort(key=lambda z:z["score"],reverse=True)
    return out[:max_results]


def impact_features(frame,previous=None):
    """Describe a broad central HUD/target region without assuming game-specific hit colours."""
    if frame is None or frame.size==0:return {}
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    bright=float(np.mean(hsv[:,:,2]>=210))
    warm=float(np.mean(((hsv[:,:,0]<=18)|(hsv[:,:,0]>=170))&(hsv[:,:,1]>=110)&(hsv[:,:,2]>=120)))
    yellow=float(np.mean((hsv[:,:,0]>=18)&(hsv[:,:,0]<=42)&(hsv[:,:,1]>=90)&(hsv[:,:,2]>=140)))
    change=0.0
    if previous is not None and previous.shape==frame.shape:
        change=float(np.mean(cv2.absdiff(frame,previous)))/255.0
    return {"bright":bright,"warm":warm,"yellow":yellow,"change":change}


def _compensated_difference(frame,previous):
    """Return residual motion after estimating dominant camera motion with sparse optical flow."""
    if frame is None or previous is None or frame.shape!=previous.shape:return None,{"compensated":False}
    g0=cv2.cvtColor(previous,cv2.COLOR_BGR2GRAY);g1=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    pts=cv2.goodFeaturesToTrack(g0,maxCorners=220,qualityLevel=.01,minDistance=12,blockSize=7)
    if pts is None or len(pts)<12:
        return cv2.absdiff(frame,previous),{"compensated":False,"points":0}
    nxt,status,_=cv2.calcOpticalFlowPyrLK(g0,g1,pts,None,winSize=(21,21),maxLevel=3,
                                         criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01))
    if nxt is None or status is None:return cv2.absdiff(frame,previous),{"compensated":False,"points":0}
    ok=status.reshape(-1)==1;p0=pts.reshape(-1,2)[ok];p1=nxt.reshape(-1,2)[ok]
    if len(p0)<10:return cv2.absdiff(frame,previous),{"compensated":False,"points":int(len(p0))}
    M,inliers=cv2.estimateAffinePartial2D(p0,p1,method=cv2.RANSAC,ransacReprojThreshold=3.0,maxIters=1200,confidence=.98)
    if M is None:return cv2.absdiff(frame,previous),{"compensated":False,"points":int(len(p0))}
    h,w=frame.shape[:2]
    warped=cv2.warpAffine(previous,M,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
    angle=math.degrees(math.atan2(float(M[1,0]),float(M[0,0])))
    dx,dy=float(M[0,2]),float(M[1,2])
    return cv2.absdiff(frame,warped),{"compensated":True,"points":int(len(p0)),"dx":dx,"dy":dy,"rotation_deg":angle,
                                      "inliers":int(np.sum(inliers)) if inliers is not None else None}


def moving_candidates(frame,previous,max_targets=6):
    """Find localized motion after compensating ordinary camera pan/rotation; skip HUD edges."""
    if frame is None or previous is None or frame.shape!=previous.shape:return []
    h,w=frame.shape[:2]
    diff,cam=_compensated_difference(frame,previous)
    if diff is None:return []
    gray=cv2.cvtColor(diff,cv2.COLOR_BGR2GRAY)
    residual=float(np.mean(gray))/255.0
    # If global motion could not be compensated and almost everything changed, do not invent targets.
    if not cam.get("compensated") and residual>.095:return []
    blur=cv2.GaussianBlur(gray,(5,5),0)
    mask=cv2.threshold(blur,24,255,cv2.THRESH_BINARY)[1]
    # Exclude HUD-prone edges: top radar/captions, bottom action UI, and extreme side strips.
    playable=np.zeros_like(mask)
    y1=max(1,int(h*.16));y2=max(y1+1,int(h*.88));x1=max(1,int(w*.06));x2=max(x1+1,int(w*.94))
    playable[y1:y2,x1:x2]=255;mask=cv2.bitwise_and(mask,playable)
    k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,k,iterations=2)
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    out=[]
    frame_area=float(w*h)
    for cnt in contours:
        area=float(cv2.contourArea(cnt))
        if area<220 or area>frame_area*.08:continue
        x,y,bw,bh=cv2.boundingRect(cnt)
        if bw<12 or bh<12:continue
        pad=max(8,int(max(bw,bh)*.12))
        bx=max(x1,x-pad);by=max(y1,y-pad);ex=min(x2,x+bw+pad);ey=min(y2,y+bh+pad)
        bw2=ex-bx;bh2=ey-by
        if bw2<18 or bh2<18:continue
        local=float(np.mean(gray[by:ey,bx:ex]))/255.0
        score=min(1.0,(area/1800.0)*.35+local*3.5)
        cam_txt=(f" gmc Δx={cam.get('dx',0):.1f} Δy={cam.get('dy',0):.1f} rot={cam.get('rotation_deg',0):.1f}°"
                 if cam.get("compensated") else " no-gmc")
        out.append({"bbox":[int(bx),int(by),int(bw2),int(bh2)],"score":score,
                    "reason":f"residual motion Δ={local:.3f} area={int(area)}{cam_txt}","source":"motion",
                    "camera_motion":cam})
    out.sort(key=lambda x:x["score"],reverse=True)
    return out[:max_targets]


class AimTrackerSession:
    def __init__(self,io,target,event_cb,overlay,interval=.10,max_targets=8):
        self.io=io;self.target=target;self.event_cb=event_cb;self.overlay=overlay
        self.interval=max(.05,float(interval));self.max_targets=max_targets;self.closed=threading.Event()
        self.lock=threading.RLock();self.frame=None;self.client=None;self.tracks=[];self.next_id=1
        self.latest=queue.Queue(maxsize=1);self.previous_impact=None;self.previous_frame=None;self.history=deque(maxlen=12)
        self.thread=threading.Thread(target=self._run,daemon=True,name="aim-lab");self.thread.start()

    def close(self):
        self.closed.set();self.overlay.hide()

    def _offer(self,v):
        try:self.latest.put_nowait(v)
        except queue.Full:
            try:self.latest.get_nowait()
            except queue.Empty:pass
            try:self.latest.put_nowait(v)
            except queue.Full:pass

    def _cursor(self):
        from ctypes import wintypes as w
        p=w.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(p)):return None
        return int(p.x),int(p.y)

    def acquire_at_cursor(self,width=90,height=140,prefer_crosshair=True):
        with self.lock:
            if self.frame is None or self.client is None:return False,"No game frame yet."
            x,y,w,h=self.client
            if prefer_crosshair:
                rx,ry=w//2,h//2;source="crosshair"
            else:
                cur=self._cursor()
                if not cur:return False,"Could not read cursor position."
                cx,cy=cur;rx,ry=cx-x,cy-y;source="cursor"
                if not (0<=rx<w and 0<=ry<h):return False,"Move the cursor over the game target first."
            bw=min(max(24,int(width)),w);bh=min(max(24,int(height)),h)
            bx=max(0,min(w-bw,int(rx-bw/2)));by=max(0,min(h-bh,int(ry-bh/2)))
            crop=self.frame[by:by+bh,bx:bx+bw].copy()
            if crop.size==0:return False,"Target crop is empty."
            gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
            tid=self.next_id;self.next_id+=1
            self.tracks.append({"id":tid,"bbox":[bx,by,bw,bh],"template":gray,"score":1.0,"lost":0,"age":0})
            self.tracks=self.tracks[-self.max_targets:]
            now=time.monotonic()
            self.event_cb("annotation","target_seed",{"id":tid,"bbox":[bx,by,bw,bh],"source":source},mono=now,stream="annotations")
            return True,f"Target T{tid} seeded at {source}; template tracking begins."

    def clear(self):
        with self.lock:self.tracks=[]
        self.event_cb("annotation","targets_cleared",True,mono=time.monotonic(),stream="annotations")

    def mark(self,label):
        now=time.monotonic()
        with self.lock:
            tracks=[{"id":t["id"],"bbox":list(t["bbox"]),"score":t["score"]} for t in self.tracks]
            impact=self.history[-1] if self.history else None
        self.event_cb("annotation","aim_mark",{"label":label,"tracks":tracks,"impact":impact},mono=now,stream="annotations")

    def _track_one(self,gray,t):
        bx,by,bw,bh=t["bbox"];H,W=gray.shape
        mx=max(18,int(bw*.75));my=max(18,int(bh*.55))
        sx=max(0,bx-mx);sy=max(0,by-my);ex=min(W,bx+bw+mx);ey=min(H,by+bh+my)
        search=gray[sy:ey,sx:ex];templ=t["template"]
        if search.shape[0]<templ.shape[0] or search.shape[1]<templ.shape[1]:return t
        res=cv2.matchTemplate(search,templ,cv2.TM_CCOEFF_NORMED)
        _,score,_,loc=cv2.minMaxLoc(res)
        nbx=sx+loc[0];nby=sy+loc[1]
        t["score"]=float(score);t["age"]+=1
        # A low-score match or HUD-edge match is treated as lost rather than jumping to unrelated UI/background.
        in_playfield=(nby>=int(H*.14) and nby+bh<=int(H*.92) and nbx>=int(W*.03) and nbx+bw<=int(W*.97))
        if score>=.60 and in_playfield:
            t["bbox"]=[int(nbx),int(nby),bw,bh];t["lost"]=0
            if score>=.82 and t["age"]%8==0:
                fresh=gray[nby:nby+bh,nbx:nbx+bw]
                if fresh.shape==templ.shape:t["template"]=cv2.addWeighted(templ,.85,fresh,.15,0)
        else:t["lost"]+=1
        return t

    def _run(self):
        try:
            from capture import Grabber
            grab=Grabber()
            while not self.closed.is_set():
                started=time.monotonic()
                if self.io.foreground()!=self.target:
                    self.overlay.hide();self._offer({"foreground":False});self.closed.wait(self.interval);continue
                client=self.io.rect(self.target);x,y,w,h=client
                if w<100 or h<100:raise RuntimeError("Game is minimized or capture size is invalid")
                frame=grab.grab({"left":x,"top":y,"width":w,"height":h});gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
                motions=moving_candidates(frame,self.previous_frame);self.previous_frame=frame.copy()
                target_huds=target_hud_candidates(frame)
                for m in motions:self.event_cb("vision","motion_candidate",m,confidence=m.get("score"),mono=started,stream="vision")
                for hud in target_huds:self.event_cb("vision","target_hud",hud,confidence=hud.get("score"),mono=started,stream="vision")
                with self.lock:
                    self.frame=frame;self.client=client
                    updated=[]
                    for t in self.tracks:
                        t=self._track_one(gray,t)
                        if t["lost"]<12:updated.append(t)
                    self.tracks=updated
                    public=[]
                    for t in self.tracks:
                        bx,by,bw,bh=t["bbox"];hh=max(6,int(bh*.28))
                        cx=bx+bw/2;cy=by+hh/2
                        dx=cx-w/2;dy=cy-h/2
                        item={"id":t["id"],"bbox":list(t["bbox"]),"score":t["score"],"lost":t["lost"],
                              "head_candidate":[bx,by,bw,hh],"crosshair_error":[round(dx,2),round(dy,2)],
                              "normalized":[bx/w,by/h,bw/w,bh/h],
                              "reason":f"seed template match {t['score']:.2f}","source":"template"}
                        public.append(item)
                        self.event_cb("vision","aim_track",item,confidence=t["score"],mono=started,stream="vision")
                rw=max(80,int(w*.45));rh=max(70,int(h*.32));rx=max(0,(w-rw)//2);ry=max(0,int(h*.18))
                roi=frame[ry:min(h,ry+rh),rx:min(w,rx+rw)]
                impact=impact_features(roi,self.previous_impact);self.previous_impact=roi.copy();self.history.append(impact)
                candidate=impact.get("change",0)>.025 and (impact.get("bright",0)>.015 or impact.get("warm",0)>.003 or impact.get("yellow",0)>.003)
                impact["candidate"]=bool(candidate);impact["roi"]=[rx,ry,roi.shape[1],roi.shape[0]]
                if candidate:self.event_cb("vision","impact_candidate",impact,mono=started,stream="vision")
                self.overlay.show(client,public,motions,impact if candidate else None,target_huds)
                self._offer({"foreground":True,"tracks":public,"motions":motions,"target_huds":target_huds,"impact":impact})
                self.closed.wait(max(0.,self.interval-(time.monotonic()-started)))
        except Exception as e:
            self.overlay.hide();self._offer({"error":type(e).__name__+": "+str(e)})


class AimLabPanel:
    def __init__(self,app,parent,colors):
        self.app=app;self.tk=tk;self.c=colors;self.session=None;self.overlay=AimOverlay(app.root)
        self.status=tk.StringVar(value="Idle — bind game, START TRACKING, then press F6 while aiming at a target.")
        self.live=tk.StringVar(value="No target tracks yet.")
        self.box_w=tk.IntVar(value=int(app.settings.get("aim_seed_width",90)))
        self.box_h=tk.IntVar(value=int(app.settings.get("aim_seed_height",140)))
        self._build(parent)

    def _build(self,p):
        c=self.c
        tk.Label(p,text="AIM LAB · EXPERIMENTAL",bg=c["PANEL"],fg=c["GOLD"],font=("Segoe UI",12,"bold"),anchor="w").pack(fill="x")
        tk.Label(p,text="Visual target tracking + Scout telemetry. Draws boxes and a head-candidate band; never moves the mouse or fires.",
                 bg=c["PANEL"],fg=c["MUTED"],wraplength=410,justify="left",anchor="w",font=("Segoe UI",9)).pack(fill="x",pady=(2,8))
        row=tk.Frame(p,bg=c["PANEL"]);row.pack(fill="x",pady=3)
        tk.Button(row,text="START TRACKING",command=self.start).pack(side="left")
        tk.Button(row,text="STOP",command=self.stop).pack(side="left",padx=6)
        tk.Button(row,text="ACQUIRE (F6)",command=self.acquire).pack(side="left",padx=3)
        tk.Button(row,text="CLEAR TARGETS",command=self.clear).pack(side="left",padx=3)
        row=tk.Frame(p,bg=c["PANEL"]);row.pack(fill="x",pady=3)
        tk.Label(row,text="Seed box W×H",bg=c["PANEL"],fg=c["BONE"]).pack(side="left")
        tk.Spinbox(row,from_=24,to=400,textvariable=self.box_w,width=5,command=self._persist_size).pack(side="left",padx=(8,3))
        tk.Spinbox(row,from_=24,to=500,textvariable=self.box_h,width=5,command=self._persist_size).pack(side="left")
        for label,title in (("target","MARK TARGET"),("head","MARK HEAD"),("hit","MARK HIT"),("crit","MARK CRIT"),("miss","MARK MISS")):
            tk.Button(row,text=title,command=lambda x=label:self.mark(x)).pack(side="left",padx=(5,0))
        tk.Label(p,textvariable=self.status,bg=c["PANEL"],fg=c["GREEN"],justify="left",anchor="w",wraplength=410,font=("Segoe UI",9,"bold")).pack(fill="x",pady=(8,2))
        tk.Label(p,textvariable=self.live,bg="#10150e",fg=c["BONE"],justify="left",anchor="nw",wraplength=410,font=("Consolas",8),height=8).pack(fill="x")

    def _persist_size(self):
        self.app.persist("aim_seed_width",self.box_w.get());self.app.persist("aim_seed_height",self.box_h.get())

    def start(self):
        if self.session:self.stop()
        if self.app.visual:self.status.set("Aim Lab requires a real Windows game target.");return
        if not self.app.target:self.status.set("Bind the game first.");return
        self.app.scout_start("aim","Research")
        try:
            self.session=AimTrackerSession(self.app.io,self.app.target,self.app.scout_event,self.overlay)
            self.status.set("TRACKING — stay in game; press F6 to acquire. LMB sample bursts can be labeled later in labels.csv.")
        except Exception as e:
            self.app.scout_stop("Aim Lab start failed");self.session=None;self.status.set("Start failed: "+str(e))

    def stop(self):
        s=self.session;self.session=None
        if s:s.close()
        if getattr(self.app,"scout",None):self.app.scout_stop("Aim Lab stopped")
        if s:self.status.set("Stopped. Aim/Scout logs preserved in data/scout_sessions.")

    def acquire(self):
        if not self.session:self.status.set("Start tracking first.");return
        try:self._persist_size();ok,msg=self.session.acquire_at_cursor(self.box_w.get(),self.box_h.get(),prefer_crosshair=True)
        except Exception as e:ok,msg=False,str(e)
        self.status.set(msg)

    def clear(self):
        if self.session:self.session.clear()
        self.status.set("Target tracks cleared.")

    def mark(self,label):
        if not self.session:self.status.set("Start tracking first.");return
        self.session.mark(label);self.status.set("Marked: "+label.upper())

    def tick(self):
        if not self.session:return
        latest=None
        while True:
            try:latest=self.session.latest.get_nowait()
            except queue.Empty:break
        if latest is None:return
        if latest.get("error"):self.live.set("ERROR: "+latest["error"]);return
        if not latest.get("foreground"):self.live.set("Game not foreground — tracking paused.");return
        tracks=latest.get("tracks") or [];motions=latest.get("motions") or [];huds=latest.get("target_huds") or [];impact=latest.get("impact") or {}
        lines=[f"template tracks={len(tracks)}  motion={len(motions)}  aimed-HUD={len(huds)}  impactΔ={impact.get('change',0):.3f}"]
        for t in tracks[:6]:
            lines.append(f"T{t['id']} score={t['score']:.2f} bbox={t['bbox']} head={t['head_candidate']} err={t['crosshair_error']}")
        self.live.set("\n".join(lines))
