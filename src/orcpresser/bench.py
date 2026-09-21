"""Automated test runs for Auto Presser speed options (the STATS tab).

A run tests several configurations. Each configuration gets two phases:
  static  - the player stands still facing a prompt (e.g. in water: Collect Water / Fill Watering Can)
  camera  - the app sweeps the camera left/right with the SAME mouse path for every configuration and
            returns it exactly to the start, so all configurations see the same angles and scenery.
Everything runs in PREVIEW: prompts are recognized and decisions are timed, but no key is ever sent.

Ground truth is not available from the screen alone, so results are relative to the Baseline (all
speed options off, full OCR) measured in the same run:
  - reference label = the prompt Baseline saw most in its static phase
  - detection %     = scans that found an approved prompt
  - agreement %     = detections that match the reference label (static) / Baseline's label mix (camera)
"""
import json, math, time
from pathlib import Path

OPTION_LABELS = {'fast_det': 'Fast detection', 'rec_only': 'Recognition only', 'memory': 'Learned memory',
                 'templates': 'Templates', 'single': 'Single-scan confirm', 'dxgi': 'DXGI capture', 'gpu': 'GPU'}
SHORT = {'baseline': 'BASE', 'fast_det': 'FAST', 'rec_only': 'REC', 'memory': 'MEM', 'templates': 'TPL',
         'single': '1SCN', 'dxgi': 'DXGI', 'gpu': 'GPU', 'all': 'ALL'}
PHASES = ('static', 'camera')


def plan(ticked):
    """Baseline + each ticked option alone + all ticked together (if 2+). ticked: iterable of option keys."""
    ticked = [k for k in OPTION_LABELS if k in set(ticked)]
    off = {k: False for k in OPTION_LABELS}
    configs = [{'id': 'baseline', 'name': 'Baseline (all off)', 'opts': dict(off)}]
    for k in ticked:
        configs.append({'id': k, 'name': OPTION_LABELS[k], 'opts': dict(off, **{k: True})})
    if len(ticked) >= 2:
        configs.append({'id': 'all', 'name': 'All ticked', 'opts': dict(off, **{k: True for k in ticked})})
    return configs


class CameraPath:
    """Horizontal sinusoidal sweep: offset(t) = A*sin(2*pi*t/P). Whole periods only, so it ends at 0."""
    def __init__(self, amplitude_px, period_s):
        self.a, self.p = float(amplitude_px), max(.5, float(period_s)); self.applied = 0

    def offset(self, t):
        return self.a * math.sin(2 * math.pi * t / self.p)

    def delta(self, t):
        """Integer mouse movement to reach the path position at time t."""
        d = int(round(self.offset(t))) - self.applied
        self.applied += d
        return d

    def home(self):
        d = -self.applied; self.applied = 0; return d


class PhaseStats:
    def __init__(self):
        self.scan_ms, self.labels, self.sources, self.confirm_ms = [], [], [], []
        self.cpu = None; self.duration = 0.; self._seen = None; self._seen_at = None; self._done = False

    def scan(self, scan_ms, label, source, stamp, decided):
        self.scan_ms.append(scan_ms); self.labels.append(label); self.sources.append(source if label else None)
        if label != self._seen:
            self._seen, self._seen_at, self._done = label, stamp, False
        if label and decided and not self._done:
            self._done = True; self.confirm_ms.append((stamp - self._seen_at) * 1000 + scan_ms)

    def summary(self, reference=None):
        n = len(self.scan_ms); det = [l for l in self.labels if l]
        changes = sum(1 for a, b in zip(self.labels, self.labels[1:]) if a != b)
        s = sorted(self.scan_ms)
        out = {
            'scans': n,
            'scan_ms': round(sum(s) / n, 1) if n else None,
            'scan_p95': round(s[min(n - 1, int(n * .95))], 1) if n else None,
            'detect_pct': round(100 * len(det) / n, 1) if n else None,
            'changes_per_min': round(60 * changes / self.duration, 1) if self.duration else None,
            'confirm_ms': round(sum(self.confirm_ms) / len(self.confirm_ms), 0) if self.confirm_ms else None,
            'learned_pct': round(100 * sum(1 for x in self.sources if x in ('memory', 'template')) / len(det), 1) if det else None,
            'cpu_pct': self.cpu,
            'labels': {' '.join(map(str, l)): self.labels.count(l) for l in set(det)},
        }
        if reference is not None and det:
            out['agree_pct'] = round(100 * sum(1 for l in det if l == reference) / len(det), 1)
        return out


