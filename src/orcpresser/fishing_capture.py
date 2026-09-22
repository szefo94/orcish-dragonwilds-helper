"""Fishing capture: fast color observations and a separate, bounded OCR worker."""
from dataclasses import asdict
from pathlib import Path
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
        self.lock=threading.Lock();self.text='';self.text_stamp=0.;self.active=False;self.active_stamp=0.;self.ocr_ms=0.;self.error=''
        self.started=time.monotonic();self.folder=None;self.bytes=0
        if record:
            from datetime import datetime
            self.folder=Path(folder)/'fishing_sessions'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            self.folder.mkdir(parents=True)
        self.reader=threading.Thread(target=self.read_text,daemon=True,name='fishing-ocr')
        self.worker=threading.Thread(target=self.capture,daemon=True,name='fishing-capture')
        self.reader.start();self.worker.start()
    def close(self):self.closed.set()
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
                lines=[];active=False;start=time.monotonic()
                for name,frame in images:
                    work=cv2.resize(frame,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC) if name=='active' else frame
                    result,_=ocr(work)
                    found=[str(r[1]) for r in result or [] if float(r[2])>=.75]
                    if name=='active':
                        joined=' '.join(found).lower();active=('stop' in joined and 'fish' in joined)
                    else:lines += found
                with self.lock:
                    self.text=' | '.join(lines);self.text_stamp=stamp;self.active=active;self.active_stamp=stamp;self.ocr_ms=(time.monotonic()-start)*1000
        except Exception as e:
            with self.lock:self.error='Fishing OCR: '+str(e)
    def capture(self):
        try:
            from capture import Grabber
            grab=Grabber();grab.set_dxgi(self.dxgi)
            last_text=last_save=last_spot=0.;candidate=None
            log=(self.folder/'observations.jsonl').open('w',encoding='utf-8') if self.folder else None
            try:
                while not self.closed.is_set():
                    now=time.monotonic()
                    if self.io.foreground()!=self.target:
                        self.closed.wait(.05);continue
                    client=self.io.rect(self.target)
                    if min(client[2:])<100:raise RuntimeError('Game is minimized or capture size is invalid')
                    bar=grab.grab(rect_pixels(client,self.regions['bar']))
                    color,red,blue=indicator(bar)
                    images=[]
                    if now-last_text>=.4 and self.ocr_jobs.empty():
                        for name in ('prompt','result','active'):
                            if name in self.regions:images.append((name,grab.grab(rect_pixels(client,self.regions[name]))))
                        self.ocr_jobs.put_nowait((now,images));last_text=now
                    if 'spot' in self.regions and now-last_spot>.25:
                        candidate=spot_candidate(grab.grab(rect_pixels(client,self.regions['spot'])));last_spot=now
                    with self.lock:text,stamp,active,active_stamp,ocr_ms,error=self.text,self.text_stamp,self.active,self.active_stamp,self.ocr_ms,self.error
                    o=Observation(now,color,text,stamp,active=active,active_stamp=active_stamp)
                    physical={k:self.io.pressed(v) for k,v in [('A',0x41),('D',0x44),('LMB',1)]}
                    info=dict(red=red,blue=blue,ocr_ms=ocr_ms,backend=grab.last_backend,spot=candidate,physical=physical)
                    if error:raise RuntimeError(error)
                    if log and now-self.started<300 and self.bytes<100*1024*1024:
                        line=json.dumps(dict(observation=asdict(o),**info))+'\n';log.write(line);self.bytes+=len(line)
                        if now-last_save>=1:
                            for name,im in [('bar',bar)]+[(f'text-{name}',im) for name,im in images]:
                                p=self.folder/f'{now-self.started:08.3f}-{name}.png';cv2.imwrite(str(p),im);self.bytes+=p.stat().st_size
                            log.flush();last_save=now
                    self.offer((o,info,None))
                    self.closed.wait(max(0,.05-(time.monotonic()-now)))
            finally:
                if log:log.close()
                grab.mss.close()
        except Exception as e:self.offer((None,{},str(e)))
