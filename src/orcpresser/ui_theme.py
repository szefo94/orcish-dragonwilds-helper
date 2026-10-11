"""One look for the Tk shell and every feature panel.

Warcraft-style command post: near-black stone background, bronze panels inside a thin gold frame,
parchment text, green for "ready / active", ember red for STOP. Everything is drawn with Tk
primitives (no image assets), so the theme works on a bare Python + Tcl/Tk install.

Rules that keep the UI from repeating itself:
- a section title is a `heading()`; there is no numbering, and feature panels never add a title of
  their own (the shell shows one tool title per tab);
- runtime messages go into the TOOL OUTPUT column (`card_text`), never into the settings column;
- buttons are always `RuneButton`s sized to their label, so no caption is ever clipped;
- instructions that apply to every tab (global control bar, hotkeys) exist once, in the shell.
"""
import tkinter as tk
from tkinter import ttk, font as tkfont

BG='#0d0f0b'        # window stone
PANEL='#1b1f16'     # bronze panel
INSET='#0b0d09'     # sunken card
EDGE='#3b4030'      # quiet separators
GOLD='#cfae56'      # frames, headings
GOLD_DIM='#7d6a36'  # inactive frames
BONE='#e8dcb5'      # body text
GREEN='#9ad15a'     # ready / active / live
MUTED='#8f957f'     # captions
RED='#cf5a3f'       # stop / danger
TEAL='#4fc3c5'      # informational accent

FONT_TITLE=('Georgia',26,'bold')
FONT_HEAD=('Georgia',11,'bold')
FONT_BTN=('Georgia',10,'bold')
FONT_UI=('Segoe UI',10)
FONT_SMALL=('Segoe UI',9)
FONT_TINY=('Segoe UI',8)
FONT_MONO=('Consolas',9)
FONT_MONO_B=('Consolas',10,'bold')

COLORS={'BG':BG,'PANEL':PANEL,'INSET':INSET,'GOLD':GOLD,'BONE':BONE,'GREEN':GREEN,'MUTED':MUTED,'RED':RED}

_FILL={'normal':('#2a2619','#36301f'),'primary':('#2b4423','#365a2c'),'stop':('#46221b','#5a2a21'),'tab':('#24211a','#302b1f')}


def init_styles(root):
    """ttk pieces that cannot be coloured through plain Tk options."""
    s=ttk.Style(root)
    try:s.theme_use('clam')
    except tk.TclError:pass
    s.configure('Orc.TCombobox',fieldbackground=INSET,background=PANEL,foreground=BONE,arrowcolor=GOLD,bordercolor=EDGE,
                lightcolor=PANEL,darkcolor=PANEL,selectbackground='#2f3a24',selectforeground=BONE)
    s.map('Orc.TCombobox',fieldbackground=[('readonly',INSET)],foreground=[('readonly',BONE)])
    s.configure('Orc.Vertical.TScrollbar',background=PANEL,troughcolor=BG,bordercolor=BG,arrowcolor=GOLD,lightcolor=PANEL,darkcolor=PANEL)
    root.option_add('*TCombobox*Listbox.background',INSET);root.option_add('*TCombobox*Listbox.foreground',BONE)
    root.option_add('*TCombobox*Listbox.selectBackground','#2f3a24');root.option_add('*TCombobox*Listbox.selectForeground',BONE)


class RuneButton(tk.Canvas):
    """Chamfered bronze button with gold studs. Sizes itself to its label; `label`, `enabled` and
    `active` can be changed and `draw()` re-renders (the shell does this for PREVIEW/LIVE/STOP)."""
    def __init__(self,parent,text,command,width=None,height=38,kind='normal'):
        super().__init__(parent,width=width or 10,height=height,bg=parent['bg'],highlightthickness=0,cursor='hand2')
        self.label=text;self.command=command;self.kind=kind if kind in _FILL else 'normal'
        self.active=False;self.hover=False;self.enabled=True;self.min_w=width;self.h=height
        self.bind('<Button-1>',lambda e:self.invoke());self.bind('<Enter>',lambda e:self.set_hover(True))
        self.bind('<Leave>',lambda e:self.set_hover(False));self.bind('<Return>',lambda e:self.invoke());self.configure(takefocus=True)
        self.draw()
    def invoke(self):
        if self.enabled:self.command()
    def set_hover(self,v):self.hover=v;self.draw()
    def draw(self):
        need=tkfont.Font(font=FONT_BTN).measure(self.label)+38
        w=max(self.min_w or 0,need);self.w=w;h=self.h
        if int(self.cget('width'))!=w:self.configure(width=w)
        self.delete('all');base,hi=_FILL[self.kind]
        fill=('#3a5a2a' if self.active else hi if self.hover else base) if self.enabled else '#1c1b15'
        edge=GREEN if self.active else (GOLD if self.enabled else GOLD_DIM)
        c=7
        self.create_polygon(c,1,w-c,1,w-1,c,w-1,h-c,w-c,h-1,c,h-1,1,h-c,1,c,fill=fill,outline=edge,width=2)
        self.create_line(c+3,4,w-c-3,4,fill='#8a7a4a' if self.enabled else '#3a3526')                  # bevel highlight
        self.create_line(c+3,h-4,w-c-3,h-4,fill='#120f0a')                                               # bevel shadow
        for x,y in ((c,c),(w-c,c),(c,h-c),(w-c,h-c)):self.create_oval(x-2,y-2,x+2,y+2,fill=edge,outline='')   # studs
        self.create_text(w/2,h/2,text=self.label,fill=GREEN if self.active else (BONE if self.enabled else '#6d6753'),font=FONT_BTN)