class Benchmark:
    """Drives one run. The app calls step(now) every tick and scan(...) for every finished scan."""
    def __init__(self, configs, phase_s=15., settle_s=2., amplitude_px=250, period_s=4.):
        self.configs = configs; self.phase_s = float(phase_s); self.settle_s = float(settle_s)
        self.period_s = float(period_s); self.amplitude = amplitude_px
        # camera phase lasts a whole number of sweep periods so it ends where it started
        self.camera_s = max(1, round(self.phase_s / self.period_s)) * self.period_s
        self.i = 0; self.phase = 'static'; self.t0 = None; self.settling = True
        self.stats = {(c['id'], p): PhaseStats() for c in configs for p in PHASES}
        self.path = None; self.done = False; self.aborted = None; self.started = time.time()
        self.events = []   # ('config', idx) | ('phase', name) - consumed by the app

    @property
    def config(self): return self.configs[self.i]

    def total_s(self):
        return len(self.configs) * (self.phase_s + self.camera_s + 2 * self.settle_s)

    def remaining(self, now):
        return max(0., self.total_s() - (now - getattr(self, 'first', now)))

    def progress(self, now):
        steps = len(self.configs) * 2; k = self.i * 2 + (self.phase == 'camera')
        return f'{self.config["name"]} · {self.phase} · {k + 1}/{steps}'

    def step(self, now, cpu=None):
        """Advance phases. Returns horizontal mouse delta to apply (camera phase), else 0."""
        if self.done: return 0
        if self.t0 is None:
            self.t0 = self.first = now; self.events.append(('config', self.i))
        el = now - self.t0
        if self.settling:                       # let the engine switch (GPU rebuild, new crop) before measuring
            if el < self.settle_s: return 0
            self.settling = False; self.t0 = now; el = 0.
            if cpu: cpu()                        # reset CPU meter at the start of the measured window
            if self.phase == 'camera': self.path = CameraPath(self.amplitude, self.period_s)
        length = self.phase_s if self.phase == 'static' else self.camera_s
        st = self.stats[(self.config['id'], self.phase)]
        if el >= length:
            st.duration = length
            if cpu: st.cpu = round(cpu(), 1)
            back = self.path.home() if self.path else 0
            self.path = None
            if self.phase == 'static': self.phase = 'camera'
            else:
                self.phase = 'static'; self.i += 1
                if self.i >= len(self.configs): self.done = True; return back
                self.events.append(('config', self.i))
            self.events.append(('phase', self.phase)); self.settling = True; self.t0 = now
            return back
        return self.path.delta(el) if self.path else 0

    def measuring(self):
        return not self.done and not self.settling and self.t0 is not None

    def scan(self, scan_ms, label, source, stamp, decided):
        if self.measuring(): self.stats[(self.config['id'], self.phase)].scan(scan_ms, label, source, stamp, decided)

    def abort(self, reason):
        self.aborted = reason; self.done = True
        back = self.path.home() if self.path else 0; self.path = None
        return back

    def results(self, meta=None):
        base = self.stats.get(('baseline', 'static'))
        ref = None
        if base and any(base.labels):
            det = [l for l in base.labels if l]; ref = max(set(det), key=det.count)
        out = {'version': 1, 'started': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.started)),
               'phase_s': self.phase_s, 'camera_s': self.camera_s, 'amplitude_px': self.amplitude, 'period_s': self.period_s,
               'reference': ' '.join(map(str, ref)) if ref else None, 'aborted': self.aborted, 'meta': meta or {},
               'configs': []}
        base_cam = self.stats.get(('baseline', 'camera'))
        cam_ref = {l: base_cam.labels.count(l) for l in set(base_cam.labels) if l} if base_cam else {}
        for c in self.configs:
            row = {'id': c['id'], 'name': c['name'], 'opts': c['opts']}
            for p in PHASES:
                st = self.stats[(c['id'], p)]
                if not st.scan_ms: continue
                s = st.summary(ref if p == 'static' else None)
                if p == 'camera' and cam_ref:   # share of detections whose label Baseline also produced here
                    det = [l for l in st.labels if l]
                    if det: s['agree_pct'] = round(100 * sum(1 for l in det if l in cam_ref) / len(det), 1)
                row[p] = s
            out['configs'].append(row)
        return out


