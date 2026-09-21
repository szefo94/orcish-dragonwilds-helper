"""Local combined detection: bright square keycaps + spatially aligned OCR.
1.5: selectable OCR paths (full / fast native detection / recognition-only) and learned
shortcuts (memory, templates) that skip OCR for prompts already read once."""
import re
from dataclasses import dataclass
import cv2
import numpy as np

SPAN = 20.   # default: action text may start this many keycap widths left of the keycap

from game_profile import PROFILE

ACTIONS = PROFILE.action_names

@dataclass(frozen=True)
class Prompt:
    action: str
    key: str
    hold: bool
    confidence: float
    box: tuple
    text: str
    span: tuple = None      # (left, top, right, bottom) of the action text, capture pixels
    source: str = 'ocr'     # ocr | memory | template

    @property
    def identity(self):
        return self.action, self.key, self.hold


def classify(text):
    return PROFILE.classify(text)


def exclusions(text):
    """'Stone, Cabbage' -> ('stone', 'cabbage'); empty entries ignored."""
    return tuple(dict.fromkeys(t for t in (re.sub(r'\s+', ' ', p).strip().lower() for p in text.split(',')) if t))


def excluded_term(text, terms):
    """Case-insensitive match at a word start: 'stone' hits 'Stone', 'Stones', 'Stone Chunk'."""
    t = re.sub(r'\s+', ' ', text.lower())
    for term in terms:
        if re.search(r'(?<![a-z0-9])' + re.escape(term), t): return term
    return None


def keycaps(frame):
    # Neutral, bright UI edges distinguish active keycaps from dim options.
    # cv2 channel ops instead of numpy max/min/astype(int): same mask, ~30x faster on large regions.
    b, g, r = cv2.split(frame)
    hi, lo = cv2.max(cv2.max(b, g), r), cv2.min(cv2.min(b, g), r)
    mask = cv2.bitwise_and(cv2.threshold(lo, PROFILE.keycap_min_bright, 255, cv2.THRESH_BINARY)[1],
                           cv2.threshold(cv2.subtract(hi, lo), PROFILE.keycap_max_spread, 255, cv2.THRESH_BINARY_INV)[1])
    edges = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3,3),np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for c in contours:
        x,y,w,h = cv2.boundingRect(c)
        (smin, smax), (amin, amax) = PROFILE.keycap_size, PROFILE.keycap_aspect
        if not (smin <= w <= smax and smin <= h <= smax and amin < w/h < amax): continue
        if cv2.contourArea(c) < .5*w*h: continue
        if any(abs(x-a)<7 and abs(y-b)<7 for a,b,_,_ in found): continue
        found.append((x,y,w,h))
    return found


def neutral_bright(img, lo_min=130, spread=90):
    """UI text and keycaps are bright and low-saturation; most scenery is not."""
    b, g, r = cv2.split(img)
    hi, lo = cv2.max(cv2.max(b, g), r), cv2.min(cv2.min(b, g), r)
    return cv2.bitwise_and(cv2.threshold(lo, lo_min, 255, cv2.THRESH_BINARY)[1],
                           cv2.threshold(cv2.subtract(hi, lo), spread, 255, cv2.THRESH_BINARY_INV)[1])


def has_glyph(frame, cap):
    """A real keycap has a letter inside; letter holes (o, e) that pass the shape filter do not."""
    x,y,w,h = cap
    k = max(2, int(min(w,h)*.25))
    inner = frame[y+k:y+h-k, x+k:x+w-k]
    if inner.size == 0: return False
    f = float(np.count_nonzero(neutral_bright(inner, 150, 80))) / (inner.shape[0]*inner.shape[1])
    return .04 < f < .75


def span(w, factor=SPAN):
    """How far left of a keycap the action text may start (scales with UI size)."""
    return int(max(3., factor)*w)


def context_text(cap, items, factor=SPAN):
    """Text in the prompt row and up to ~4 keycap heights above it (object name line)."""
    x,y,w,h = cap
    return ' '.join(i[4] for i in items if i[2] >= x-span(w,factor) and i[0] <= x+w+8
                    and y-4.5*h <= (i[1]+i[3])/2 <= y+h*1.5)


