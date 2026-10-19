"""Post-render evaluation: measure the output, never assume it.

The renderer cannot see or hear. It can measure: frozen picture, black
runs, silence, integrated loudness and true peak. Each check produces a
Finding; errors block the render unless evaluation is disabled, warnings
are reported and recorded.

The parsers are pure so the rules can be tested against real ffmpeg
stderr without rendering.
"""

import re
import subprocess
from dataclasses import dataclass

ERROR = "error"
WARNING = "warning"

EVAL_DEFAULTS = {
    "eval_freeze_min": 1.0,
    "eval_black_min": 0.2,
    "eval_silence_min": 2.0,
    "eval_lufs_tolerance": 3.0,
    "eval_true_peak_max": -1.0,
}


@dataclass(frozen=True)
class Finding:
    severity: str
    rule: str
    message: str
    at: float | None = None


def _spans(pattern, stderr, start_key, end_key):
    starts = [float(m) for m in re.findall(rf"{start_key}:\s*(-?[0-9.]+)", stderr)]
    ends = [float(m) for m in re.findall(rf"{end_key}:\s*(-?[0-9.]+)", stderr)]
    spans = []
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else None
        spans.append((start, end))
    return spans


def parse_freezedetect(stderr):
    """Return [(start, end|None)] from ffmpeg freezedetect stderr."""
    return _spans(None, stderr, "freeze_start", "freeze_end")


def parse_blackdetect(stderr):
    """Return [(start, end|None)] from ffmpeg blackdetect stderr."""
    return _spans(None, stderr, "black_start", "black_end")


def parse_silencedetect(stderr):
    """Return [(start, end|None)] from ffmpeg silencedetect stderr."""
    return _spans(None, stderr, "silence_start", "silence_end")


def parse_ebur128(stderr):
    """Return {'integrated': LUFS, 'lra': LU, 'true_peak': dBTP} or Nones."""
    integrated = re.findall(r"I:\s*(-?[0-9.]+)\s*LUFS", stderr)
    lra = re.findall(r"LRA:\s*(-?[0-9.]+)\s*LU", stderr)
    peak = re.findall(r"Peak:\s*(-?[0-9.]+)\s*dBFS", stderr)
    return {
        "integrated": float(integrated[-1]) if integrated else None,
        "lra": float(lra[-1]) if lra else None,
        "true_peak": float(peak[-1]) if peak else None,
    }


def _stderr(path, args):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), *args,
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=3600,
    )
    return result.stderr


def _video_pass(path, cfg):
    chain = (f"blackdetect=d={cfg['eval_black_min']}:pix_th=0.10,"
             f"freezedetect=n=0.002:d={cfg['eval_freeze_min']}")
    return _stderr(path, ["-map", "0:v:0", "-vf", chain])


def _audio_pass(path, cfg):
    chain = (f"silencedetect=n=-50dB:d={cfg['eval_silence_min']},"
             f"ebur128=peak=true")
    return _stderr(path, ["-map", "0:a:0", "-af", chain])


def _span_findings(spans, rule, severity, label):
    findings = []
    for start, end in spans:
        if end is None:
            message = f"{label} from {start:.2f}s to the end"
        else:
            message = f"{label} {start:.2f}s-{end:.2f}s"
        findings.append(Finding(severity, rule, message, start))
    return findings


def evaluate(path, config, has_audio=True):
    """Run every measurement on a rendered file. Returns Findings."""
    cfg = {**EVAL_DEFAULTS, **{k: v for k, v in config.items() if k in EVAL_DEFAULTS}}
    findings = []

    video = _video_pass(path, cfg)
    findings += _span_findings(parse_blackdetect(video), "black", WARNING,
                               "black picture")
    findings += _span_findings(parse_freezedetect(video), "freeze", WARNING,
                               "frozen picture")

    if not has_audio:
        return findings

    audio = _audio_pass(path, cfg)
    findings += _span_findings(parse_silencedetect(audio), "silence", WARNING,
                               "silence")

    loudness = parse_ebur128(audio)
    target = config.get("lufs_target", -14)
    integrated = loudness["integrated"]
    tolerance = cfg["eval_lufs_tolerance"]
    if integrated is None:
        findings.append(Finding(WARNING, "loudness",
                                "could not measure integrated loudness"))
    elif abs(integrated - target) > tolerance:
        findings.append(Finding(
            ERROR, "loudness",
            f"integrated {integrated:.1f} LUFS is more than {tolerance:g} LU "
            f"from the {target:g} LUFS target"))
    peak = loudness["true_peak"]
    if peak is not None and peak > cfg["eval_true_peak_max"]:
        findings.append(Finding(
            ERROR, "true_peak",
            f"true peak {peak:.1f} dBTP exceeds "
            f"{cfg['eval_true_peak_max']:g} dBTP, the mix will clip"))
    return findings


def blocking(findings):
    return [f for f in findings if f.severity == ERROR]


def promote(findings):
    """Turn every warning into an error (strict mode)."""
    return [Finding(ERROR, f.rule, f.message, f.at) for f in findings]
