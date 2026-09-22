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
        if isinstance(saved,dict) and isinstance(saved.get('confirmed'),(int,float)):self.calibration.confirmed=float(saved['confirmed'])
        self.regions=app.settings.get('fishing_regions',{})
        if not isinstance(self.regions,dict):self.regions={}
        self.regions={k:v for k,v in self.regions.items() if k in ('bar','prompt','result','spot','active','left','right') and isinstance(v,list) and len(v)==4 and all(isinstance(n,(float,int)) and 0<=n<=1 for n in v) and v[2]>0 and v[3]>0 and v[0]+v[2]<=1.001 and v[1]+v[3]<=1.001}
        self.mode=tk.StringVar(value=app.settings.get('fishing_mode','101'))
        if self.mode.get() not in ('101','advanced'):self.mode.set('101')
        self.record=tk.BooleanVar(value=bool(app.settings.get('fishing_record',False)));self.auto=tk.BooleanVar(value=bool(app.settings.get('fishing_auto_cast',False)))
        self.show_overlay=tk.BooleanVar(value=bool(app.settings.get('fishing_show_overlay',False)))
        self.recurring=tk.BooleanVar(value=bool(app.settings.get('fishing_recurring',False)))
        self.trial=tk.BooleanVar(value=False);self.duration=tk.StringVar(value=str(app.settings.get('fishing_cast_ms',600)))
        self.message=tk.StringVar(value='Fishing Bot 101: set BAR and PROMPT first. RESULT is recommended for No fish/depleted detection.')
        bg=parent['bg']
        def button(text,fn):tk.Button(parent,text=text,command=fn,bg='#384829',fg='#e6d8b0',activebackground='#526737',relief='flat').pack(fill='x',pady=2)
        button('BIND GAME · switch to it within 3 seconds',app.bind_game)
        modes=tk.Frame(parent,bg=bg);modes.pack(fill='x',pady=(2,4))
        for value,title in [('101','FISHING BOT 101'),('advanced','ADVANCED · EXP')]:
            tk.Radiobutton(modes,text=title,value=value,variable=self.mode,command=self.mode_changed,bg=bg,fg='#e6d8b0',selectcolor='#15200e',activebackground=bg).pack(side='left',expand=True,fill='x')
        row=tk.Frame(parent,bg=bg);row.pack(fill='x')
        for key,label in [('bar','BAR'),('prompt','REEL'),('active','STOP'),('left','PULL L'),('right','PULL R'),('result','RESULT'),('spot','SPOT')]:tk.Button(row,text=label,command=lambda n=key:self.select(n),bg='#302c22',fg='#e6d8b0').pack(side='left',expand=True,fill='x')
        tk.Label(parent,text='BOT 101 requires BAR + REEL. STOP should frame Stop Fishing (waiting-for-bite). PULL L / PULL R should frame the fight prompts.\nRESULT improves catch/no-fish detection. SPOT and automatic casting belong to Advanced.',bg=bg,fg='#9ba087',justify='left',wraplength=365).pack(fill='x')
        self.overlay_box=tk.Checkbutton(parent,text='Show calibration overlay (BAR / REEL / STOP / PULL L / PULL R / RESULT / SPOT)',variable=self.show_overlay,command=self.overlay_changed,bg=bg,fg='#e6d8b0',selectcolor='#15200e',activebackground=bg,anchor='w');self.overlay_box.pack(fill='x')
        self.recurring_box=tk.Checkbutton(parent,text='Recurring rounds · after catch/failure, wait for your next cast',variable=self.recurring,command=lambda:(app.stop('Fishing settings changed'),app.persist('fishing_recurring',self.recurring.get())),bg=bg,fg='#e6d8b0',selectcolor='#15200e',activebackground=bg,anchor='w');self.recurring_box.pack(fill='x')
        self.record_box=tk.Checkbutton(parent,text='Record manual test (cropped images + A/D/LMB states)',variable=self.record,command=lambda:(app.stop('Fishing settings changed'),app.persist('fishing_record',self.record.get())),bg=bg,fg='#e6d8b0',selectcolor='#15200e',activebackground=bg,anchor='w');self.record_box.pack(fill='x')
        self.auto_box=tk.Checkbutton(parent,text='Advanced: automatic cast from current position',variable=self.auto,command=lambda:(app.stop('Fishing settings changed'),app.persist('fishing_auto_cast',self.auto.get())),bg=bg,fg='#e6d8b0',selectcolor='#15200e',activebackground=bg,anchor='w');self.auto_box.pack(fill='x')
        self.trial_box=tk.Checkbutton(parent,text='Advanced: trial cast only (one cast, then stop)',variable=self.trial,command=lambda:app.stop('Fishing settings changed'),bg=bg,fg='#e6d8b0',selectcolor='#15200e',activebackground=bg,anchor='w');self.trial_box.pack(fill='x')
        tk.Label(parent,text='Bot 101: hold A/D through blue; swap direction only when blue returns to red. Reel (Hold) overrides A/D.',bg=bg,fg='#9ba087',justify='left').pack(fill='x')
        self.cast_row=row=tk.Frame(parent,bg=bg);row.pack(fill='x');tk.Label(row,text='Advanced cast hold · ms (50–3000)',bg=bg,fg='#e6d8b0').pack(side='left');self.cast_entry=tk.Entry(row,textvariable=self.duration,width=9);self.cast_entry.pack(side='right')
        self.duration.trace_add('write',self.duration_changed)
        tk.Label(parent,text='USE SHORT/MID/LONG selects a trial. Then label landing WAS SHORT, WAS LONG, or WAS HIT (correct).',bg=bg,fg='#9ba087',wraplength=365,justify='left').pack(fill='x',pady=(4,0))
        self.trial_buttons=[]
        row=tk.Frame(parent,bg=bg);row.pack(fill='x',pady=3)
        for kind in ('short','mid','long'):
            b=tk.Button(row,text='USE '+kind.upper(),command=lambda k=kind:self.use_trial(k));b.pack(side='left',expand=True,fill='x');self.trial_buttons.append(b)
        row=tk.Frame(parent,bg=bg);row.pack(fill='x')
        for kind in ('short','hit','long'):
            b=tk.Button(row,text='WAS '+kind.upper(),command=lambda k=kind:self.feedback(k));b.pack(side='left',expand=True,fill='x');self.trial_buttons.append(b)
        button('RESET CAST BRACKET (100–1200 ms)',self.reset);button('NEW SPOT / REACQUIRE',self.reacquire)
        tk.Label(parent,textvariable=self.message,bg=bg,fg='#98c657',wraplength=365,justify='left',anchor='w').pack(fill='x',pady=6)
        self.mode_changed(initial=True)
    def ensure_overlay(self):
        if self.overlay is None:self.overlay=FishingOverlay(self.app.root)
        return self.overlay
    def refresh_overlay(self,caption='CALIBRATION OVERLAY · adjust BAR / REEL / STOP / PULL L / PULL R / RESULT / SPOT'):
        a=self.app
        if not self.show_overlay.get():
            if self.overlay:self.overlay.hide()
            return
        if not a.target or a.visual:
            self.message.set('Bind the game first to show the calibration overlay.');return
        overlay=self.ensure_overlay()
        if not overlay.available:
            self.message.set('Overlay is unavailable on this system/capture mode.');return
        overlay.show(a.io.rect(a.target),self.regions,caption,{'spot':None,'app_minimized':a.root.state()=='iconic','running':bool(getattr(a.ctrl,'running',False)),'preview':bool(getattr(a.ctrl,'preview',False)),'state':getattr(a.ctrl,'state','IDLE'),'held':getattr(a.ctrl,'held',None)})
    def overlay_changed(self):
        self.app.persist('fishing_show_overlay',self.show_overlay.get())
        if self.show_overlay.get():self.refresh_overlay()
        elif self.overlay:self.overlay.hide()
    def duration_changed(self,*_):
        self.app.stop('Cast duration changed')
        try:value=int(self.duration.get())
        except ValueError:return
        if 50<=value<=3000:self.app.persist('fishing_cast_ms',value)
    def mode_changed(self,initial=False):
        advanced=self.mode.get()=='advanced'
        self.app.persist('fishing_mode',self.mode.get())
        state='normal' if advanced else 'disabled'
        for w in [self.auto_box,self.trial_box,self.cast_entry,*self.trial_buttons]:w.configure(state=state)
        if not advanced:self.trial.set(False)
        if not initial:self.app.stop('Fishing mode changed')
        self.message.set('Advanced: BAR + REEL + optional RESULT/SPOT; auto-cast calibration available. Movement/pool navigation is not autonomous yet.' if advanced else 'Fishing Bot 101: set BAR and REEL. Cast, position, and move manually; F7 = New spot / Reacquire.')
    def save_bracket(self):self.app.persist('fishing_cast_bracket',{'low':self.calibration.low,'high':self.calibration.high,'confirmed':self.calibration.confirmed})
    def reset(self):self.app.stop();self.calibration=CastCalibration();self.save_bracket();self.message.set('Bracket reset; maintain a fixed player position and camera.')
    def reacquire(self):self.app.stop('New spot / camera changed');self.calibration=CastCalibration();self.save_bracket();self.message.set('Travel pause complete: cast timing invalidated. BAR/REEL screen regions remain saved; verify Preview before resuming.')
    def use_trial(self,kind):self.duration.set(str(round(self.calibration.trial(kind)*1000)));self.trial.set(True)
    def feedback(self,kind):
        self.app.stop()
        try:
            seconds=float(self.duration.get())/1000;next_=self.calibration.feedback(seconds,kind);self.save_bracket()
            if kind=='hit':self.app.persist('fishing_cast_ms',round(seconds*1000));self.trial.set(False);self.message.set('Cast duration saved. Recalibrate if player/camera/rod changes.')
            else:self.duration.set(str(round(next_*1000)));self.message.set('Next midpoint selected; enable Trial cast and LIVE to try it.')
        except ValueError as e:self.message.set(str(e))
    def select(self,name):
        a=self.app;a.stop()
        if self.overlay:self.overlay.hide()
        if not a.target or a.visual:self.message.set('Bind the game first.');return
        x,y,w,h=a.io.rect(a.target)
        if min(w,h)<100:self.message.set('Restore the game window first.');return
        a.selecting=True;over=tk.Toplevel(a.root);over.overrideredirect(True);over.geometry(f'{w}x{h}{x:+d}{y:+d}');over.attributes('-topmost',True);over.attributes('-alpha',.45)
        c=tk.Canvas(over,bg='#183015',cursor='crosshair',highlightthickness=0);c.pack(fill='both',expand=True)
        # Keep every saved calibration visible while editing. The region being replaced
        # is highlighted separately, so the new drag can be compared with the old box.
        for old_name,(l,t,r,b) in self.regions.items():
            x1,y1,x2,y2=l*w,t*h,(l+r)*w,(t+b)*h
            selected=old_name==name
            outline='#66d9ff' if selected else '#a4d666'
            label='REEL' if old_name=='prompt' else 'STOP' if old_name=='active' else 'PULL L' if old_name=='left' else 'PULL R' if old_name=='right' else old_name.upper()
            c.create_rectangle(x1,y1,x2,y2,outline=outline,width=3 if selected else 2,dash=(7,4) if selected else ())
            c.create_text(x1,max(12,y1-12),text=('OLD '+label if selected else label),anchor='w',fill=outline,font=('Segoe UI',10,'bold'))
        c.create_text(w/2,30,text='DRAG NEW '+('REEL' if name=='prompt' else 'STOP' if name=='active' else 'PULL L' if name=='left' else 'PULL R' if name=='right' else name.upper())+' REGION · BLUE DASH = OLD · ESC CANCELS',fill='white',font=('Segoe UI',16,'bold'))
        start=[];shape=[None]
        def close():
            a.selecting=False;over.destroy();self.refresh_overlay()
        def down(e):start[:]=[e.x,e.y]
        def drag(e):
            if not start:return
            if shape[0]:c.delete(shape[0])
            shape[0]=c.create_rectangle(*start,e.x,e.y,outline='yellow',width=2)
        def up(e):
            if start:
                l,r=sorted((start[0],max(0,min(w,e.x))));t,b=sorted((start[1],max(0,min(h,e.y))))
                if r-l>=15 and b-t>=8:self.regions[name]=[l/w,t/h,(r-l)/w,(b-t)/h];a.persist('fishing_regions',self.regions);self.message.set('Regions: '+', '.join(self.regions))
            close()
        c.bind('<Button-1>',down);c.bind('<B1-Motion>',drag);c.bind('<ButtonRelease-1>',up);over.bind('<Escape>',lambda _:close());over.focus_force()
    def start(self,run):
        a=self.app
        if a.visual:return
        if not a.target or not a.io.game(a.target):a.status.set('Bind a Dragonwilds game window first.');return
        if not all(k in self.regions for k in ('bar','prompt')):a.status.set('Select BAR and REEL regions first.');return
        if self.record.get() and run!='Preview':a.status.set('Manual recording uses PREVIEW, so only you control the game.');return
        try:config=FishingConfig(cast_seconds=float(self.duration.get())/1000,auto_cast=self.mode.get()=='advanced' and self.auto.get(),recurring=self.recurring.get(),require_active=self.recurring.get() and 'active' in self.regions).validate()
        except ValueError as e:a.status.set(str(e));return
        a.stop();a.generation+=1;a.io.tripped=False
        if self.show_overlay.get():self.ensure_overlay()
        a.ctrl=FishingController(a.io.output,config);a.ctrl.start(run=='Preview',self.trial.get());self.session=FishingCapture(a.io,a.target,self.regions,a.folder,self.record.get(),a.opts()['dxgi'])
        a.run=run;a.last_run=run;a.armed=True;a.draw_run();a.status.set('FISHING ARMED — switch to the game; F8 stops');self.message.set(('Recurring: waiting for your next cast; STOP confirms waiting-for-bite.' if self.recurring.get() else 'Watching fishing phase signals.')+' PULL L/R or BAR starts fight handling; Reel (Hold) overrides with LMB.')
    def stop(self):
        if self.session:self.session.close();self.session=None
        if self.overlay:
            if self.show_overlay.get():self.refresh_overlay()
            else:self.overlay.hide()
    def tick(self,now,fg):
        a=self.app
        if not self.session:return
        if fg!=a.target:
            if self.overlay:self.overlay.hide()
            return
        if a.root.state()!='iconic':
            x,y=a.root.winfo_rootx(),a.root.winfo_rooty();w,h=a.root.winfo_width(),a.root.winfo_height();client=a.io.rect(a.target)
            for region in self.regions.values():
                r=rect_pixels(client,region)
                if x<r['left']+r['width'] and x+w>r['left'] and y<r['top']+r['height'] and y+h>r['top']:
                    a.ctrl.release();self.message.set('Move the panel outside fishing capture regions, or minimize it.');return
        try:o,info,error=self.session.results.get_nowait()
        except queue.Empty:return
        if error:a.stop(error);return
        a.ctrl.observe(o,now)
        stop_text='YES' if info.get('active') is True else 'NO' if info.get('active') is False else 'N/A';active_score=info.get('active_score')
        score_text='' if active_score is None else f' {active_score:.0%}'
        left_text='YES' if info.get('pull_left') is True else 'NO' if info.get('pull_left') is False else 'N/A'
        right_text='YES' if info.get('pull_right') is True else 'NO' if info.get('pull_right') is False else 'N/A'
        caption=f'{"PREVIEW" if a.ctrl.preview else "LIVE"}  {a.ctrl.state} | {o.color} | {"would hold" if a.ctrl.preview else "holding"}: {a.ctrl.held or "none"}';caption+=f'\nSTOP {stop_text}{score_text} | PULL L {left_text} | PULL R {right_text} | red {info["red"]:.0%} blue {info["blue"]:.0%} | OCR {info["ocr_ms"]:.0f} ms | frame {(now-o.stamp)*1000:.0f} ms'
        if a.ctrl.state in ('FAILED','DEPLETED'):caption+='\nNO FISH / DEPLETED — move manually, then NEW SPOT / REACQUIRE.'
        elif a.ctrl.state=='WAIT_CAST':caption+='\nROUND ENDED — cast again manually; waiting for STOP Fishing.'
        elif a.ctrl.state=='WAIT_BITE':caption+='\nSTOP Fishing visible — waiting for bite / PULL L-R.'
        self.message.set(caption+'\n'+o.text[:180]+'\n'+a.ctrl.reason);a.scan_ms=info['ocr_ms'];a.capture_backend=info['backend']
        if self.show_overlay.get():
            overlay_info=dict(info);overlay_info.update(app_minimized=a.root.state()=='iconic',running=a.ctrl.running,preview=a.ctrl.preview,state=a.ctrl.state,held=a.ctrl.held)
            self.ensure_overlay().show(a.io.rect(a.target),self.regions,caption,overlay_info)
        elif self.overlay:self.overlay.hide()
        if not a.ctrl.running:a.stop(a.ctrl.reason)