def _ratio(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def baseline_ok(res, min_detect=20.):
    """Suggestions need a Baseline that actually saw a prompt while standing still."""
    base = next((r for r in res.get('configs', []) if r['id'] == 'baseline'), None)
    return bool(base and base.get('static', {}).get('detect_pct') and base['static']['detect_pct'] >= min_detect)


def recommend(res):
    """Per option: ('suggest'|'avoid'|'neutral', short reason). Compares 'option alone' with Baseline.
    Empty when Baseline saw no prompt: nothing to compare against."""
    rows = {r['id']: r for r in res.get('configs', [])}
    base = rows.get('baseline'); out = {}
    if not baseline_ok(res): return out
    for oid, r in rows.items():
        if oid in ('baseline', 'all') or 'static' not in r: continue
        bs, os_ = base['static'], r['static']; bc, oc = base.get('camera', {}), r.get('camera', {})
        speed = _ratio(bs['scan_ms'], os_['scan_ms'])
        det = [x for x in (_ratio(os_['detect_pct'], bs['detect_pct']), _ratio(oc.get('detect_pct'), bc.get('detect_pct'))) if x is not None]
        agree = [x for x in (os_.get('agree_pct'), oc.get('agree_pct')) if x is not None]
        conf = _ratio(bs.get('confirm_ms'), os_.get('confirm_ms'))
        flips = _ratio(oc.get('changes_per_min'), bc.get('changes_per_min')) if bc.get('changes_per_min') else None
        worst_det = min(det) if det else None; worst_agree = min(agree) if agree else None
        why = []
        if speed: why.append(f'scan {100 * (1 / speed - 1):+.0f}%')
        if worst_det is not None: why.append(f'detection {100 * (worst_det - 1):+.0f}%')
        if worst_agree is not None: why.append(f'agreement {worst_agree:.0f}%')
        if oid == 'single' and conf: why.append(f'reaction {100 * (1 / conf - 1):+.0f}%')
        reason = ', '.join(why)
        if (worst_det is not None and worst_det < .9) or (worst_agree is not None and worst_agree < 95) \
                or (speed is not None and speed < .9 and oid != 'single') or (oid == 'single' and flips and flips > 1.3):
            out[oid] = ('avoid', reason)
        elif (worst_det is None or worst_det >= .97) and (worst_agree is None or worst_agree >= 98) and (
                (speed and speed >= 1.15) or (oid == 'single' and conf and conf >= 1.15 and (not flips or flips <= 1.1))):
            out[oid] = ('suggest', reason)
        else:
            out[oid] = ('neutral', reason)
    return out


def save(res, folder):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    f = folder / ('bench_' + res['started'].replace(':', '').replace('-', '').replace(' ', '_') + '.json')
    f.write_text(json.dumps(res, indent=1), encoding='utf-8'); return f


def load_all(folder):
    out = []
    for f in sorted(Path(folder).glob('bench_*.json'), reverse=True):
        try: out.append((f, json.loads(f.read_text(encoding='utf-8'))))
        except (OSError, ValueError): pass
    return out
