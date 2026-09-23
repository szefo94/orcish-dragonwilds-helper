"""Shared non-activating four-corner HUD for minimized / opacity-0 operation."""
import ctypes, sys, tkinter as tk

PALETTES={
    "tl":("#14251b","#39ff88","#e9fff1"),
    "tr":("#17172a","#8f7cff","#f2efff"),
    "bl":("#2a1c10","#ff9e3d","#fff0dc"),
    "br":("#11242a","#35d9ff","#e7fbff"),
    "attention":("#2a2110","#ffd84d","#fff6c7"),
    "danger":("#2b1111","#ff5a5a","#ffe9e9"),
}

class StatusOverlay:
    def __init__(self,root):
        self.window=tk.Toplevel(root);self.window.withdraw();self.window.overrideredirect(True)
        self.window.configure(bg="#010101");self.window.attributes("-topmost",True);self.window.attributes("-alpha",.55)
        self.canvas=tk.Canvas(self.window,bg="#010101",highlightthickness=0);self.canvas.pack(fill="both",expand=True)
        self.available=False
        if sys.platform=="win32":
            try:
                self.window.attributes("-transparentcolor","#010101");self.window.update_idletasks()
                u=ctypes.windll.user32
                from ctypes import wintypes as w
                u.GetAncestor.argtypes=[w.HWND,w.UINT];u.GetAncestor.restype=w.HWND
                hwnd=u.GetAncestor(self.window.winfo_id(),2)
                get=u.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p)==8 else u.GetWindowLongW
                set_=u.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p)==8 else u.SetWindowLongW
                get.argtypes=[w.HWND,ctypes.c_int];get.restype=ctypes.c_ssize_t
                set_.argtypes=[w.HWND,ctypes.c_int,ctypes.c_ssize_t];set_.restype=ctypes.c_ssize_t
                set_(hwnd,-20,get(hwnd,-20)|0x08000000|0x00000020|0x00080000|0x00000080)
                u.SetWindowDisplayAffinity.argtypes=[w.HWND,w.DWORD]
                u.ShowWindow.argtypes=[w.HWND,ctypes.c_int]
                self.hwnd=hwnd;self.available=bool(u.SetWindowDisplayAffinity(hwnd,0x11))
            except Exception:self.available=False

    def _panel(self,pos,w,h,title,lines):
        margin=max(12,min(28,int(min(w,h)*.018)))
        max_w=max(300,min(620,int(w*.31)))
        clean=[str(x).replace("\n"," · ").strip() for x in lines if str(x).strip()][:6]
        panel_h=36+20*max(1,len(clean))
        if pos=="tl":x1,y1=margin,margin
        elif pos=="tr":x1,y1=max(margin,w-margin-max_w),margin
        elif pos=="bl":x1,y1=margin,max(margin,h-margin-panel_h)
        else:x1,y1=max(margin,w-margin-max_w),max(margin,h-margin-panel_h)
        # Clamp after sizing so ultra-wide, tiny, or partially restored clients never draw off-screen.
        x1=max(0,min(x1,max(0,w-max_w)));y1=max(0,min(y1,max(0,h-panel_h)))
        x2=min(w,x1+max_w);y2=min(h,y1+panel_h)
        bg,edge,fg=PALETTES[pos]
        c=self.canvas
        c.create_rectangle(x1,y1,x2,y2,fill=bg,outline=edge,width=2)
        c.create_text(x1+10,y1+8,text=title,anchor="nw",fill=edge,font=("Consolas",10,"bold"))
        for i,line in enumerate(clean):
            c.create_text(x1+10,y1+31+i*20,text=line,anchor="nw",fill=fg,font=("Consolas",9),width=max(50,x2-x1-20))

    def _revive(self):
        if not self.available:return False
        try:
            self.window.deiconify();self.window.attributes("-topmost",True);self.window.attributes("-alpha",.55)
            self.window.update_idletasks();ctypes.windll.user32.ShowWindow(self.hwnd,4);return True
        except Exception:return False

    def show(self,client,panels,attention=None,danger=False):
        if not self._revive():return
        x,y,w,h=client
        if w<180 or h<120:return self.hide()
        self.window.geometry(f"{w}x{h}{x:+d}{y:+d}");self.window.update_idletasks()
        ctypes.windll.user32.ShowWindow(self.hwnd,4)
        self.canvas.delete("all")
        for pos in ("tl","tr","bl","br"):
            data=panels.get(pos) if isinstance(panels,dict) else None
            if data:
                title,lines=data
                self._panel(pos,w,h,title,lines)
        if attention:
            msg=str(attention).replace("\n"," · ")[:150]
            bw=min(max(260,8*len(msg)+34),max(260,int(w*.46)))
            bh=34;x1=max(8,min((w-bw)//2,max(8,w-bw-8)));y1=10
            bg,edge,fg=PALETTES["danger" if danger else "attention"]
            self.canvas.create_rectangle(x1,y1,x1+bw,y1+bh,fill=bg,outline=edge,width=2)
            self.canvas.create_text(x1+bw/2,y1+17,text="↩ APP · "+msg,fill=fg,font=("Consolas",9,"bold"))

    def hide(self):
        try:self.window.withdraw()
        except Exception:pass

    def close(self):
        try:self.window.destroy()
        except Exception:pass