def associate(caps, items, allowed, exclude=(), rejected=None, factor=SPAN):
    """items: (left, top, right, bottom, text, confidence) in capture pixels.
    exclude: lower-case terms; matching prompts are dropped and reported in rejected."""
    prompts = []
    for x,y,w,h in caps:
        cy = y+h/2
        row = [i for i in items if abs((i[1]+i[3])/2-cy) < max(h*.55, (i[3]-i[1])*.55)
               and i[2] >= x-span(w,factor) and i[0] <= x+w+8 and i[5] >= .82]
        row.sort(key=lambda i:i[0])
        key = None
        parts = []
        scores = []
        boxes = []
        for l,t,r,b,txt,score in row:
            cleaned = txt.strip().strip('[]{}| ')
            # The final character must be spatially inside the detected keycap.
            if r >= x+w*.35 and l <= x+w*.8:
                m = re.search(PROFILE.key_pattern, cleaned)
                if m:
                    key = m[1].upper()
                    prefix = cleaned[:m.start()].strip()
                    if prefix: parts.append(prefix); boxes.append((l,t,min(r,x),b))
                    scores.append(score)
                    continue
            if r <= x+5:
                parts.append(cleaned); boxes.append((l,t,r,b))
                scores.append(score)
        text = ' '.join(parts)
        action = classify(text)
        if not key or action not in allowed: continue
        hold = PROFILE.is_hold(text)
        # e.g. Siphon requires a hold: never silently turn a failed HOLD read into a tap.
        if not PROFILE.accept(action, hold): continue
        term = excluded_term(context_text((x,y,w,h), items, factor), exclude) if exclude else None
        if term:
            if rejected is not None: rejected.append((action, key, term, (x,y,w,h)))
            continue
        tb = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else None
        prompts.append(Prompt(action,key,hold,min(scores), (x,y,w,h),text,tb))
    # Use an explicit action priority, not whichever OCR word happens to come first.
    return sorted(prompts, key=lambda p: allowed.index(p.action))


def strips(caps, shape, context=False, factor=SPAN):
    """Crop rectangles around each keycap row, overlapping crops merged.
    OCR on these strips instead of the whole capture is the main speed-up."""
    H, W = shape[:2]
    rects = []
    for x,y,w,h in caps:
        # Generous margins matter: thin strips (width/height > 8) get padded by RapidOCR and a keycap
        # touching the crop edge was often missed by the detector in synthetic tests.
        top = y - (4.5*h if context else 1.5*h)
        rects.append([max(0,int(x-span(w,factor))), max(0,int(top)), min(W,int(x+2*w)), min(H,int(y+2.5*h))])
    # Merge until no two crops overlap, so no text is OCR'd (and associated) twice.
    merged = []
    for r in rects:
        while True:
            hit = next((m for m in merged if r[0] <= m[2] and r[2] >= m[0] and r[1] <= m[3] and r[3] >= m[1]), None)
            if hit is None: break
            merged.remove(hit)
            r = [min(hit[0],r[0]), min(hit[1],r[1]), max(hit[2],r[2]), max(hit[3],r[3])]
        merged.append(r)
    return merged


def text_extent(frame, cap, factor=SPAN):
    """Recognition-only path: find the run of bright text columns ending just left of the keycap.
    Word gaps up to ~0.9 keycap heights are bridged. Returns (l, t, r, b) or None."""
    x,y,w,h = cap
    l0 = max(0, x-span(w,factor)); t, b = max(0,y), min(frame.shape[0], y+h)
    band = frame[t:b, l0:max(l0,x-1)]
    if band.size == 0: return None
    cols = np.count_nonzero(neutral_bright(band), axis=0) > 0
    i = len(cols)-1; gap = 0; right = None; left = None
    while i >= 0:
        if cols[i]:
            if right is None: right = i
            left = i; gap = 0
        else:
            gap += 1
            if right is None and gap > 1.5*h: return None       # nothing near the keycap
            if right is not None and gap > .9*h: break
        i -= 1
    if right is None or right-left < .5*h: return None
    return (l0+left-4, max(0,int(y-.1*h)), min(x-1, l0+right+5), min(frame.shape[0], int(y+h*1.1)))


