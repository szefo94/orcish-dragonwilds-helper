"""Offline Scout screenshot analyzer and human review queue."""
from __future__ import annotations
import argparse,csv,os,time
from pathlib import Path
import cv2
from aim_lab import impact_features,moving_candidates,target_hud_candidates

EXTRA=["analysis_status","suggested_label","suggestion_reason","review_status","reviewed_at"]
LABELS=["target","head","moose_body","moose_head","deer_body","deer_head","chicken_body","chicken_head",
        "runestone","item_pickup","inventory","hit","crit","miss","hud","background","other"]

def latest_session(root="data"):
    p=Path(root)/"scout_sessions"
    if not p.exists():return None
    xs=[x for x in p.iterdir() if x.is_dir() and (x/"labels.csv").exists()]
    return max(xs,key=lambda x:x.stat().st_mtime) if xs else None

def read_labels(path):
    with Path(path).open("r",encoding="utf-8",newline="") as f:
        rd=csv.DictReader(f);fields=list(rd.fieldnames or []);rows=[dict(x) for x in rd]
    for x in EXTRA:
        if x not in fields:fields.append(x)
    for r in rows:
        for x in EXTRA:r.setdefault(x,"")
    return fields,rows

def write_labels(path,fields,rows):
    path=Path(path);tmp=path.with_suffix(".csv.tmp")
    with tmp.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    os.replace(tmp,path)

def load_image(session,row):
    p=Path(session)/(row.get("image") or "")
    return cv2.imread(str(p)) if p.exists() else None

def analyze_rows(session,rows,reanalyze=False):
    groups={}
    for r in rows:groups.setdefault(r.get("sample_id",""),[]).append(r)
    changed=0
    for grp in groups.values():
        grp.sort(key=lambda r:int(float(r.get("delay_ms") or 0)));prev=None
        for r in grp:
            img=load_image(session,r)
            if reanalyze or not (r.get("analysis_status") or "").strip():
                if img is None:status,sug,reason="error","missing_image","image missing/unreadable"
                else:
                    delay=int(float(r.get("delay_ms") or 0));focus=r.get("focus_source") or "unknown"
                    impact=impact_features(img,prev) if prev is not None and prev.shape==img.shape else {}
                    motions=moving_candidates(img,prev,3) if prev is not None and prev.shape==img.shape else []
                    huds=target_hud_candidates(img,2)
                    hit=impact.get("change",0)>.025 and (impact.get("bright",0)>.015 or impact.get("warm",0)>.003 or impact.get("yellow",0)>.003)
                    if huds:
                        sug="close_aimed_target"
                        reason=f"green target HP HUD detected ({huds[0].get('reason')}); confirm species/body/head"
                    elif delay==0:
                        sug="aim_context" if focus=="crosshair" else "cursor_context"
                        reason=f"first frame; focus={focus}; tell reviewer what is under focus"
                    elif hit:
                        sug="possible_hit_or_crit";reason=f"+{delay}ms visual change={impact.get('change',0):.3f}; confirm hit/crit/miss"
                    elif motions:
                        sug="moving_target_or_residual";reason=f"+{delay}ms {motions[0].get('reason','motion')}"
                    else:sug,reason="review",f"+{delay}ms no strong automatic cue"
                    status="proposed"
                r["analysis_status"]=status;r["suggested_label"]=sug;r["suggestion_reason"]=reason;changed+=1
            if img is not None:prev=img
    return changed

def counts(rows):
    a=sum(bool((r.get("analysis_status") or "").strip()) for r in rows)
    v=sum(r.get("review_status") in ("confirmed","skipped") for r in rows)
    return len(rows),a,v

