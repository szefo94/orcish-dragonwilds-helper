"""Screen capture backends. mss (GDI BitBlt) is the default; DXGI Desktop Duplication via dxcam
is optional and usually a few ms faster per grab. Any DXGI problem falls back to mss."""
import numpy as np

def dxgi_available():
    """Installed? Checked WITHOUT importing: importing dxcam creates DirectX devices and initializes
    COM in the calling thread, which must not happen in the UI thread at startup (1.5-1.7 did)."""
    import importlib.util, sys
    return sys.platform == 'win32' and importlib.util.find_spec('dxcam') is not None


class Grabber:
    def __init__(self):
        import mss
        self.mss = mss.mss(); self.dx = None; self.cams = {}; self.use_dxgi = False; self.last_backend = 'mss'

    def set_dxgi(self, on):
        self.use_dxgi = bool(on) and dxgi_available()
        if self.use_dxgi and self.dx is None:
            try:
                import dxcam
                self.dx = dxcam; self.factory = getattr(dxcam, '__factory')
            except Exception:
                self.use_dxgi = False

    def _output_for(self, rect):
        """(device, output, left, top) of the monitor fully containing rect, else None."""
        l, t = rect['left'], rect['top']; r, b = l+rect['width'], t+rect['height']
        for d, outs in enumerate(self.factory.outputs):
            for o, out in enumerate(outs):
                out.update_desc(); c = out.desc.DesktopCoordinates
                if c.left <= l and c.top <= t and r <= c.right and b <= c.bottom: return d, o, c.left, c.top
        return None

    def grab(self, rect):
        if self.use_dxgi:
            try:
                where = self._output_for(rect)
                if where:
                    d, o, ox, oy = where
                    cam = self.cams.get((d, o))
                    if cam is None:
                        cam = self.cams[(d, o)] = self.dx.create(device_idx=d, output_idx=o, output_color='BGR')
                    l, t = rect['left']-ox, rect['top']-oy
                    frame = cam.grab(region=(l, t, l+rect['width'], t+rect['height']), new_frame_only=False)
                    if frame is not None:
                        self.last_backend = 'dxgi'
                        return np.ascontiguousarray(frame[:, :, :3])
            except Exception:
                pass            # lost device, UAC screen, spanning monitors...: use mss this time
        self.last_backend = 'mss'
        return np.asarray(self.mss.grab(rect))[:, :, :3].copy()
