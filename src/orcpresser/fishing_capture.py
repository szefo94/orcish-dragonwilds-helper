"""Fishing capture: fast color observations and a separate, bounded OCR worker."""
from dataclasses import asdict
from pathlib import Path
import json, queue, threading, time
import cv2
import numpy as np
from fishing import Observation


def indicator(frame):
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    saturated=(hsv[:,:,1]>100)&(hsv[:,:,2]>90)
    red=float(np.mean(saturated&((hsv[:,:,0]<12)|(hsv[:,:,0]>168))))
    blue=float(np.mean(saturated&(hsv[:,:,0]>90)&(hsv[:,:,0]<135)))
    color='red' if red>.035 and red>blue*1.4 else 'blue' if blue>.035 and blue>red*1.4 else 'unknown'
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
        self.lock=threading.Lock();self.text='';self.text_stamp=0.;self.ocr_ms=0.;self.error=''
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
                lines=[];start=time.monotonic()
                for frame in images:
                    result,_=ocr(frame)
                    lines += [str(r[1]) for r in result or [] if float(r[2])>=.8]
                with self.lock:self.text=' | '.join(lines);self.text_stamp=stamp;self.ocr_ms=(time.monotonic()-start)*1000
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
                        for name in ('prompt','result'):
                            if name in self.regions:images.append(grab.grab(rect_pixels(client,self.regions[name])))
                        self.ocr_jobs.put_nowait((now,images));last_text=now
                    if 'spot' in self.regions and now-last_spot>.25:
                        candidate=spot_candidate(grab.grab(rect_pixels(client,self.regions['spot'])));last_spot=now
                    with self.lock:text,stamp,ocr_ms,error=self.text,self.text_stamp,self.ocr_ms,self.error
                    o=Observation(now,color,text,stamp)
                    physical={k:self.io.pressed(v) for k,v in [('A',0x41),('D',0x44),('LMB',1)]}
                    info=dict(red=red,blue=blue,ocr_ms=ocr_ms,backend=grab.last_backend,spot=candidate,physical=physical)
                    if error:raise RuntimeError(error)
                    if log and now-self.started<300 and self.bytes<100*1024*1024:
                        line=json.dumps(dict(observation=asdict(o),**info))+'\n';log.write(line);self.bytes+=len(line)
                        if now-last_save>=1:
                            for name,im in [('bar',bar)]+[(f'text{i}',im) for i,im in enumerate(images)]:
                                p=self.folder/f'{now-self.started:08.3f}-{name}.png';cv2.imwrite(str(p),im);self.bytes+=p.stat().st_size
                            log.flush();last_save=now
                    self.offer((o,info,None))
                    self.closed.wait(max(0,.05-(time.monotonic()-now)))
            finally:
                if log:log.close()
                grab.mss.close()
        except Exception as e:self.offer((None,{},str(e)))