class ReviewUI:
    def __init__(self,session,fields,rows):
        import tkinter as tk
        from PIL import Image,ImageTk
        self.tk=tk;self.Image=Image;self.ImageTk=ImageTk;self.s=Path(session);self.f=fields;self.rows=rows;self.i=0;self.photo=None
        self.root=tk.Tk();self.root.title("Scout Review");self.root.geometry("1180x820")
        self.label=tk.StringVar();self.notes=tk.StringVar();self.meta=tk.StringVar();self.reason=tk.StringVar()
        self.pic=tk.Label(self.root,bg="#111");self.pic.pack(fill="both",expand=True,padx=8,pady=8)
        tk.Label(self.root,textvariable=self.meta,font=("Consolas",10,"bold")).pack(fill="x",padx=8)
        tk.Label(self.root,textvariable=self.reason,wraplength=1100,justify="left").pack(fill="x",padx=8)
        e=tk.Frame(self.root);e.pack(fill="x",padx=8,pady=4)
        tk.Label(e,text="What do you see?").pack(side="left");tk.Entry(e,textvariable=self.label,width=25).pack(side="left",padx=5)
        tk.Label(e,text="notes").pack(side="left");tk.Entry(e,textvariable=self.notes).pack(side="left",fill="x",expand=True,padx=5)
        b=tk.Frame(self.root);b.pack(fill="x",padx=8)
        for name in LABELS:tk.Button(b,text=name,command=lambda x=name:self.label.set(x)).pack(side="left",padx=2)
        n=tk.Frame(self.root);n.pack(fill="x",padx=8,pady=8)
        tk.Button(n,text="PREV",command=lambda:self.move(-1)).pack(side="left")
        tk.Button(n,text="CONFIRM + NEXT",command=self.confirm).pack(side="left",padx=5)
        tk.Button(n,text="SKIP + NEXT",command=self.skip).pack(side="left")
        tk.Button(n,text="NEXT",command=lambda:self.move(1)).pack(side="left",padx=5)
        tk.Button(n,text="PROBE MAP",command=self.probe).pack(side="right")
        self.jump(0)

    def save_fields(self):
        r=self.rows[self.i];r["label"]=self.label.get().strip();r["notes"]=self.notes.get().strip()

    def load(self):
        r=self.rows[self.i];self.label.set(r.get("label",""));self.notes.set(r.get("notes",""))
        total,an,rev=counts(self.rows)
        self.meta.set(f"{self.i+1}/{total} | analyzed={an} | user-reviewed={rev} | auto={r.get('suggested_label') or 'not analyzed'}")
        self.reason.set(r.get("suggestion_reason") or "")
        img=load_image(self.s,r)
        if img is not None:
            img=cv2.cvtColor(img,cv2.COLOR_BGR2RGB);im=self.Image.fromarray(img);im.thumbnail((1120,590))
            self.photo=self.ImageTk.PhotoImage(im);self.pic.configure(image=self.photo,text="")
        else:self.pic.configure(image="",text="missing image")

    def move(self,d):
        self.save_fields();self.i=max(0,min(len(self.rows)-1,self.i+d));self.load()

    def jump(self,start):
        for j in list(range(start,len(self.rows)))+list(range(0,start)):
            if self.rows[j].get("review_status") not in ("confirmed","skipped"):self.i=j;break
        self.load()

    def commit(self,status):
        self.save_fields();r=self.rows[self.i];r["review_status"]=status;r["reviewed_at"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
        write_labels(self.s/"labels.csv",self.f,self.rows);self.jump((self.i+1)%len(self.rows))

    def confirm(self):
        r=self.rows[self.i]
        if not self.label.get().strip() and r.get("suggested_label"):self.label.set(r["suggested_label"])
        self.commit("confirmed")

    def skip(self):self.commit("skipped")

    def probe(self):
        sid=self.rows[self.i].get("sample_id","");p=self.s/"sample_context"/f"{sid}_probe_area.jpg"
        if not p.exists():return
        import tkinter as tk
        img=cv2.imread(str(p));img=cv2.cvtColor(img,cv2.COLOR_BGR2RGB);im=self.Image.fromarray(img);im.thumbnail((1200,700))
        win=tk.Toplevel(self.root);ph=self.ImageTk.PhotoImage(im);lab=tk.Label(win,image=ph);lab.image=ph;lab.pack()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW",lambda:(self.save_fields(),write_labels(self.s/"labels.csv",self.f,self.rows),self.root.destroy()))
        self.root.mainloop()

def main():
    ap=argparse.ArgumentParser();ap.add_argument("session",nargs="?");ap.add_argument("--latest",action="store_true")
    ap.add_argument("--analyze-only",action="store_true");ap.add_argument("--reanalyze",action="store_true");args=ap.parse_args()
    session=latest_session() if args.latest or not args.session else Path(args.session)
    if not session:raise SystemExit("No Scout session with labels.csv found")
    fields,rows=read_labels(Path(session)/"labels.csv");changed=analyze_rows(session,rows,args.reanalyze)
    if changed:write_labels(Path(session)/"labels.csv",fields,rows)
    total,an,rev=counts(rows);print(f"{session}: total={total}, analyzed={an}, human-reviewed={rev}, automatic updates={changed}")
    if not args.analyze_only:ReviewUI(session,fields,rows).run()

if __name__=="__main__":main()
