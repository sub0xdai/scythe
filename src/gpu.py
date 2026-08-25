"""GPU capability probe and hardware profiles (Spec G).

Selection is invokability-based: an encoder is chosen only if it passes
a short dry-run encode to null output. No device access -> the CPU
profile, which is exactly the pre-Spec-G behavior.
"""

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class HardwareProfile:
    """Encoder choice plus the filtergraph tail and extra ffmpeg args."""
    encoder: str
    hw_chain: str = ""
    extra_args: tuple[str, ...] = ()


CPU_PROFILE = HardwareProfile("libx264", "", ())

ENCODER_ORDER = ("h264_nvenc", "h264_qsv", "h264_vaapi", "h264_videotoolbox")

PROFILE_TABLE = {
    "h264_nvenc": HardwareProfile(
        "h264_nvenc", "format=nv12,hwupload_cuda", ()),
    "h264_qsv": HardwareProfile(
        "h264_qsv", "format=nv12,hwupload=extra_hw_frames=64",
        ("-init_hw_device", "qsv=hw", "-filter_hw_device", "hw")),
    "h264_vaapi": HardwareProfile(
        "h264_vaapi", "format=nv12,hwupload",
        ("-init_hw_device", "vaapi=va:/dev/dri/renderD128", "-filter_hw_device", "va")),
    "h264_videotoolbox": HardwareProfile("h264_videotoolbox", "format=nv12", ()),
}


def parse_encoders(output):
    """Extract encoder names from `ffmpeg -hide_banner -encoders` output."""
    names = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            names.add(parts[1])
    return names


def _encoders_from_ffmpeg():
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True, text=True, timeout=30,
    )
    return parse_encoders(result.stdout)


def dry_run(encoder, extra_args):
    """Encode 0.2s of black to null; True when the encoder is invokable."""
    cmd = ["ffmpeg", "-hide_banner", "-f", "lavfi", "-i",
           "color=c=black:s=64x64:r=10:d=0.2",
           *extra_args, "-c:v", encoder, "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    return result.returncode == 0


def probe(encoder_list=None, dry_run_fn=None):
    """Return the first invokable hardware encoder, else the CPU profile."""
    if encoder_list is None:
        encoder_list = _encoders_from_ffmpeg()
    if dry_run_fn is None:
        dry_run_fn = dry_run
    for name in ENCODER_ORDER:
        if name in encoder_list and dry_run_fn(name, PROFILE_TABLE[name].extra_args):
            return PROFILE_TABLE[name]
    return CPU_PROFILE


def profile_for(encoder_name):
    """Resolve a forced encoder name to its profile, or None if unknown."""
    return PROFILE_TABLE.get(encoder_name)


def quality_for(encoder, crf):
    """Return the rate-control/quality args for an encoder given a CRF.

    libx264, nvenc, qsv, and vaapi are CRF-aligned (lower is better) and take
    the CRF unchanged. videotoolbox is inverted (higher is better on a 1-100
    scale) and takes 100 - crf, clamped to [1, 100]. Unknown encoders raise.
    """
    if encoder == "libx264":
        return ("-preset", "veryfast", "-crf", str(crf))
    if encoder == "h264_nvenc":
        return ("-rc", "vbr", "-cq", str(crf), "-preset", "p5")
    if encoder in ("h264_qsv", "h264_vaapi"):
        return ("-global_quality", str(crf))
    if encoder == "h264_videotoolbox":
        return ("-q:v", str(max(1, min(100, 100 - crf))))
    raise ValueError(f"unknown encoder: {encoder}")