def heading(parent,text,pady=(10,4)):
    """Gold section title with a rule and a centre diamond. Pack it with fill='x'."""
    f=tk.Frame(parent,bg=parent['bg'])
    tk.Label(f,text=text,bg=parent['bg'],fg=GOLD,font=FONT_HEAD,anchor='w').pack(fill='x')
    c=tk.Canvas(f,height=7,bg=parent['bg'],highlightthickness=0);c.pack(fill='x')
    def rule(e=None):
        c.delete('all');w=max(40,c.winfo_width())
        c.create_line(0,3,w,3,fill=GOLD_DIM);c.create_polygon(14,0,18,3,14,6,10,3,fill=GOLD,outline='')
    c.bind('<Configure>',rule);rule()
    return f


def label(parent,text='',color=BONE,font=FONT_UI,var=None,wrap=None,anchor='w',justify='left'):
    kw=dict(bg=parent['bg'],fg=color,font=font,anchor=anchor,justify=justify)
    if wrap:kw['wraplength']=wrap
    return tk.Label(parent,text=text,**kw) if var is None else tk.Label(parent,textvariable=var,**kw)


def caption(parent,text,wrap=400,color=MUTED,var=None):
    return label(parent,text,color,FONT_SMALL,var=var,wrap=wrap)


def entry(parent,var,width=None):
    kw=dict(textvariable=var,bg=INSET,fg=BONE,insertbackground=GREEN,relief='flat',font=('Segoe UI',11),
            highlightthickness=1,highlightbackground=EDGE,highlightcolor=GOLD_DIM,disabledbackground='#15170f',disabledforeground='#6d6753')
    if width:kw['width']=width
    return tk.Entry(parent,**kw)


def check(parent,text,var,command=None,enabled=True,accent=False,wrap=None,font=FONT_SMALL):
    kw=dict(text=text,variable=var,bg=parent['bg'],fg=GREEN if accent else BONE,selectcolor='#15200e',activebackground=parent['bg'],
            activeforeground=GREEN,disabledforeground='#6d6753',anchor='w',font=font,state='normal' if enabled else 'disabled',justify='left')
    if command:kw['command']=command
    if wrap:kw['wraplength']=wrap
    return tk.Checkbutton(parent,**kw)


def radio(parent,text,var,value,command=None):
    kw=dict(text=text,variable=var,value=value,bg=parent['bg'],fg=BONE,selectcolor='#15200e',activebackground=parent['bg'],
            activeforeground=GREEN,anchor='w',font=FONT_SMALL)
    if command:kw['command']=command
    return tk.Radiobutton(parent,**kw)


def combo(parent,var,values,width=12,state='readonly',font=None):
    kw=dict(textvariable=var,values=values,width=width,style='Orc.TCombobox',state=state)
    if font:kw['font']=font
    return ttk.Combobox(parent,**kw)


def spin(parent,var,lo,hi,width=5,command=None):
    kw=dict(from_=lo,to=hi,textvariable=var,width=width,bg=INSET,fg=BONE,buttonbackground=PANEL,insertbackground=GREEN,relief='flat',
            highlightthickness=1,highlightbackground=EDGE,font=FONT_UI)
    if command:kw['command']=command
    return tk.Spinbox(parent,**kw)


def scale(parent,var,lo,hi,command=None):
    kw=dict(from_=lo,to=hi,orient='horizontal',variable=var,bg=parent['bg'],fg=BONE,troughcolor=INSET,highlightthickness=0,
            activebackground=GREEN,sliderrelief='flat',font=FONT_TINY)
    if command:kw['command']=command
    return tk.Scale(parent,**kw)


