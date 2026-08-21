"""FFmpeg progress parsing and telemetry events (Spec F).

Feed -progress pipe:1 lines into ProgressParser; it emits throttled
event dicts. Events are skipped until speed is known so every emitted
progress event carries a finite eta_seconds.
"""

import time


class ProgressParser:
    """Parse ffmpeg progress blocks into throttled event dicts."""

    def __init__(self, duration, emit, min_interval=1.0):
        self.duration = duration
        self.emit = emit
        self.min_interval = min_interval
        self._fields = {}
        self._last_emit = 0.0

    def feed_line(self, line):
        line = line.strip()
        if "=" not in line:
            return
        key, _, value = line.partition("=")
        self._fields[key] = value
        if key == "progress" and value in ("continue", "end"):
            self._flush(value == "end")

    def _out_time(self):
        microseconds = self._fields.get("out_time_us")
        if microseconds:
            try:
                return float(microseconds) / 1e6
            except ValueError:
                pass
        raw = self._fields.get("out_time", "0")
        try:
            hours, minutes, rest = raw.split(":")
            seconds, frac = rest.split(".")
            return (int(hours) * 3600 + int(minutes) * 60 + int(seconds)
                    + int(frac.ljust(6, "0")) / 1e6)
        except (ValueError, IndexError):
            return 0.0

    def _speed(self):
        raw = self._fields.get("speed", "")
        try:
            return float(raw.rstrip("x"))
        except ValueError:
            return 0.0

    def _flush(self, final):
        now = time.monotonic()
        if not final and now - self._last_emit < self.min_interval:
            return
        speed = self._speed()
        if speed <= 0:
            if not final:
                return
            speed = None
        out_time = self._out_time()
        if final or self.duration <= 0:
            percent = 100.0
        else:
            percent = min(100.0, out_time / self.duration * 100)
        eta = (self.duration - out_time) / speed if speed else None
        self._last_emit = now
        self.emit({
            "type": "progress",
            "percent": round(percent, 1),
            "frame": int(float(self._fields.get("frame", 0) or 0)),
            "out_time": round(out_time, 3),
            "speed": round(speed, 2) if speed else None,
            "eta_seconds": round(eta, 1) if eta is not None and eta >= 0 else None,
        })
