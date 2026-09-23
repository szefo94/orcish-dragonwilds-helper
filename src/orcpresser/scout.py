"""Local parallel telemetry recorder for Scout research.

One recorder = one Preview/Live Auto Picker or Fishing run.  It never reads or
writes game memory; Phase A records the existing visual/controller stream plus
ordinary OS process metadata so later tools can correlate sources on one
monotonic timeline.
"""
from __future__ import annotations
from pathlib import Path
import json, os, platform, time, uuid, threading

MAX_BYTES=20*1024*1024

class ScoutRecorder:
    def __init__(self, root, domain, run, pid=None, metadata=None, clock=time.monotonic):
        self.clock=clock;self.domain=domain;self.run=run;self.pid=pid
        self.session_id=str(uuid.uuid4());self.seq=0;self.bytes=0;self.closed=False
        stamp=time.strftime('%Y%m%d-%H%M%S')
        self.folder=Path(root)/'scout_sessions'/f'{stamp}-{self.session_id[:8]}'
        self.folder.mkdir(parents=True,exist_ok=True)
        self.streams={};self.lock=threading.RLock()
        manifest={
            'schema':1,'session_id':self.session_id,'domain':domain,'run':run,
            'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'pid':pid,'platform':platform.platform(),'metadata':metadata or {},
            'scope':'single-player/private research','max_bytes':MAX_BYTES
        }
        self._write_json(self.folder/'manifest.json',manifest)
        if pid:self.process_snapshot(pid)

    def _write_json(self,path,value):
        path.write_text(json.dumps(value,indent=2,ensure_ascii=False,default=str),encoding='utf-8')

    def _stream(self,name):
        f=self.streams.get(name)
        if f is None:
            f=(self.folder/(name+'.jsonl')).open('a',encoding='utf-8')
            self.streams[name]=f
        return f

    def event(self,source,signal,value=None,confidence=None,mono=None,latency_ms=None,fresh_ms=None,details=None,stream=None):
        with self.lock:
            if self.closed or self.bytes>=MAX_BYTES:return False
            self.seq+=1
            m=self.clock() if mono is None else float(mono)
            obj={'session_id':self.session_id,'seq':self.seq,'mono':m,
                 'wall_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                 'source':source,'domain':self.domain,'signal':signal,'value':value}
            if confidence is not None:obj['confidence']=float(confidence)
            if latency_ms is not None:obj['latency_ms']=float(latency_ms)
            if fresh_ms is not None:obj['fresh_ms']=float(fresh_ms)
            if details:obj['details']=details
            line=json.dumps(obj,ensure_ascii=False,default=str,separators=(',',':'))+'\n'
            data=line.encode('utf-8')
            if self.bytes+len(data)>MAX_BYTES:return False
            f=self._stream(stream or source);f.write(line);f.flush();self.bytes+=len(data)
            return True

    def process_snapshot(self,pid):
        try:
            import psutil
            p=psutil.Process(pid)
            with p.oneshot():
                d={'pid':pid,'name':p.name(),'exe':p.exe(),'create_time':p.create_time(),
                   'rss':p.memory_info().rss,'threads':p.num_threads()}
            try:
                maps=p.memory_maps(grouped=True)
                d['modules']=[os.path.basename(m.path) for m in maps[:300] if m.path]
            except (psutil.Error,OSError):d['modules']=[]
            self.event('process','snapshot',d,stream='process')
        except Exception as e:
            self.event('process','snapshot_error',type(e).__name__+': '+str(e),stream='process')

    def close(self,reason='stopped'):
        with self.lock:
            if self.closed:return
            self.event('controller','session_end',reason,stream='controller')
            self.closed=True
            for f in self.streams.values():
                try:f.close()
                except OSError:pass
            try:self._write_json(self.folder/'summary.json',{'session_id':self.session_id,'events':self.seq,'bytes':self.bytes,'reason':reason})
            except OSError:pass