def card(parent,pad=(10,8)):
    """Sunken dark box for output text and lists."""
    return tk.Frame(parent,bg=INSET,padx=pad[0],pady=pad[1],highlightthickness=1,highlightbackground=EDGE)


def card_text(parent,var,color=BONE,font=FONT_MONO,height=None,wrap=330,anchor='nw'):
    kw=dict(textvariable=var,bg=INSET,fg=color,justify='left',anchor=anchor,wraplength=wrap,font=font,padx=8,pady=6,
            highlightthickness=1,highlightbackground=EDGE)
    if height:kw['height']=height
    return tk.Label(parent,**kw)


def listbox(parent,height=6):
    return tk.Listbox(parent,height=height,bg=INSET,fg=BONE,selectbackground='#2f3a24',selectforeground=BONE,relief='flat',
                      font=FONT_MONO,exportselection=False,highlightthickness=1,highlightbackground=EDGE)


def panel(parent,title=None,width=None,pad=(14,12)):
    """Bronze panel with a 1 px gold frame. Returns (outer, inner, title_var); pack `outer`."""
    outer=tk.Frame(parent,bg=GOLD_DIM,padx=1,pady=1)
    inner=tk.Frame(outer,bg=PANEL,padx=pad[0],pady=pad[1]);inner.pack(fill='both',expand=True)
    if width:outer.configure(width=width);outer.pack_propagate(False)
    var=None
    if title is not None:
        var=tk.StringVar(value=title)
        tk.Label(inner,textvariable=var,bg=PANEL,fg=GOLD,font=FONT_HEAD,anchor='w').pack(fill='x')
        c=tk.Canvas(inner,height=7,bg=PANEL,highlightthickness=0);c.pack(fill='x',pady=(0,8))
        def rule(e=None):
            c.delete('all');w=max(40,c.winfo_width())
            c.create_line(0,3,w,3,fill=GOLD_DIM);c.create_polygon(14,0,18,3,14,6,10,3,fill=GOLD,outline='')
        c.bind('<Configure>',rule);rule()
    return outer,inner,var


def row(parent,pady=3):
    return tk.Frame(parent,bg=parent['bg'])


def button_row(parent,specs,gap=6,kind='normal',height=34,max_width=430):
    """specs: [(text, command), ...] -> frame of RuneButtons that wraps into new rows when the labels
    would exceed max_width (a settings column), so no button is ever clipped. Returns (frame, {text: button})."""
    f=tk.Frame(parent,bg=parent['bg']);out={};x=0;r=0;col=0
    for text,cmd in specs:
        b=RuneButton(f,text,cmd,height=height,kind=kind);out[text]=b
        if col and x+b.w>max_width:r+=1;col=0;x=0
        b.grid(row=r,column=col,padx=(0,gap),pady=(0,gap),sticky='w');x+=b.w+gap;col+=1
    return f,out


# ----------------------------------------------------------------------------------------------
# Header art: drawn with canvas polygons so no image assets ship with the helper.
# ----------------------------------------------------------------------------------------------
def _poly(c,pts,fill,outline='',width=1):
    return c.create_polygon(*pts,fill=fill,outline=outline,width=width,joinstyle='round')


def draw_crest(c,x,y,s=1.0):
    """Clan crest: a bronze kite shield with a gold rim and rivets, a double-bit axe over it.
    (x, y) is the top-left of an ~96×78 box at scale 1."""
    S=lambda px,py:(x+px*s,y+py*s)
    shield=[S(48,4),S(84,14),S(88,40),S(76,64),S(48,76),S(20,64),S(8,40),S(12,14)]
    _poly(c,shield,'#2b3a22',GOLD,2.5)
    inner=[S(48,12),S(76,20),S(79,40),S(69,58),S(48,68),S(27,58),S(17,40),S(20,20)]
    _poly(c,inner,'#3a4d2c','#8c7a44',1)
    for px,py in ((48,8),(81,16),(85,40),(74,61),(48,72),(22,61),(11,40),(15,16)):
        xx,yy=S(px,py);c.create_oval(xx-2.2*s,yy-2.2*s,xx+2.2*s,yy+2.2*s,fill=GOLD,outline='')
    # axe: haft, binding, two bits with a lighter bevel, spike on top
    _poly(c,[S(46,22),S(50,22),S(51,70),S(45,70)],'#5a4428','#2a1f12',1)
    for py in (56,61):c.create_line(*S(45,py),*S(51,py),fill='#1c1409',width=max(1,2*s))
    left=[S(46,26),S(33,20),S(22,30),S(22,46),S(33,54),S(46,48)]
    right=[S(50,26),S(63,20),S(74,30),S(74,46),S(63,54),S(50,48)]
    for bit in (left,right):_poly(c,bit,'#b9b4a6','#2a2a24',1.5)
    _poly(c,[S(46,30),S(36,26),S(27,34),S(27,44),S(36,50),S(46,46)],'#d9d4c4','')
    _poly(c,[S(50,30),S(60,26),S(69,34),S(69,44),S(60,50),S(50,46)],'#d9d4c4','')
    _poly(c,[S(48,10),S(52,22),S(44,22)],'#d9d4c4','#2a2a24',1)
    _poly(c,[S(46,22),S(50,22),S(52,27),S(44,27)],GOLD,'',1)
    c.create_text(*S(48,88),text='ASHENFALL',fill=GOLD_DIM,font=('Georgia',7,'bold')) if False else None