class Detector:
    """OCR engine plus optional learned shortcuts. opts keys:
    fast_det (native-resolution text detection), rec_only (skip detection, recognition only),
    memory / templates (learned shortcuts, see learn.py), span (text span factor)."""
    def __init__(self, gpu=False):
        from rapidocr_onnxruntime import RapidOCR
        # Default det config is limit_type=min/736: every input is UPSCALED until its short side is 736 px,
        # which made a 600x200 region cost as much as a full screen. 'max' only caps oversized input.
        kw = dict(det_use_dml=True, rec_use_dml=True) if gpu else {}
        self.gpu = gpu
        self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1,
                            det_limit_side_len=2000, det_limit_type='max', use_cls=False, **kw)

    def reread_keys(self, frame, caps, items, factor=SPAN, force=False):
        """Recognize the keycap interior directly (~20 ms) when no key letter was read inside it.
        Only for caps with text to their left (skips letter holes). The 0.82 gate still applies."""
        extra = []
        for x,y,w,h in caps:
            # Re-read also when the letter inside was found but below the 0.82 confidence gate.
            inside = any(i[2] >= x+w*.35 and i[0] <= x+w*.8 and y <= (i[1]+i[3])/2 <= y+h and i[5] >= .82 for i in items)
            left = any(i[2] <= x+5 and i[2] >= x-span(w,factor) and abs((i[1]+i[3])/2-(y+h/2)) < h*.55 for i in items)
            if (inside and not force) or not left: continue
            k = int(round(min(w,h)*.16))
            g = frame[y+k:y+h-k, x+k:x+w-k]
            if g.size == 0: continue
            g = cv2.resize(g, None, fx=48/g.shape[0], fy=48/g.shape[0], interpolation=cv2.INTER_CUBIC)
            # Two paddings in one batch; recognition of a lone glyph is sensitive to it. Best valid wins.
            reads = self.ocr.text_rec([cv2.copyMakeBorder(g, 0, 0, p, p, cv2.BORDER_REPLICATE) for p in (24, 48)])[0]
            valid = [(float(sc), t.strip()) for t, sc in reads if re.fullmatch(r'\s*[A-Za-z0-9]\s*', t)]
            if valid:
                score, text = max(valid)
                extra.append((x+k, y+k, x+w-k, y+h-k, text, score))
        return extra

    def ocr_strip(self, frame, rect, fast, caps=()):
        """Detection + recognition on one strip. fast: detect at native size (~4x fewer pixels),
        recognize each found line from a 2x upscaled crop. Keycap letters missed by native
        detection are recovered by reread_keys."""
        l,t,r,b = rect
        crop = frame[t:b, l:r]
        items = []
        if not fast:
            big = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            result, _ = self.ocr(big, use_cls=False)
            for box, text, score in result or []:
                a = np.asarray(box)/2
                items.append((float(a[:,0].min())+l, float(a[:,1].min())+t, float(a[:,0].max())+l, float(a[:,1].max())+t, text, float(score)))
            return items
        boxes, _ = self.ocr.text_det(crop)
        if boxes is None or not len(boxes): return items
        rects, imgs = [], []
        for box in boxes:
            a = np.asarray(box)
            x0,y0 = max(0,int(a[:,0].min())-2), max(0,int(a[:,1].min())-2)
            x1,y1 = min(crop.shape[1],int(a[:,0].max())+3), min(crop.shape[0],int(a[:,1].max())+3)
            # At native size a line often runs into the keycap ('Harvest [Hold] ]'). Cut it at the
            # keycap's left edge; the letter is then read by reread_keys.
            big = max((c[3] for c in caps), default=0)
            for cx,cy,cw,ch in caps:
                if ch < .7*big: continue                      # letter holes, not keycaps
                cx -= l; cy -= t
                if x0 < cx-.5*ch and cx+.3*cw < x1 <= cx+cw+.6*ch and y0 < cy+ch and y1 > cy: x1 = min(x1, cx-1)
            if x1-x0 < 3 or y1-y0 < 3: continue
            rects.append((x0,y0,x1,y1))
            imgs.append(cv2.resize(crop[y0:y1,x0:x1], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
        if not imgs: return items
        for (x0,y0,x1,y1),(text,score) in zip(rects, self.ocr.text_rec(imgs)[0]):
            if score >= .5 and text.strip(): items.append((x0+l, y0+t, x1+l, y1+t, text, float(score)))
        return items

    def rec_only(self, frame, caps, factor):
        """No detection model: text extent from bright-pixel columns, then recognition only.
        Returns items for caps where this worked; others fall back to detection."""
        items, done, imgs, rects = [], [], [], []
        for cap in caps:
            ext = text_extent(frame, cap, factor)
            if not ext: continue
            l,t,r,b = ext
            crop = frame[t:b, max(0,l):r]
            if crop.size == 0: continue
            imgs.append(cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)); rects.append((cap,ext))
        if imgs:
            for (cap,(l,t,r,b)),(text,score) in zip(rects, self.ocr.text_rec(imgs)[0]):
                if text.strip() and classify(text.strip().strip('[]{}| ')):
                    items.append((l,t,r,b,text,float(score))); done.append(cap)
        return items, done

    def detect(self, frame, allowed, exclude=(), opts=None, learner=None):
        """Returns prompts, annotated debug image, raw text, rejected [(action,key,term,box)], info.
        info: source ('ocr'/'memory'/'template'/'none') and geo [(cap, text_left)] for the crop advisor."""
        o = opts or {}; factor = o.get('span', SPAN)
        info = {'source':'none', 'geo':[]}
        caps = keycaps(frame)
        if not caps: return [], frame, 'No active keycap found', [], info
        learned, rejected = [], []
        if learner is not None:
            learned, rejected = learner.recognize(frame, caps, allowed, exclude, o)
        todo = caps
        if learned or rejected:
            done = [p.box for p in learned] + [r[3] for r in rejected]
            # Letter holes and caps already covered by a recognized row do not need OCR.
            todo = [c for c in caps if c not in done and has_glyph(frame, c) and not any(
                abs((c[1]+c[3]/2)-(d[1]+d[3]/2)) < d[3]*.6 and d[0]-span(d[2],factor) <= c[0] <= d[0] for d in done)]
        items = []
        if todo:
            rest = todo
            if o.get('rec_only') and not exclude:
                ri, done = self.rec_only(frame, [c for c in todo if has_glyph(frame, c)], factor)
                items += ri; rest = [c for c in todo if c not in done and not any(
                    abs((c[1]+c[3]/2)-(d[1]+d[3]/2)) < d[3]*.6 and d[0]-span(d[2],factor) <= c[0] <= d[0] for d in done)]
            for rect in strips(rest, frame.shape, bool(exclude), factor):
                items += self.ocr_strip(frame, rect, o.get('fast_det', False), rest)
            items += self.reread_keys(frame, todo, items, factor)
            ocr_prompts = associate(todo, items, allowed, exclude, rejected, factor)
            if learner is not None:
                everything = associate(todo, items, list(ACTIONS), (), None, factor)
                learner.learn(frame, everything, items, factor)
        else: ocr_prompts = []
        prompts = sorted(learned + ocr_prompts, key=lambda p: allowed.index(p.action))
        if prompts: info['source'] = prompts[0].source
        for p in prompts:
            if p.span: info['geo'].append((p.box, p.span[0]))
        debug = frame.copy()
        for x,y,w,h in caps: cv2.rectangle(debug,(x,y),(x+w,y+h),(40,160,220),1)
        for *_, (x,y,w,h) in rejected: cv2.rectangle(debug,(x,y),(x+w,y+h),(60,60,235),2)
        for p in prompts:
            x,y,w,h = p.box
            cv2.rectangle(debug,(x,y),(x+w,y+h),(70,255,110) if p.source=='ocr' else (255,200,70),2)
        raw = ' | '.join(i[4] for i in items) or ('[' + ', '.join(f'{p.action} {p.key}' for p in learned) + '] from ' + info['source'] if learned else 'No readable text')
        return prompts, debug, raw, rejected, info
