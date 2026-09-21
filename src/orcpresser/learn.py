"""Learned shortcuts that skip OCR for prompts already read once.

Memory (options 1 + 6): a nearest-neighbour classifier. Every confident OCR read stores a small
normalized image of the prompt (text row, keycap and the name line above) with its label. Later
scans compare against these samples; a close, unambiguous match returns the label without OCR.
There is no training step: OCR labels the data as you play. A size limit (MB) caps storage.

Templates (option 2): per action wording and per key letter, learned separately, matched with
normalized cross-correlation. They compose: 'Harvest' learned with E and F learned from another
prompt also recognize 'Harvest [F]'. Not used while exclusions are active (they cannot see names).

Both only ever return a result that OCR produced before, and reject near-ties. Unknown or
ambiguous images fall back to OCR (slower, never a guess).
"""
import json, time
from pathlib import Path
import cv2
import numpy as np
from vision import Prompt, neutral_bright, span, excluded_term, text_extent, SPAN

PW, PH = 194, 67            # memory patch: 15.2 keycaps wide (text + cap), 5.6 high (4.4 above)
ROW_TOP = PH - 17           # row part = bottom 1.4 keycap heights
KEY = 24                    # key interior patch size
TPL = 24                    # template scale: px per keycap height
MAX_PER_LABEL = 30


def _crop(img, l, t, r, b):
    """Crop with zero padding outside the frame."""
    H, W = img.shape[:2]
    out = np.zeros((b-t, r-l) + img.shape[2:], img.dtype)
    sl, st, sr, sb = max(l,0), max(t,0), min(r,W), min(b,H)
    if sr > sl and sb > st: out[st-t:sb-t, sl-l:sr-l] = img[st:sb, sl:sr]
    return out


def key_patch(frame, cap):
    x,y,w,h = cap
    k = int(round(min(w,h)*.16))
    g = neutral_bright(_crop(frame, x+k, y+k, x+w-k, y+h-k), 160, 80)
    return cv2.resize(g, (KEY, KEY), interpolation=cv2.INTER_AREA)


def mem_patch(frame, cap):
    x,y,w,h = cap
    reg = _crop(frame, int(x-15*h), int(y-4.4*h), int(x+w+.2*h), int(y+1.2*h))
    return cv2.resize(neutral_bright(reg, 160, 80), (PW, PH), interpolation=cv2.INTER_AREA)


def _d(a, b):
    """Normalized mask difference: |a-b| / (|a|+|b|). 0 = identical, 1 = no overlap. Unlike a plain
    mean it is not diluted by empty background, so short and long labels are judged alike."""
    s = float(np.sum(a, dtype=np.float64) + np.sum(b, dtype=np.float64))
    return float(np.sum(cv2.absdiff(a, b), dtype=np.float64)) / s if s > 0 else 0.


def _ncc(img, tpl):
    if img.shape[0] < tpl.shape[0] or img.shape[1] < tpl.shape[1]: return None
    if not tpl.any(): return None
    return cv2.matchTemplate(img.astype(np.float32), tpl.astype(np.float32), cv2.TM_CCOEFF_NORMED)


class Memory:
    T_ROW, T_CTX, T_KEY = .08, .08, .09      # normalized distance limits; synthetic: same <= .06, different >= .12
    RATIO = 1.6                               # nearest other label must be this much further

    def __init__(self):
        self.labels, self.ctx, self.patches, self.keys, self.stamp = [], [], [], [], []

    def nbytes(self):
        return len(self.labels)*(PW*PH + KEY*KEY + 64)

    def match(self, frame, cap, use_context):
        if not self.labels: return None
        p, k = mem_patch(frame, cap), key_patch(frame, cap)
        best = {}
        for i, (lab, sp, sk) in enumerate(zip(self.labels, self.patches, self.keys)):
            dk = _d(k, sk) / self.T_KEY
            dr = _d(p[ROW_TOP:], sp[ROW_TOP:]) / self.T_ROW
            dc = _d(p, sp) / self.T_CTX if use_context else 0.
            score = max(dk, dr, dc)                        # < 1 means all parts within threshold
            if lab not in best or score < best[lab][0]: best[lab] = (score, i)
        ranked = sorted(best.items(), key=lambda kv: kv[1][0])
        (lab, (score, i)) = ranked[0]
        if score >= 1: return None
        if len(ranked) > 1 and ranked[1][1][0] < max(score*self.RATIO, .5): return None   # ambiguous
        return lab, self.ctx[i], 1 - score/2

    def add(self, frame, cap, label, ctx, limit):
        p, k = mem_patch(frame, cap), key_patch(frame, cap)
        same = [i for i, l in enumerate(self.labels) if l == label and self.ctx[i] == ctx]
        # Skip near-duplicates: they cost space and add nothing.
        if any(_d(p, self.patches[i]) < self.T_ROW*.3 and _d(k, self.keys[i]) < self.T_KEY*.3 for i in same): return False
        self.labels.append(label); self.ctx.append(ctx); self.patches.append(p); self.keys.append(k); self.stamp.append(time.time())
        self.trim(limit)
        return True

    def trim(self, limit):
        """Evict oldest samples of the largest label until within limit and per-label cap."""
        while self.labels:
            counts = {}
            for l in self.labels: counts[l] = counts.get(l, 0) + 1
            big = max(counts, key=counts.get)
            if self.nbytes() <= limit and counts[big] <= MAX_PER_LABEL: return
            i = min((i for i, l in enumerate(self.labels) if l == big), key=lambda i: self.stamp[i])
            for arr in (self.labels, self.ctx, self.patches, self.keys, self.stamp): del arr[i]


