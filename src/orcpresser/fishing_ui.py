"""Fishing tab integration; calibration and observations stay in data/."""
import queue
import tkinter as tk
from fishing import FishingController, FishingConfig, CastCalibration
from fishing_capture import FishingCapture, rect_pixels
from fishing_overlay import FishingOverlay

class FishingPanel:
    def __init__(self,app,parent):
        self.app=app;self.session=None;self.overlay=None
        saved=app.settings.get('fishing_cast_bracket',{})
        try:self.calibration=CastCalibration(float(saved.get('low',.1)),float(saved.get('high',1.2)))
        except (AttributeError,TypeError,ValueError):self.calibration=CastCalibration()
        self.regions=app.settings.get('fishing_regions',{})
        if not isinstance(self.regions,dict):self.regions={}
        self.regions={k:v for k,v in self.regions.items() if k in ('bar','prompt','result','spot') and isinstance(v,list) and len(v)==4 and all(isinstance(n,(float,int)) and 0<=n<=1 for n in v) and v[2]>0 and v[3]>0 and v[0]+v[2]<=1.001 and v[1]+v[3]<=1.001}
        self.record=tk.BooleanVar(value=bool(app.settings.get('fishing_record',False)));self.auto=tk.BooleanVar(value=bool(app.settings.get('fishing_auto_cast',False)))
        self.trial=tk.BooleanVar(value=False)
        self.duration=tk.StringVar(value=str(app.settings.get('fishing_cast_ms',600)))
        self.message=tk.StringVar(value='Fishing Bot 101: set BAR and PROMPT first. RESULT is recommended for No fish/depleted detection.')
        bg=parent['bg']
        def button(text,fn):
            tk.Button(parent,text=text,command=fn,bg='#384829',fg='#e6d8b0',activebackground='#526737',relief='flat').pack(fill='x',pady=2)
        button('BIND GAME · switch to it within 3 seconds',app.bind_game)
        row=tk.Frame(parent,bg=bg);row.pack(fill='x')
        for name in ('bar','prompt','result','spot'):
            tk.Button(row,text=name.upper(),command=lambda n=name:self.select(n),bg='#302c22',fg='#e6d8b0').pack(side='left',expand=True,fill='x')
        tk.Label(parent,text='BAR = red/blue tension · PROMPT = Cast/Reel (required)\nRESULT = no-fish/catch messages (recommended) · SPOT = advanced/experimental',bg=bg,fg='#9ba087',justify='left').pack(fill='x')
        for title,var,key in [('Record manual test (cropped images + A/D/LMB states)',self.record,'fishing_record'),('Automatic cast from the current position',self.auto,'fishing_auto_cast')]:
            tk.Checkbutton(parent,text=title,variable=var,command=lambda v=var,k=key:(app.stop('Fishing settings changed'),app.persist(k,v.get())),bg=bg,fg='#e6d8b0',selectcolor='#15200e',activebackground=bg,anchor='w').pack(fill='x')
        tk.Checkbutton(parent,text='Trial cast only (one cast, then stop)',variable=self.trial,command=lambda:app.stop('Fishing settings changed'),bg=bg,fg='#e6d8b0',selectcolor='#15200e',activebackground=bg,anchor='w').pack(fill='x')
        tk.Label(parent,text='Bot 101 rule: blue releases A/D and waits for confirmed Reel (Hold).',bg=bg,fg='#9ba087',justify='left').pack(fill='x')
        row=tk.Frame(parent,bg=bg);row.pack(fill='x')
        tk.Label(row,text='Cast hold · ms (50–3000)',bg=bg,fg='#e6d8b0').pack(side='left')
        tk.Entry(row,textvariable=self.duration,width=9).pack(side='right')
        self.duration.trace_add('write',lambda *_:app.stop('Cast duration changed'))
        tk.Label(parent,text='USE SHORT/MID/LONG selects a trial. Then label landing WAS SHORT, WAS LONG, or WAS HIT (correct).',bg=bg,fg='#9ba087',wraplength=365,justify='left').pack(fill='x',pady=(4,0))
        row=tk.Frame(parent,bg=bg);row.pack(fill='x',pady=3)
        for kind in ('short','mid','long'):
            tk.Button(row,text='USE '+kind.upper(),command=lambda k=kind:self.use_trial(k)).pack(side='left',expand=True,fill='x')
        row=tk.Frame(parent,bg=bg);row.pack(fill='x')
        for kind in ('short','hit','long'):
            tk.Button(row,text='WAS '+kind.upper(),command=lambda k=kind:self.feedback(k)).pack(side='left',expand=True,fill='x')
        button('RESET CAST BRACKET (100–1200 ms)',self.reset)
        button('NEW SPOT / REACQUIRE',self.reacquire)
        tk.Label(parent,textvariable=self.message,bg=bg,fg='#98c657',wraplength=365,justify='left',anchor='w').pack(fill='x',pady=6)
    def save_bracket(self):self.app.persist('fishing_cast_bracket',{'low':self.calibration.low,'high':self.calibration.high})
    def reset(self):self.app.stop();self.calibration=CastCalibration();self.save_bracket();self.message.set('Bracket reset; maintain a fixed player position and camera.')
    def reacquire(self):self.app.stop('New spot / camera changed');self.calibration=CastCalibration();self.save_bracket();self.message.set('Move complete: cast timing invalidated. BAR/PROMPT regions remain saved; verify Preview before resuming.')
    def use_trial(self,kind):self.duration.set(str(round(self.calibration.trial(kind)*1000)));self.trial.set(True)
    def feedback(self,kind):
        self.app.stop()
        try:
            seconds=float(self.duration.get())/1000
            next_=self.calibration.feedback(seconds,kind);self.save_bracket()
            if kind=='hit':self.app.persist('fishing_cast_ms',round(seconds*1000));self.trial.set(False);self.message.set('Cast duration saved. Recalibrate if player/camera/rod changes.')
            else:self.duration.set(str(round(next_*1000)));self.message.set('Next midpoint selected; enable Trial cast and LIVE to try it.')
        except ValueError as e:self.message.set(str(e))
    def select(self,name):
        a=self.app;a.stop()
        if not a.target or a.visual:self.message.set('Bind the game first.');return
        x,y,w,h=a.io.rect(a.target)
        if min(w,h)<100:self.message.set('Restore the game window first.');return
        a.selecting=True;over=tk.Toplevel(a.root);over.overrideredirect(True)
        over.geometry(f'{w}x{h}{x:+d}{y:+d}');over.attributes('-topmost',True);over.attributes('-alpha',.45)
        c=tk.Canvas(over,bg='#183015',cursor='crosshair',highlightthickness=0);c.pack(fill='both',expand=True)
        c.create_text(w/2,30,text='DRAG '+name.upper()+' REGION · ESC CANCELS',fill='white',font=('Segoe UI',16,'bold'))
        start=[];shape=[None]
        def close():a.selecting=False;over.destroy()
        def down(e):start[:]=[e.x,e.y]
        def drag(e):
            if not start:return
            if shape[0]:c.delete(shape[0])
            shape[0]=c.create_rectangle(*start,e.x,e.y,outline='yellow',width=2)
        def up(e):
            if start:
                l,r=sorted((start[0],max(0,min(w,e.x))));t,b=sorted((start[1],max(0,min(h,e.y))))
                if r-l>=15 and b-t>=8:
                    self.regions[name]=[l/w,t/h,(r-l)/w,(b-t)/h]
                    a.persist('fishing_regions',self.regions);self.message.set('Regions: '+', '.join(self.regions))
            close()
        c.bind('<Button-1>',down);c.bind('<B1-Motion>',drag);c.bind('<ButtonRelease-1>',up)
        over.bind('<Escape>',lambda _:close());over.focus_force()
    def start(self,run):
        a=self.app
        if a.visual:return
        if not a.target or not a.io.game(a.target):a.status.set('Bind a Dragonwilds game window first.');return
        if not all(k in self.regions for k in ('bar','prompt')):a.status.set('Select BAR and PROMPT regions first.');return
        if self.record.get() and run!='Preview':a.status.set('Manual recording uses PREVIEW, so only you control the game.');return
        try:config=FishingConfig(cast_seconds=float(self.duration.get())/1000,auto_cast=self.auto.get()).validate()
        except ValueError as e:a.status.set(str(e));return
        a.stop();a.generation+=1;a.io.tripped=False
        self.overlay=FishingOverlay(a.root)
        a.ctrl=FishingController(a.io.output,config);a.ctrl.start(run=='Preview',self.trial.get())
        self.session=FishingCapture(a.io,a.target,self.regions,a.folder,self.record.get(),a.opts()['dxgi'])
        a.run=run;a.last_run=run;a.armed=True;a.draw_run()
        a.status.set('FISHING ARMED — switch to the game; F8 stops')
        self.message.set('Watching BAR + PROMPT. Blue waits for Reel (Hold). No fish/depleted stops safely: move manually, then NEW SPOT / REACQUIRE.')
    def stop(self):
        if self.session:self.session.close();self.session=None
        if self.overlay:self.overlay.close();self.overlay=None
    def tick(self,now,fg):
        a=self.app
        if not self.session:return
        if fg!=a.target:
            if self.overlay:self.overlay.hide()
            return
        if a.root.state()!='iconic':
            x,y=a.root.winfo_rootx(),a.root.winfo_rooty();w,h=a.root.winfo_width(),a.root.winfo_height()
            client=a.io.rect(a.target)
            for region in self.regions.values():
                r=rect_pixels(client,region)
                if x<r['left']+r['width'] and x+w>r['left'] and y<r['top']+r['height'] and y+h>r['top']:
                    a.ctrl.release();self.message.set('Move the panel outside fishing capture regions, or minimize it.');return
        try:o,info,error=self.session.results.get_nowait()
        except queue.Empty:return
        if error:a.stop(error);return
        a.ctrl.observe(o,now)
        caption=f'{"PREVIEW" if a.ctrl.preview else "LIVE"}  {a.ctrl.state} | {o.color} | {"would hold" if a.ctrl.preview else "holding"}: {a.ctrl.held or "none"}'
        caption+=f'\nred {info["red"]:.0%} blue {info["blue"]:.0%} | OCR {info["ocr_ms"]:.0f} ms | frame {(now-o.stamp)*1000:.0f} ms'
        if a.ctrl.state=='FAILED':caption+='\nNO FISH / FAILED — move manually, then NEW SPOT / REACQUIRE.'
        self.message.set(caption+'\n'+o.text[:180]+'\n'+a.ctrl.reason)
        a.scan_ms=info['ocr_ms'];a.capture_backend=info['backend']
        if self.overlay:self.overlay.show(a.io.rect(a.target),self.regions,caption,info)
        if not a.ctrl.running:a.stop(a.ctrl.reason)
