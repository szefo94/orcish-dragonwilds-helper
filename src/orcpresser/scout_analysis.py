"""Read-only analyzer for Scout session logs.

Raw logs under data/scout_sessions are NEVER modified. Reports are written to
data/scout_reports and include SHA-256 hashes of every source file used.
"""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json, math, statistics, time

RAW_FILES=("manifest.json","summary.json","vision.jsonl","controller.jsonl","process.jsonl")

def sha256_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def load_json(path, default=None):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError):return default

def load_jsonl(path):
    out=[]
    try:
        with Path(path).open("r",encoding="utf-8") as f:
            for n,line in enumerate(f,1):
                line=line.strip()
                if not line:continue
                try:out.append(json.loads(line))
                except ValueError:out.append({"_parse_error":n,"_raw":line[:500]})
    except OSError:pass
    return out

def percentile(values,p):
    xs=sorted(float(x) for x in values if isinstance(x,(int,float)) and math.isfinite(float(x)))
    if not xs:return None
    if len(xs)==1:return xs[0]
    k=(len(xs)-1)*p/100.0;lo=int(math.floor(k));hi=int(math.ceil(k))
    return xs[lo] if lo==hi else xs[lo]+(xs[hi]-xs[lo])*(k-lo)

def stats(values):
    xs=[float(x) for x in values if isinstance(x,(int,float)) and math.isfinite(float(x))]
    if not xs:return {"count":0}
    return {"count":len(xs),"min":min(xs),"median":statistics.median(xs),"p95":percentile(xs,95),"max":max(xs),"mean":statistics.fmean(xs)}

def source_hashes(session):
    hashes={}
    for name in RAW_FILES:
        p=Path(session)/name
        if p.is_file():hashes[name]=sha256_file(p)
    return hashes

def _state_transitions(controller):
    out=[];last=None
    for e in sorted(controller,key=lambda x:x.get("mono",0)):
        if e.get("signal")!="fishing_decision":continue
        value=e.get("value") or {};state=value.get("state")
        if state and state!=last:
            out.append({"mono":e.get("mono"),"state":state,"held":value.get("held"),"reason":(e.get("details") or {}).get("reason")})
            last=state
    return out

def _prompt_transitions(vision):
    out=[];sentinel=object();last=sentinel
    for e in sorted(vision,key=lambda x:x.get("mono",0)):
        if e.get("signal")!="prompt":continue
        v=e.get("value");key=None if v is None else (v.get("action"),v.get("key"),bool(v.get("hold")),v.get("source"))
        if last is sentinel or key!=last:
            out.append({"mono":e.get("mono"),"prompt":v,"confidence":e.get("confidence")});last=key
    return out

def analyze_session(session):
    session=Path(session)
    manifest=load_json(session/"manifest.json",{}) or {};summary=load_json(session/"summary.json",{}) or {}
    vision=load_jsonl(session/"vision.jsonl");controller=load_jsonl(session/"controller.jsonl");process=load_jsonl(session/"process.jsonl")
    all_events=vision+controller+process
    valid=[e for e in all_events if isinstance(e,dict) and isinstance(e.get("mono"),(int,float))]
    monos=[e["mono"] for e in valid]
    report={"schema":1,"session":session.name,"session_path":str(session),"generated_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
            "domain":manifest.get("domain"),"run":manifest.get("run"),"session_id":manifest.get("session_id"),
            "source_hashes":source_hashes(session),"raw_logs_preserved":True,
            "counts":{"vision":len(vision),"controller":len(controller),"process":len(process),"parse_errors":sum(1 for e in all_events if "_parse_error" in e)},
            "timeline":{"start_mono":min(monos) if monos else None,"end_mono":max(monos) if monos else None,"duration_s":(max(monos)-min(monos)) if len(monos)>=2 else 0},
            "latency_ms":stats([e.get("latency_ms") for e in vision]),"fresh_ms":stats([e.get("fresh_ms") for e in vision]),
            "manifest":manifest,"session_summary":summary}
    if manifest.get("domain")=="fishing":
        obs=[e for e in vision if e.get("signal")=="fishing_observation"]
        report["fishing"]={"observations":len(obs),"ocr_ms":stats([(e.get("details") or {}).get("ocr_ms") for e in obs]),
            "positive_frames":{"stop":sum(1 for e in obs if (e.get("value") or {}).get("stop") is True),
                               "pull_left":sum(1 for e in obs if (e.get("value") or {}).get("pull_left") is True),
                               "pull_right":sum(1 for e in obs if (e.get("value") or {}).get("pull_right") is True),
                               "reel_text":sum(1 for e in obs if "reel" in str((e.get("value") or {}).get("text","")).lower())},
            "state_transitions":_state_transitions(controller)}
    elif manifest.get("domain")=="auto_picker":
        prompts=[e for e in vision if e.get("signal")=="prompt"]
        report["auto_picker"]={"observations":len(prompts),"approved":sum(1 for e in prompts if e.get("value") is not None),
            "sent_decisions":sum(1 for e in controller if e.get("signal")=="decision" and (e.get("value") or {}).get("sent")),
            "prompt_transitions":_prompt_transitions(vision)}
    return report

