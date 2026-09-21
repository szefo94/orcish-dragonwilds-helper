"""Deterministic output controller, independent of GUI and OCR."""
FRESH = .5   # auto repeat taps continue only while the prompt was confirmed this recently (s)
HOLD_MAX = 15.
class Controller:
    def __init__(self, output):
        self.output=output
        self.held=None
        self.running=False
        self.last=None
        self.stable=0
        self.last_seen=0
        self.next_at=0
        self.until=0
        self.count=0
        self.preview=True
        self.latched=None
        self.empty=0
        self.repeat=False
        self.prompt=None
        self.confirm=2

    def release(self):
        if self.held:
            self.output(self.held,False)
            self.held=None

    def stop(self):
        self.release()
        self.running=False
        self.last=None
        self.stable=0
        self.latched=None
        self.empty=0
        self.prompt=None

    def start(self, mode, key, interval, hold, preview=True, repeat=False, confirm=2):
        """Auto mode: hold = tap length, interval = start-to-start spacing of taps (incl. repeats).
        confirm: matching scans required before the first press (1 = fastest, 2 = safer)."""
        self.stop()
        self.mode,self.key,self.interval,self.hold=mode,key,interval,hold
        self.preview=preview;self.repeat=repeat;self.confirm=max(1,int(confirm))
        self.running=True
        self.base_count=self.count
        self.next_at=0
        self.last_seen=0

    def next_due(self,now):
        """Seconds until the controller next needs tick() (manual modes), for precise scheduling."""
        if not self.running or self.mode=='Auto':return None
        if self.held:return None if self.mode=='Hold' else max(0.,self.until-now)
        return max(0.,self.next_at-now)

    def down(self,key,now,duration):
        self.release()
        self.held=key
        self.output(key,True)
        self.down_at=now
        self.until=now+duration
        self.count+=1

    def tick(self,now,focused):
        if not self.running:return
        if not focused:
            self.stop();return
        if self.mode=='Auto':
            if self.held and (now>=self.until or now-self.last_seen>.9):self.release()
            # Persistent tap prompts repeat on the clock, not on scan arrival, so the interval is honoured
            # even when scans are slower. Any missing/changed scan clears self.prompt and stops this.
            p=self.prompt
            if (self.repeat and not self.preview and not self.held and p and not p.hold
                    and self.latched==p.identity and now-self.last_seen<=FRESH and now>=self.next_at):
                self.down(p.key,now,self.hold);self.next_at=now+self.interval
            return
        if self.held:
            if self.mode!='Hold' and now>=self.until:
                self.release()
                if self.mode=='Timed':self.finished=now-self.down_at;self.stop()
                self.next_at=max(self.next_at,now+.01)
            return
        if now>=self.next_at:
            self.down(self.key,now,self.hold)
            # Anchor to the schedule, not to the (slightly late) wake-up, so small delays don't add up.
            # After a real stall (> 1 interval late) restart the schedule instead of bursting to catch up.
            base=self.next_at if self.next_at and now-self.next_at<self.interval else now
            self.next_at=base+self.interval

    def observation(self,prompt,now,repeat=None,cooldown=None):
        if not self.running or self.mode!='Auto':return
        if repeat is not None:self.repeat=repeat
        cooldown=self.interval if cooldown is None else cooldown
        if prompt is None:
            self.release()
            self.last=None;self.stable=0;self.empty+=1;self.prompt=None
            if self.empty>=2:self.latched=None
            return
        self.empty=0
        ident=prompt.identity
        if ident!=self.last:
            self.release();self.stable=1;self.last=ident;self.prompt=None
        else:self.stable+=1
        self.last_seen=now
        if self.stable>=self.confirm:self.prompt=prompt
        if self.stable<self.confirm or self.preview:return
        if self.held:return
        if now<self.next_at:return
        if self.latched==ident and (not self.repeat or prompt.hold):return
        self.down(prompt.key,now,HOLD_MAX if prompt.hold else self.hold)
        self.latched=ident
        self.next_at=now+cooldown


class ReactionMeter:
    """Reaction time per action: from the capture of the first scan that saw a prompt to the moment
    its key was sent (LIVE) or the press decision was reached (PREVIEW). Only the first press per
    sighting counts, so repeat taps do not inflate the numbers. Time before the first scan that saw
    the prompt is invisible to the program and not included."""
    def __init__(self,keep=10):
        from collections import deque
        self.ident=None;self.seen=0.;self.scans=0;self.done=False;self.last=None;self.hist=deque(maxlen=keep)

    def scan(self,identity,stamp):
        """Call once per finished scan with the top prompt identity (or None) and its capture time."""
        if identity!=self.ident:self.ident=identity;self.seen=stamp;self.scans=0;self.done=False
        if identity is not None:self.scans+=1

    def fired(self,now,label,scan_ms,source):
        """Call when the key was sent / decision reached. Returns the record or None if already counted."""
        if self.done or self.ident is None:return None
        self.done=True
        self.last={'label':label,'ms':(now-self.seen)*1000,'scans':self.scans,'scan_ms':scan_ms,'source':source}
        self.hist.append(self.last['ms']);return self.last

    def summary(self):
        if not self.last:return 'No action yet'
        l=self.last;h=list(self.hist)
        return (f"{l['label']}  {l['ms']:.0f} ms · {l['scans']} scan{'s' if l['scans']!=1 else ''} @ {l['scan_ms']:.0f} ms · {l['source']}\n"
                f"Avg {len(h)}: {sum(h)/len(h):.0f} ms · best {min(h):.0f} · worst {max(h):.0f}")
