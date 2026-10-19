"""Post-render verification gate.

Runs after a render on the tmp output, before it is renamed into place:
- container duration must equal the timeline span within one frame
- video frame count must equal duration * fps
- the picture must be live: midpoints of adjacent segments that draw from
  different sources must not sample to the same frame fingerprint

A repeated frame is only a failure when the two segments actually differ in
source (asset, in-point or generated color). A still card held across cuts,
or the same clip used twice, is a legitimate editorial choice and is not
flagged. Any violation raises VerificationError; the caller deletes the tmp
output and does not rename it.
"""

import hashlib
import subprocess

FRAME_EPSILON = 1.0 / 15.0


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


def source_key(seg):
    """Identity of what a segment draws. Equal keys may legitimately match."""
    asset = seg.get("asset")
    if asset is None or seg.get("filter") == "white_flash":
        return ("generated", seg.get("color"), seg.get("filter") == "white_flash")
    return ("asset", asset, seg.get("clip_start", 0))


def _segments_of(timeline_or_segments):
    if isinstance(timeline_or_segments, list):
        return timeline_or_segments
    return timeline_or_segments.base.segments


def verify(path, timeline_or_segments, fps, span=None):
    """Verify duration, frame count and liveness. Returns a report dict.

    span defaults to the timeline's last end; pass the transition-adjusted
    duration explicitly when the timeline uses transitions (xfade shortens
    the output below the raw span).
    """
    segments = _segments_of(timeline_or_segments)
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
    keys = []
    for i, seg in enumerate(segments):
        midpoint = (seg["start"] + seg["end"]) / 2
        fingerprints.append(fingerprint_at(path, midpoint))
        keys.append(source_key(seg))
        if i == 0:
            continue
        if keys[i] == keys[i - 1] and not _has_motion(seg):
            continue
        if fingerprints[i] == fingerprints[i - 1]:
            raise VerificationError(
                f"freeze detected: segments {i - 1} and {i} sample to the "
                f"same frame at their midpoints")

    return {
        "duration": duration,
        "frame_count": frame_count,
        "fingerprints": fingerprints,
    }


def _has_motion(seg):
    if seg.get("keyframes"):
        return len(seg["keyframes"]) > 1
    return seg.get("effect") not in (None, "strobe", "word_flash")