def _fmt(v): return "—" if v is None else f"{v:.1f}"

def markdown(report):
    lines=[f"# Scout analysis — {report['session']}","",f"- Domain: **{report.get('domain')}**",f"- Run: **{report.get('run')}**",
           f"- Duration: **{report['timeline'].get('duration_s',0):.3f} s**","- Raw logs preserved: **yes**",
           f"- Parse errors: **{report['counts'].get('parse_errors',0)}**","","## Timing",""]
    lat=report.get("latency_ms",{});fresh=report.get("fresh_ms",{})
    lines.append(f"- Vision latency: n={lat.get('count',0)}, median={_fmt(lat.get('median'))} ms, p95={_fmt(lat.get('p95'))} ms")
    lines.append(f"- Vision freshness at controller: n={fresh.get('count',0)}, median={_fmt(fresh.get('median'))} ms, p95={_fmt(fresh.get('p95'))} ms")
    if "fishing" in report:
        f=report["fishing"];lines+=["","## Fishing","",f"- Observations: {f['observations']}",
            "- Positive frames: "+", ".join(f"{k}={v}" for k,v in f["positive_frames"].items()),"","### State transitions",""]
        for t in f["state_transitions"]:lines.append(f"- {t.get('mono')}: {t.get('state')} · held={t.get('held') or 'none'} · {t.get('reason') or ''}")
    if "auto_picker" in report:
        a=report["auto_picker"];lines+=["","## Auto Picker","",f"- Prompt observations: {a['observations']}",f"- Approved observations: {a['approved']}",
            f"- Sent decisions: {a['sent_decisions']}","","### Prompt transitions",""]
        for t in a["prompt_transitions"][:100]:lines.append(f"- {t.get('mono')}: {t.get('prompt')}")
    lines+=["","## Source hashes",""]
    for name,h in report.get("source_hashes",{}).items():lines.append(f"- {name}: {h}")
    lines+=["","The analyzer is read-only with respect to data/scout_sessions; generated reports are stored separately."]
    return "\n".join(lines)+"\n"

def latest_session(root):
    p=Path(root)/"scout_sessions";dirs=[x for x in p.iterdir() if x.is_dir()] if p.is_dir() else []
    if not dirs:raise FileNotFoundError("No Scout sessions found")
    return max(dirs,key=lambda x:x.stat().st_mtime)

def write_report(session,data_root=None):
    session=Path(session);report=analyze_session(session);root=Path(data_root) if data_root else session.parent.parent
    outdir=root/"scout_reports";outdir.mkdir(parents=True,exist_ok=True);base=outdir/session.name
    jp=base.with_suffix(".json");mp=base.with_suffix(".md")
    jp.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding="utf-8");mp.write_text(markdown(report),encoding="utf-8")
    return jp,mp,report

def main(argv=None):
    ap=argparse.ArgumentParser(description="Analyze Scout logs without modifying raw sessions.")
    ap.add_argument("session",nargs="?",help="Path to one data/scout_sessions/<session> directory")
    ap.add_argument("--data",default="data",help="Data root used by --latest and report output")
    ap.add_argument("--latest",action="store_true",help="Analyze the newest Scout session")
    args=ap.parse_args(argv)
    session=latest_session(args.data) if args.latest or not args.session else Path(args.session)
    j,m,_=write_report(session,args.data)
    print(f"Analyzed {session}");print(f"JSON: {j}");print(f"Markdown: {m}");print("Raw Scout logs were read only and left unchanged.")
    return 0

if __name__=="__main__":raise SystemExit(main())
