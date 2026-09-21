"""Experimental rod-fishing state machine. No GUI, capture, or Windows dependencies."""
from dataclasses import dataclass
import math
import re

@dataclass(frozen=True)
class Observation:
    stamp: float
    color: str = 'unknown'
    text: str = ''
    text_stamp: float = 0.
    stamina: float | None = None

@dataclass
class FishingConfig:
    cast_seconds: float = .6
    auto_cast: bool = False
    blue_release: bool = False
    first_pull: str = 'A'
    red_probe_seconds: float = .3
    stale_seconds: float = .75
    bite_timeout: float = 30.
    fight_timeout: float = 90.
    min_stamina: float = .08

    def validate(self):
        for name,low,high in [('cast_seconds',.05,3.),('red_probe_seconds',.15,1.),
                              ('stale_seconds',.2,2.),('bite_timeout',3.,120.),
                              ('fight_timeout',5.,180.),('min_stamina',0.,1.)]:
            v=getattr(self,name)
            if not math.isfinite(v) or not low<=v<=high:raise ValueError(f'{name} must be {low}–{high}')
        if self.first_pull not in ('A','D'):raise ValueError('First pull must be A or D')
        return self

class CastCalibration:
    """Manual labels bracket cast strength; player/camera must remain fixed."""
    def __init__(self,low=.1,high=1.2):
        if not 0.05<=low<high<=3:raise ValueError('Cast bounds must satisfy 0.05 <= low < high <= 3 s')
        self.low,self.high=low,high;self.confirmed=None
    def trial(self,kind='mid'):
        return self.low if kind=='short' else self.high if kind=='long' else (self.low+self.high)/2
    def feedback(self,seconds,outcome):
        if not self.low<=seconds<=self.high:raise ValueError('Trial outside current bracket')
        if outcome=='short':self.low=seconds
        elif outcome=='long':self.high=seconds
        elif outcome=='hit':self.confirmed=seconds
        else:raise ValueError('Outcome must be short, long or hit')
        if self.high-self.low<.025 and self.confirmed is None:raise ValueError('Bracket exhausted: reposition and recalibrate')
        return self.trial()

class FishingController:
    mode='Fishing'
    def __init__(self,output,config=None):
        self.output=output;self.config=(config or FishingConfig()).validate()
        self.running=False;self.held=None;self.count=0;self.base_count=0;self.preview=True
        self.state='IDLE';self.reason='';self.started=None;self.last_observation=None
        self.last_color='unknown';self.color_count=0;self.direction=self.config.first_pull
        self.changed=0.;self.cast_until=0.;self.text_kind='';self.text_count=0;self.text_seen=None
        self.trial_only=False
    def start(self,preview=True,trial_only=False):
        self.stop();self.running=True;self.preview=preview;self.trial_only=trial_only
        self.state='READY';self.reason='Waiting for current fishing evidence';self.started=None
        self.last_observation=None;self.last_color='unknown';self.color_count=0;self.text_count=0
        self.text_kind='';self.text_seen=None;self.direction=self.config.first_pull;self.base_count=self.count
        self.changed=0.;self.cast_until=0.
    def release(self):
        if self.held:
            if not self.preview:self.output(self.held,False)
            self.held=None
    def set_key(self,key):
        if key==self.held:return
        self.release()
        if key:
            self.held=key;self.count+=1
            if not self.preview:self.output(key,True)
    def stop(self,reason='Stopped'):
        self.release();self.running=False;self.reason=reason
    def next_due(self,now):return None
    def tick(self,now,focused=True):
        if not self.running:return
        if not focused:self.stop('Game lost focus');return
        if self.started is None:self.started=now
        if self.last_observation is not None and now-self.last_observation>self.config.stale_seconds:
            self.stop('Capture stale — released all inputs');return
        if self.last_observation is None and now-self.started>3:
            self.stop('No capture received');return
        if self.state=='CAST' and now>=self.cast_until:
            self.release();self.state='WAIT_BITE';self.changed=now
            if self.trial_only:self.state='TRIAL_DONE';self.stop('Trial cast released; record short / long / hit')
        if self.state in ('READY','WAIT_BITE') and now-(self.changed or self.started)>self.config.bite_timeout:
            self.stop('No bite / cast evidence before timeout')
        if self.state in ('FIGHT','REEL') and now-self.fight_started>self.config.fight_timeout:
            self.stop('Fight timeout')
    def observe(self,o,now):
        if not self.running or now-o.stamp>self.config.stale_seconds:return
        self.last_observation=o.stamp
        if o.stamina is not None and o.stamina<self.config.min_stamina:
            self.stop('Stamina below configured threshold');return
        text=o.text.lower() if now-o.text_stamp<1.5 else ''
        # Text confirmations count distinct OCR images, not fast ticks reusing cached text.
        kind=('caught' if re.search(r'\b(?:fish caught|you caught|caught a)\b',text) else
              'bait' if 'consider bait' in text else
              'failed' if any(t in text for t in ('escaped','startled','too close','no fish here','depleted')) else
              'reel' if re.search(r'\breel\b',text) and 'hold' in text else
              'cast' if re.search(r'\bcast\b',text) and 'hold' in text else '')
        if o.text_stamp!=self.text_seen:
            self.text_count=self.text_count+1 if kind==self.text_kind else 1
            self.text_seen=o.text_stamp;self.text_kind=kind
        confirmed=kind and self.text_count>=2
        if confirmed and kind in ('caught','bait','failed'):
            self.state={'caught':'CAUGHT','bait':'BAIT_MESSAGE','failed':'FAILED'}[kind]
            self.stop('Observed result: '+kind);return
        self.color_count=self.color_count+1 if o.color==self.last_color else 1
        self.last_color=o.color
        stable=self.color_count>=2
        if self.state=='READY':
            if stable and o.color in ('red','blue'):
                self.state='FIGHT';self.fight_started=now;self.changed=now
            elif confirmed and kind=='cast' and (self.config.auto_cast or self.trial_only):
                self.state='CAST';self.cast_until=now+self.config.cast_seconds;self.changed=now
                self.set_key('LMB');return
            else:return
        if self.state=='WAIT_BITE':
            if stable and o.color in ('red','blue'):
                self.state='FIGHT';self.fight_started=now;self.changed=now
            else:return
        if self.state not in ('FIGHT','REEL'):return
        if not stable:return
        if o.color=='red':
            # Red overrides a cached Reel prompt. Never pull and reel simultaneously.
            if self.state=='REEL':self.release();self.state='FIGHT';self.changed=now
            if self.held is None:self.set_key(self.direction);self.changed=now
            elif now-self.changed>=self.config.red_probe_seconds:
                self.direction='D' if self.direction=='A' else 'A'
                self.set_key(self.direction);self.changed=now
        elif confirmed and kind=='reel' and o.color=='blue':
            self.state='REEL';self.set_key('LMB')
        elif o.color=='blue' and self.state=='FIGHT':
            self.set_key(None if self.config.blue_release else self.direction)
        elif o.color=='unknown':
            self.release();self.reason='Indicator unknown — waiting; not counted as a catch'
        elif self.state=='REEL' and kind!='reel':
            self.release();self.state='FIGHT'