class Templates:
    T_WORD = .80
    PER = 3

    def __init__(self):
        self.words = {}    # (action, hold) -> [mask images scaled to TPL px per keycap height]
        self.keys = {}     # 'E' -> [KEY x KEY masks]

    def nbytes(self):
        return sum(t.size for v in self.words.values() for t in v) + sum(t.size for v in self.keys.values() for t in v)

    def add(self, frame, prompt):
        x,y,w,h = prompt.box
        l,t,r,b = (int(v) for v in prompt.span)
        r = min(r, x-3)                              # text only; the keycap is matched separately
        s = TPL/h
        wm = cv2.resize(neutral_bright(_crop(frame, l-2, t-2, r+2, b+2)), None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        changed = False
        for store, lab, img in ((self.words, (prompt.action, prompt.hold), wm), (self.keys, prompt.key, key_patch(frame, prompt.box))):
            lst = store.setdefault(lab, [])
            if any(t.shape == img.shape and _d(img, t) < .03 for t in lst): continue
            lst.append(img); changed = True
            if len(lst) > self.PER: del lst[0]
        return changed

    def match(self, frame, cap, factor):
        if not self.words or not self.keys: return None
        x,y,w,h = cap
        s = TPL/h
        band = cv2.resize(neutral_bright(_crop(frame, x-span(w,factor), int(y-.4*h), x+2, int(y+1.4*h))), None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        near = band.shape[1] - int(2.2*TPL)           # text must end within ~2 keycaps of the cap
        hits = []
        for lab, lst in self.words.items():
            for t in lst:
                res = _ncc(band, t)
                if res is None: continue
                ok = res[:, max(0, near - t.shape[1]):]          # only placements ending near the cap
                if ok.size and ok.max() >= self.T_WORD: hits.append((t.shape[1], float(ok.max()), lab))
        if not hits: return None
        # Longest matching wording wins ('Collect Water' over 'Collect', 'Harvest [Hold]' over 'Harvest').
        hits.sort(key=lambda h: (h[0], h[1]), reverse=True)
        width, wscore, (action, hold) = hits[0]
        # The template must cover the whole text next to the keycap. Otherwise a learned 'Collect'
        # would claim an unseen 'Collect Water', or 'Harvest' an unseen 'Harvest [Hold]'.
        ext = text_extent(frame, cap, factor)
        if not ext: return None
        ew = ext[2]-ext[0]
        if abs(width/s - ew) > .15*ew + 8: return None
        # Keys: symmetric distance, not correlation. Correlation lets an 'E' template accept an 'F'.
        kp = key_patch(frame, cap)
        kd = sorted((min(_d(kp, t) for t in lst), k) for k, lst in self.keys.items())
        if not kd or kd[0][0] >= Memory.T_KEY: return None
        if len(kd) > 1 and kd[1][0] < kd[0][0]*Memory.RATIO: return None
        return action, kd[0][1], hold, min(wscore, 1 - kd[0][0])


class Learner:
    """Owns both stores, persistence and the size limit. Used only from the worker thread."""
    def __init__(self, folder, limit_mb=4., load=True, persist=True):
        self.folder = Path(folder); self.limit = int(limit_mb*1024*1024)
        self.persist = persist; self.load_error = None
        self.memory, self.templates = Memory(), Templates()
        self.opts = {}; self.dirty = False; self.saved = time.monotonic(); self.pending = {}
        if load: self.load()

    def set_limit(self, mb):
        self.limit = int(mb*1024*1024); self.memory.trim(max(0, self.limit - self.templates.nbytes()))

    def stats(self):
        return len(self.memory.labels), sum(len(v) for v in self.templates.words.values()), (self.memory.nbytes()+self.templates.nbytes())/1024

    def clear(self):
        self.memory, self.templates = Memory(), Templates(); self.dirty = True; self.save()

    def recognize(self, frame, caps, allowed, exclude, opts):
        from vision import has_glyph
        self.opts = opts; factor = opts.get('span', SPAN)
        out, rejected = [], []
        for cap in caps:
            if not has_glyph(frame, cap): continue
            got = None
            if opts.get('memory'):
                m = self.memory.match(frame, cap, bool(exclude))
                if m:
                    (action, key, hold), ctx, conf = m
                    term = excluded_term(ctx, exclude) if exclude else None
                    if term: rejected.append((action, key, term, cap)); continue
                    got = Prompt(action, key, hold, conf, cap, action + (' [Hold]' if hold else ''), None, 'memory')
            if got is None and opts.get('templates') and not exclude:
                t = self.templates.match(frame, cap, factor)
                if t:
                    action, key, hold, conf = t
                    got = Prompt(action, key, hold, conf, cap, action + (' [Hold]' if hold else ''), None, 'template')
            if got and got.action in allowed: out.append(got)
        return out, rejected

    def learn(self, frame, prompts, items, factor):
        """Store confident OCR reads. A label is committed only after OCR has read the same
        label (and name context) twice, so a single misread cannot poison the stores."""
        from vision import context_text
        for p in prompts:
            if p.confidence < .85 or p.source != 'ocr': continue
            ctx = context_text(p.box, items, factor)
            if self.pending.get((p.identity, ctx), 0) < 1:
                self.pending[(p.identity, ctx)] = 1
                if len(self.pending) > 200: self.pending.clear()
                continue
            if self.opts.get('memory'):
                self.dirty |= self.memory.add(frame, p.box, p.identity, ctx, max(0, self.limit - self.templates.nbytes()))
            if self.opts.get('templates') and p.span:
                self.dirty |= self.templates.add(frame, p)
        if self.dirty and time.monotonic() - self.saved > 30: self.save()

    # Persistence: plain arrays + JSON (no pickle), in ./learned/
    def save(self):
        if not self.persist: return
        try:
            self.folder.mkdir(exist_ok=True)
            m, t = self.memory, self.templates
            meta = {'labels': [list(l) for l in m.labels], 'ctx': m.ctx, 'stamp': m.stamp,
                    'words': [[a, h, len(v)] for (a, h), v in t.words.items()], 'keys': [[k, len(v)] for k, v in t.keys.items()]}
            arrays = {'patches': np.array(m.patches, np.uint8).reshape(-1, PH, PW), 'mkeys': np.array(m.keys, np.uint8).reshape(-1, KEY, KEY)}
            for i, v in enumerate(t.words.values()):
                for j, img in enumerate(v): arrays[f'w{i}_{j}'] = img
            for i, v in enumerate(t.keys.values()):
                for j, img in enumerate(v): arrays[f'k{i}_{j}'] = img
            tmp = self.folder / 'learned.tmp.npz'
            np.savez_compressed(tmp, meta=np.frombuffer(json.dumps(meta).encode(), np.uint8), **arrays)
            tmp.replace(self.folder / 'learned.npz')
            self.dirty = False; self.saved = time.monotonic()
        except OSError: pass

    def load(self):
        f = self.folder / 'learned.npz'
        if not f.exists(): return
        try:
            with np.load(f) as z:
                meta = json.loads(bytes(z['meta']).decode())
                m = self.memory
                m.labels = [tuple(l) for l in meta['labels']]; m.ctx = meta['ctx']; m.stamp = meta['stamp']
                m.patches = list(z['patches']); m.keys = list(z['mkeys'])
                for i, (a, h, n) in enumerate(meta['words']): self.templates.words[(a, bool(h))] = [z[f'w{i}_{j}'] for j in range(n)]
                for i, (k, n) in enumerate(meta['keys']): self.templates.keys[k] = [z[f'k{i}_{j}'] for j in range(n)]
        except Exception as e:
            self.memory, self.templates = Memory(), Templates()     # corrupt file: start from zero
            self.load_error = f'{type(e).__name__}: {e}'