def draw_orc(c,cx,cy,s=1.0):
    """Orc head: pointed ears, heavy brow, glowing eyes, broad nose, jaw with two tusks, iron helm band."""
    S=lambda px,py:(cx+px*s,cy+py*s)
    skin='#4e6b3b';dark='#2f4524';mid='#5f7f48';light='#7c9a5c';bone='#eae2c6';iron='#5a5f55'
    # ears
    _poly(c,[S(-34,-6),S(-56,-22),S(-50,6),S(-34,10)],skin,dark,1.5)
    _poly(c,[S(34,-6),S(56,-22),S(50,6),S(34,10)],skin,dark,1.5)
    _poly(c,[S(-38,-4),S(-50,-16),S(-46,2)],mid,'')
    _poly(c,[S(38,-4),S(50,-16),S(46,2)],mid,'')
    # skull and jaw
    head=[S(-30,-34),S(-8,-42),S(8,-42),S(30,-34),S(38,-14),S(36,10),S(26,32),S(10,40),S(-10,40),S(-26,32),S(-36,10),S(-38,-14)]
    _poly(c,head,skin,dark,2)
    _poly(c,[S(-24,-30),S(-6,-37),S(6,-37),S(24,-30),S(28,-20),S(-28,-20)],mid,'')        # forehead light
    _poly(c,[S(-30,8),S(30,8),S(24,30),S(10,38),S(-10,38),S(-24,30)],dark,'')              # lower jaw shadow
    # helm band with rivets
    _poly(c,[S(-36,-18),S(36,-18),S(38,-8),S(-38,-8)],iron,'#2a2d27',1.5)
    for px in (-26,-9,9,26):
        xx,yy=S(px,-13);c.create_oval(xx-2*s,yy-2*s,xx+2*s,yy+2*s,fill=GOLD,outline='')
    # eyes: slanted sockets (inner corner low, outer corner high), ember irises, angry brows
    for sx in (-1,1):
        _poly(c,[S(sx*7,6),S(sx*28,-4),S(sx*30,5),S(sx*10,13)],'#15190f','')
        _poly(c,[S(sx*10,6),S(sx*26,-1),S(sx*27,5),S(sx*12,11)],'#ff6a2a','')
        _poly(c,[S(sx*14,5),S(sx*23,1),S(sx*23,4),S(sx*15,8)],'#ffd27a','')
        _poly(c,[S(sx*4,2),S(sx*31,-9),S(sx*32,-4),S(sx*6,8)],dark,'')
    _poly(c,[S(-6,-2),S(6,-2),S(4,8),S(-4,8)],dark,'')                                   # furrow between brows
    # nose
    _poly(c,[S(-7,10),S(7,10),S(10,20),S(0,24),S(-10,20)],mid,dark,1)
    xx,yy=S(-4,19);c.create_oval(xx-2*s,yy-1.5*s,xx+2*s,yy+1.5*s,fill=dark,outline='')
    xx,yy=S(4,19);c.create_oval(xx-2*s,yy-1.5*s,xx+2*s,yy+1.5*s,fill=dark,outline='')
    # mouth and tusks
    c.create_line(*S(-18,28),*S(18,28),fill='#15190f',width=max(1,3*s),capstyle='round')
    _poly(c,[S(-18,32),S(-24,6),S(-10,27)],bone,'#8b8460',1)
    _poly(c,[S(18,32),S(24,6),S(10,27)],bone,'#8b8460',1)
    # scar
    c.create_line(*S(18,12),*S(28,24),fill='#3a2a28',width=max(1,2*s))
