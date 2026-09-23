"""Fishing capture: fast color observations and a separate, bounded OCR worker."""
from dataclasses import asdict
from pathlib import Path

log=logging.getLogger('orcpresser')
import json, queue, threading, time
import cv2
import numpy as np
from fishing import Observation


def _longest_run(mask):
    best=cur=0
    for value in mask:
        if value:cur+=1;best=max(best,cur)
        else:cur=0
    return best


def indicator(frame):
    """Classify the burn-down fishing bar.

    The active fill shrinks into black/grey. A red state can therefore be only a
    very thin vertical strip at the live edge, so whole-ROI colour percentage is
    not enough. Detect coherent coloured columns instead and give a narrow,
    full-height red edge priority over the older blue fill behind it.
    """
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    # Reference colours sampled from Dragonwilds captures:
    # blue ≈ RGB 181/223/230 (HSV ~94/54/230), red ≈ 208/68/50 (HSV ~3/194/208).
    red_mask=(((hsv[:,:,0]<=10)|(hsv[:,:,0]>=170))&(hsv[:,:,1]>=110)&(hsv[:,:,2]>=90))
    blue_mask=((hsv[:,:,0]>=88)&(hsv[:,:,0]<=135)&(hsv[:,:,1]>=25)&(hsv[:,:,2]>=120))
    h,w=red_mask.shape
    red=float(np.mean(red_mask));blue=float(np.mean(blue_mask))
    red_cols=np.mean(red_mask,axis=0)>=.55
    blue_cols=np.mean(blue_mask,axis=0)>=.55
    red_run=_longest_run(red_cols);blue_run=_longest_run(blue_cols)
    min_edge=max(2,int(np.ceil(w*.004)))
    broad=max(3,int(np.ceil(w*.03)))
    red_edge=(red_run>=min_edge and red_run<=max(4,int(np.ceil(w*.05))) and
              float(np.max(np.mean(red_mask,axis=0),initial=0))>=.70)
    red_broad=red_run>=broad;blue_broad=blue_run>=broad
    if red_edge and blue_broad:color='red'
    elif red_broad and not blue_broad:color='red'
    elif blue_broad and not red_broad:color='blue'
    elif red_broad and blue_broad:
        color='red' if red_run>blue_run*1.4 else 'blue' if blue_run>red_run*1.4 else 'unknown'
    else:color='unknown'
    return color,red,blue


def bar_fill_estimate(frame):
    """Diagnostic 0..1 estimate of the coloured active portion of the fight bar.

    This value is recorded for offline tuning only; controller decisions use the
    red/blue classification, not this estimate.
    """
    if frame is None or getattr(frame,'size',0)==0:return None
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    red=(((hsv[:,:,0]<=10)|(hsv[:,:,0]>=170))&(hsv[:,:,1]>=110)&(hsv[:,:,2]>=90))
    blue=((hsv[:,:,0]>=88)&(hsv[:,:,0]<=135)&(hsv[:,:,1]>=25)&(hsv[:,:,2]>=120))
    coloured=red|blue
    if coloured.shape[1]==0:return None
    active_cols=np.mean(coloured,axis=0)>=.20
    return float(np.mean(active_cols))


