#!/usr/bin/env python3
"""Generate a default cutlist for a scythe project.

Scans raw_footage/, builds a simple continuous timeline that passes the
validation gate: no gaps, no filter or effect assumptions, no casing rules.
It is a starting point, not a style - edit or replace it.
"""

import glob
import json
import os
import subprocess
import sys

SEGMENT_SEC = 3.0
MIN_SEC = 0.5
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".mkv")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def assets(project_dir):
    found = []
    for ext in VIDEO_EXTS + IMAGE_EXTS:
        found.extend(glob.glob(os.path.join(project_dir, "raw_footage", "*" + ext)))
    return [os.path.relpath(p, project_dir) for p in sorted(found)]


def duration_sec(asset, project_dir):
    if os.path.splitext(asset)[1].lower() in IMAGE_EXTS:
        return SEGMENT_SEC
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", os.path.join(project_dir, asset)],
        capture_output=True, text=True,
    )
    try:
        value = float(result.stdout.strip())
    except ValueError:
        return SEGMENT_SEC
    return value if value > 0.01 else SEGMENT_SEC


def build(project_dir):
    found = assets(project_dir)
    if not found:
        sys.exit("no video/image assets in raw_footage/ - drop some in and re-run")

    segments = []
    t = 0.0
    for asset in found:
        available = duration_sec(asset, project_dir)
        span = max(MIN_SEC, min(SEGMENT_SEC, available))
        segments.append({
            "start": round(t, 3),
            "end": round(t + span, 3),
            "asset": asset,
            "fade_in": 0.2 if t == 0.0 else 0.0,
        })
        t += span

    _self_check(segments)
    return segments


def _self_check(segments):
    assert segments, "no segments generated"
    assert segments[0]["start"] == 0.0, "timeline must start at 0"
    for i, seg in enumerate(segments):
        assert seg["end"] > seg["start"], f"segment {i} has no duration"
        if i:
            assert seg["start"] == segments[i - 1]["end"], f"gap before {i}"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: generate_cutlist.py <project-dir>")
    project_dir = sys.argv[1]
    segments = build(project_dir)
    prompts = os.path.join(project_dir, "prompts")
    os.makedirs(prompts, exist_ok=True)
    target = os.path.join(prompts, "cutlist.json")
    with open(target, "w") as f:
        json.dump(segments, f, indent=2)
    print(f"cutlist written: {len(segments)} segments, "
          f"{segments[-1]['end']:.1f}s total -> {target}")


if __name__ == "__main__":
    main()
