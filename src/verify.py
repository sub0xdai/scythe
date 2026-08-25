"""Post-render verification gate (render-performance CP-4).

Runs after a render on the tmp output, before it is renamed into place:
- container duration must equal the cutlist span within one frame
- video frame count must equal duration * fps
- the picture must be live: adjacent cutlist segment midpoints sample to
  different frame fingerprints (a frozen picture repeats one frame)

Any violation raises VerificationError with a named message; the caller
deletes the tmp output and does not rename it.
"""

import hashlib
import subprocess

FRAME_EPSILON = 1.0 / 15.0  # one frame at the minimum supported fps


class VerificationError(Exception):
    """The render failed verification; the tmp output must not be renamed."""


def _probe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    return float(result.stdout.strip())


def _probe_frame_count(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True, timeout=120,
    )
    return int(result.stdout.strip())


def fingerprint_at(path, t):
    """Hash one decoded frame at time t (downscaled grayscale)."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:g}", "-i", str(path),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray",
         "-vf", "scale=64:-1", "-"],
        capture_output=True, check=True, timeout=60,
    )
    return hashlib.sha256(result.stdout).hexdigest()


def verify(path, segments, fps, span=None):
    """Verify duration, frame count, and liveness. Returns a report dict.

    span defaults to the cutlist's last end; pass the transition-adjusted
    duration explicitly when the timeline uses transitions (xfade shortens
    the output below the raw span).
    """
    if span is None:
        span = segments[-1]["end"]
    expected_frames = round(span * fps)

    duration = _probe_duration(path)
    if abs(duration - span) > FRAME_EPSILON:
        raise VerificationError(
            f"duration drift: expected {span:.3f}s, container reports "
            f"{duration:.3f}s")
    frame_count = _probe_frame_count(path)
    if frame_count != expected_frames:
        raise VerificationError(
            f"frame count: expected {expected_frames} "
            f"(round({span:.3f}s * {fps}fps)), got {frame_count}")

    fingerprints = []
    for i, seg in enumerate(segments):
        midpoint = (seg["start"] + seg["end"]) / 2
        fingerprints.append(fingerprint_at(path, midpoint))
        if i > 0 and fingerprints[i] == fingerprints[i - 1]:
            raise VerificationError(
                f"freeze detected: segments {i - 1} and {i} sample to the "
                f"same frame at their midpoints")

    return {
        "duration": duration,
        "frame_count": frame_count,
        "fingerprints": fingerprints,
    }