def active_indicator(frame):
    """Detect the on-screen Stop Fishing indicator without relying on OCR alone.

    The supplied Dragonwilds reference uses white UI glyphs/text on a changing world
    background. A tight ACTIVE ROI is considered present when enough bright,
    low-saturation UI pixels exist in both the upper (label) and lower (mouse icon)
    parts of the region.
    """
    if frame is None or getattr(frame,'size',0)==0:return False,0.
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    white=(hsv[:,:,1]<70)&(hsv[:,:,2]>190)
    h=white.shape[0]
    if h<4:return False,float(np.mean(white))
    total=float(np.mean(white));upper=float(np.mean(white[:max(1,h//2)]));lower=float(np.mean(white[h//2:]))
    score=min(1.,total/.035)*.5+min(1.,upper/.04)*.3+min(1.,lower/.015)*.2
    return bool(total>=.015 and upper>=.015 and lower>=.006),score


def ui_prompt_score(frame):
    """Cheap white-UI score for small calibrated fishing prompt ROIs.

    This is deliberately geometry/color based and runs much faster than OCR.
    """
    if frame is None or getattr(frame,"size",0)==0:return 0.0
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    white=((hsv[:,:,1]<75)&(hsv[:,:,2]>185)).astype(np.uint8)*255
    h,w=white.shape
    if h<3 or w<3:return float(np.mean(white>0))
    ratio=float(np.mean(white>0))
    # Join letter/icon fragments horizontally and score coherent UI-like components.
    joined=cv2.morphologyEx(white,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(5,2)),iterations=1)
    contours,_=cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    widest=max((cv2.boundingRect(x)[2] for x in contours),default=0)/max(1,w)
    components=sum(1 for x in contours if cv2.contourArea(x)>=4)
    return min(1.0,min(1.0,ratio/.045)*.55+min(1.0,widest/.45)*.30+min(1.0,components/4)*.15)


def resolve_pull_direction(left_score,right_score,min_score=.42,margin=.14,ratio=1.28):
    """Map calibrated PULL L/PULL R visual evidence to A/D, or None if ambiguous."""
    ls=float(left_score or 0.);rs=float(right_score or 0.)
    best=max(ls,rs);other=min(ls,rs)
    if best<min_score:return None,0.0
    if best-other<margin and best/max(.001,other)<ratio:return None,best
    return ('A' if ls>rs else 'D'),best


def rect_pixels(client,ratio):
    x,y,w,h=client;l,t,r,b=ratio
    return dict(left=x+int(l*w),top=y+int(t*h),width=max(1,int(r*w)),height=max(1,int(b*h)))


def spot_candidate(frame):
    """A tentative bright ripple ellipse; never used as proof of cast distance."""
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,np.array([0,0,175]),np.array([179,90,255]))
    contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[c for c in contours if len(c)>=5 and cv2.contourArea(c)>100]
    if not candidates:return None
    c=max(candidates,key=cv2.contourArea)
    return tuple(map(int,cv2.boundingRect(c)))


class FishingCapture:
    def __init__(self,io,target,regions,folder,record=False,dxgi=False):
        self.io,self.target,self.regions=io,target,dict(regions)
        self.record=record;self.dxgi=dxgi;self.closed=threading.Event()
        self.results=queue.Queue(maxsize=1);self.ocr_jobs=queue.Queue(maxsize=1)
        self.lock=threading.Lock();self.text='';self.text_stamp=0.;self.pull_left=False;self.pull_right=False;self.pull_stamp=0.;self.ocr_regions={};self.ocr_ms=0.;self.error=''
        self.started=time.monotonic();self.folder=None;self.bytes=0
        if record:
            from datetime import datetime
            self.folder=Path(folder)/'fishing_sessions'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            self.folder.mkdir(parents=True)
        self.reader=threading.Thread(target=self.read_text,daemon=True,name='fishing-ocr')
        self.worker=threading.Thread(target=self.capture,daemon=True,name='fishing-capture')
        self.reader.start();self.worker.start()
    def close(self,wait=True):
        """Stop both capture/OCR workers. Safe to call repeatedly."""
        self.closed.set()
        # Unblock an OCR worker waiting on queue.get quickly; timeout remains a fallback.
        try:self.ocr_jobs.put_nowait((time.monotonic(),[]))
        except queue.Full:pass
        if wait:
            current=threading.current_thread()
            for t in (getattr(self,"worker",None),getattr(self,"reader",None)):
                if t and t is not current and t.is_alive():t.join(timeout=2.0)
    def offer(self,value):
        try:self.results.put_nowait(value)
        except queue.Full:
            try:self.results.get_nowait()
            except queue.Empty:pass
            try:self.results.put_nowait(value)
            except queue.Full:pass
    def read_text(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
            ocr=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,det_limit_type='max',det_limit_side_len=1200,use_cls=False)
            while not self.closed.is_set():
                try:stamp,images=self.ocr_jobs.get(timeout=.2)
                except queue.Empty:continue
                lines=[];pull_left=False;pull_right=False;regions_text={};start=time.monotonic()
                for name,frame in images:
                    work=cv2.resize(frame,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC) if name in ('left','right') else frame
                    result,_=ocr(work)
                    found=[str(r[1]) for r in result or [] if float(r[2])>=.72]
                    joined=' '.join(found).lower();regions_text[name]=joined
                    if name=='left':pull_left=('pull' in joined and 'left' in joined) or joined.strip() in ('a','[a]')
                    elif name=='right':pull_right=('pull' in joined and 'right' in joined) or joined.strip() in ('d','[d]')
                    else:lines += found
                with self.lock:
                    self.text=' | '.join(lines);self.text_stamp=stamp;self.pull_left=pull_left;self.pull_right=pull_right;self.pull_stamp=stamp
                    self.ocr_regions=regions_text;self.ocr_ms=(time.monotonic()-start)*1000
        except Exception as e:
            log.exception('Fishing OCR worker crashed')
            with self.lock:self.error='Fishing OCR: '+str(e)
    def capture(self):
        try:
            from capture import Grabber
            grab=Grabber();grab.set_dxgi(self.dxgi)
            last_text=last_save=last_spot=last_active=last_fast=0.;candidate=None;active=False;active_score=0.;active_stamp=0.
            pull_direction=None;pull_confidence=0.;pull_visual_stamp=0.;left_score=right_score=0.
            reel_visible=False;reel_score=0.;reel_stamp=0.;fast_frames={}
            session_log=(self.folder/'observations.jsonl').open('w',encoding='utf-8') if self.folder else None
            try:
                while not self.closed.is_set():
                    now=time.monotonic()
                    if self.io.foreground()!=self.target:
                        self.closed.wait(.05);continue
                    client=self.io.rect(self.target)
                    if min(client[2:])<100:raise RuntimeError('Game is minimized or capture size is invalid')
                    bar=grab.grab(rect_pixels(client,self.regions['bar']))
                    color,red,blue=indicator(bar);bar_fill=bar_fill_estimate(bar)
                    images=[]
                    # Fast visual pass for time-critical REEL and A/D direction.
                    if now-last_fast>=.10:
                        fast_frames={}
                        for name in ('prompt','left','right'):
                            if name in self.regions:fast_frames[name]=grab.grab(rect_pixels(client,self.regions[name]))
                        reel_score=ui_prompt_score(fast_frames.get('prompt'));reel_visible=reel_score>=.50;reel_stamp=now
                        left_score=ui_prompt_score(fast_frames.get('left'));right_score=ui_prompt_score(fast_frames.get('right'))
                        pull_direction,pull_confidence=resolve_pull_direction(left_score,right_score)
                        pull_visual_stamp=now;last_fast=now
                    if now-last_text>=.4 and self.ocr_jobs.empty():
                        for name in ('prompt','result','left','right'):
                            if name in self.regions:
                                frame=fast_frames.get(name)
                                if frame is None:frame=grab.grab(rect_pixels(client,self.regions[name]))
                                images.append((name,frame))
                        self.ocr_jobs.put_nowait((now,images));last_text=now
                    if 'active' in self.regions and now-last_active>=.15:
                        active_frame=grab.grab(rect_pixels(client,self.regions['active']));active,active_score=active_indicator(active_frame);active_stamp=now;last_active=now
                    if 'spot' in self.regions and now-last_spot>.25:
                        candidate=spot_candidate(grab.grab(rect_pixels(client,self.regions['spot'])));last_spot=now
                    with self.lock:text,stamp,pull_left,pull_right,pull_stamp,ocr_regions,ocr_ms,error=self.text,self.text_stamp,self.pull_left,self.pull_right,self.pull_stamp,dict(self.ocr_regions),self.ocr_ms,self.error
                    o=Observation(now,color,text,stamp,active=active if 'active' in self.regions else None,active_stamp=active_stamp,
                                  pull_left=pull_left if 'left' in self.regions else None,pull_right=pull_right if 'right' in self.regions else None,pull_stamp=pull_stamp,
                                  pull_direction=pull_direction,pull_confidence=pull_confidence,pull_visual_stamp=pull_visual_stamp,
                                  reel_visible=reel_visible if 'prompt' in self.regions else None,reel_score=reel_score,reel_stamp=reel_stamp)
                    physical={k:self.io.pressed(v) for k,v in [('A',0x41),('D',0x44),('LMB',1)]}
                    info=dict(red=red,blue=blue,bar_fill=bar_fill,active=active if 'active' in self.regions else None,active_score=active_score if 'active' in self.regions else None,active_stamp=active_stamp,
                              pull_left=pull_left if 'left' in self.regions else None,pull_right=pull_right if 'right' in self.regions else None,pull_stamp=pull_stamp,
                              pull_direction=pull_direction,pull_confidence=pull_confidence,pull_visual_stamp=pull_visual_stamp,
                              pull_left_score=left_score,pull_right_score=right_score,
                              reel_visible=reel_visible if 'prompt' in self.regions else None,reel_score=reel_score,reel_stamp=reel_stamp,
                              ocr_regions=ocr_regions,ocr_ms=ocr_ms,backend=grab.last_backend,spot=candidate,physical=physical)
                    if error:raise RuntimeError(error)
                    if log and now-self.started<300 and self.bytes<100*1024*1024:
                        line=json.dumps(dict(observation=asdict(o),**info))+'\n';log.write(line);self.bytes+=len(line)
                        if now-last_save>=1:
                            extra=[('active',active_frame)] if 'active' in self.regions and 'active_frame' in locals() else []
                            for name,im in [('bar',bar)]+[(f'text-{name}',im) for name,im in images]+extra:
                                p=self.folder/f'{now-self.started:08.3f}-{name}.png';cv2.imwrite(str(p),im);self.bytes+=p.stat().st_size
                            session_log.flush();last_save=now
                    self.offer((o,info,None))
                    self.closed.wait(max(0,.05-(time.monotonic()-now)))
            finally:
                if session_log:session_log.close()
                grab.mss.close()
        except Exception as e:
            log.exception('Fishing capture worker crashed')
            self.offer((None,{},'Fishing capture: '+str(e)))
