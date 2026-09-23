"""Common non-activating status HUD shown over the game when the main UI is minimized."""
import ctypes, sys, tkinter as tk

class StatusOverlay:
    def __init__(self,root):
        self.window=tk.Toplevel(root);self.window.withdraw();self.window.overrideredirect(True)
        self.window.configure(bg="#010101");self.window.attributes("-topmost",True)
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

    def show(self,client,title,lines):
        if not self.available:return
        x,y,w,h=client
        box_w=min(560,max(360,int(w*.34)));box_h=38+22*min(6,max(1,len(lines)))
        left=max(14,w-box_w-18);top=18
        self.window.geometry(f"{w}x{h}{x:+d}{y:+d}");self.window.update_idletasks()
        ctypes.windll.user32.ShowWindow(self.hwnd,4)
        c=self.canvas;c.delete("all")
        c.create_rectangle(left,top,left+box_w,top+box_h,fill="#172012",outline="#98c657",width=2)
        c.create_text(left+12,top+10,text=title,anchor="nw",fill="#f0d698",font=("Consolas",11,"bold"))
        y0=top+34
        for i,line in enumerate(lines[:6]):
            c.create_text(left+12,y0+i*22,text=str(line),anchor="nw",fill="#e6d8b0",font=("Consolas",9),width=box_w-24)

    def hide(self):
        try:self.window.withdraw()
        except Exception:pass

    def close(self):
        try:self.window.destroy()
        except Exception:pass
