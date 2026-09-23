"""Non-activating, click-through Windows overlay excluded from screen capture."""
import ctypes
import sys
import tkinter as tk

class FishingOverlay:
    def __init__(self,root):
        self.window=tk.Toplevel(root);self.window.withdraw();self.window.overrideredirect(True)
        self.window.configure(bg='#010101');self.window.attributes('-topmost',True);self.window.attributes('-alpha',.55)
        self.canvas=tk.Canvas(self.window,bg='#010101',highlightthickness=0);self.canvas.pack(fill='both',expand=True)
        self.available=False
        if sys.platform=='win32':
            try:
                self.window.attributes('-transparentcolor','#010101')
                self.window.update_idletasks()
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
                self.hwnd=hwnd
                u.ShowWindow.argtypes=[w.HWND,ctypes.c_int]
                self.available=bool(u.SetWindowDisplayAffinity(hwnd,0x11))
            except Exception:self.available=False
    def _revive(self):
        if not self.available:return False
        try:
            self.window.deiconify();self.window.attributes("-topmost",True);self.window.attributes("-alpha",.55)
            self.window.update_idletasks();ctypes.windll.user32.ShowWindow(self.hwnd,4);return True
        except Exception:return False
    def show(self,client,regions,caption,info):
        if not self._revive():return
        x,y,w,h=client;self.window.geometry(f'{w}x{h}{x:+d}{y:+d}')
        self.window.update_idletasks()
        ctypes.windll.user32.ShowWindow(self.hwnd,4)  # SW_SHOWNOACTIVATE
        c=self.canvas;c.delete('all')
        for name,(l,t,r,b) in regions.items():
            x1,y1,x2,y2=l*w,t*h,(l+r)*w,(t+b)*h
            c.create_rectangle(x1,y1,x2,y2,outline='#a4d666',width=2)
            label='REEL' if name=='prompt' else name.upper()
            c.create_text(x1,max(10,y1-12),text=label,anchor='w',fill='#f0d698',font=('Segoe UI',10,'bold'))
            if name=='spot' and info.get('spot'):
                sx,sy,sw,sh=info['spot'];c.create_oval(x1+sx,y1+sy,x1+sx+sw,y1+sy+sh,outline='#f0d698',width=2)
        c.create_text(20,25,text=caption,anchor='nw',fill='#f0d698',font=('Consolas',12,'bold'),width=max(300,w-40))
        if info.get('app_minimized'):
            running=bool(info.get('running'));preview=bool(info.get('preview'))
            mode='PREVIEW' if preview else 'LIVE'
            state=str(info.get('state') or 'IDLE');held=str(info.get('held') or 'none')
            status=('● '+mode+' ACTIVE' if running else '○ FISHING IDLE')+'  |  '+state+'  |  input: '+held
            # High-contrast compact badge remains visible while the main window is minimized.
            tw=min(max(360,int(w*.36)),max(360,w-40))
            x1=max(20,w-tw-20);x2=w-20
            c.create_rectangle(x1,18,x2,56,fill='#172012',outline='#98c657' if running else '#9ba087',width=2)
            c.create_text(x1+12,37,text=status,anchor='w',fill='#98c657' if running else '#e6d8b0',font=('Consolas',11,'bold'),width=max(100,tw-24))
    def hide(self):self.window.withdraw()
    def close(self):self.window.destroy()
