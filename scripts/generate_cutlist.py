#!/usr/bin/env python3
"""Generate a valid default cutlist for a scythe project.

Scans raw_footage/, builds a contiguous brutalist-style timeline that
passes the scythe validation gate: no gaps, distinct adjacent filters,
white_flash only with identity effects, UPPERCASE 2-5 word text.
Self-checks its own invariants before writing.
"""

import glob
import json
import os
import subprocess
import sys

HOOK_SEC = 2.0
DROP_SEC = 0.08
KINETIC_SEC = 1.2
FILTERS = ["grayscale", "color_invert", "chromatic_aberration",
           "high_contrast_green", "film_grain", "high_contrast_red"]
PHRASES = ["BUILD THE MACHINE", "NO EXCUSES", "MOVE FAST", "STAY SHARP",
           "MAKE IT LOUD", "OWN THE MOMENT", "KEEP PUSHING", "NO LIMITS"]
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".mkv")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def assets(project_dir):
    out = []
    for ext in VIDEO_EXTS + IMAGE_EXTS:
        out.extend(glob.glob(os.path.join(project_dir, "raw_footage", "*" + ext)))
    return [os.path.relpath(p, project_dir) for p in sorted(out)]


def duration_sec(asset, project_dir):
    if os.path.splitext(asset)[1].lower() in IMAGE_EXTS:
        return KINETIC_SEC
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", os.path.join(project_dir, asset)],
        capture_output=True, text=True,
    )
    try:
        value = float(result.stdout.strip())
        return value if value > 0.5 else KINETIC_SEC
    except ValueError:
        return KINETIC_SEC


def build(project_dir):
    found = assets(project_dir)
    if not found:
        sys.exit("no video/image assets in raw_footage/ - drop some in and re-run")

    segments = []
    t = 0.0

    # hook: first asset, slow zoom, monochrome, tension text
    hook_dur = min(HOOK_SEC, duration_sec(found[0], project_dir))
    segments.append({
        "start": round(t, 3), "end": round(t + hook_dur, 3),
        "phase": "hook", "text": PHRASES[0], "asset": found[0],
        "filter": "grayscale", "effect": "ken_burns_slow",
    })
    t += hook_dur

    # drop: white flash strobe
    segments.append({
        "start": round(t, 3), "end": round(t + DROP_SEC, 3),
        "phase": "drop_transition", "text": None, "asset": None,
        "filter": "white_flash", "effect": "strobe",
    })
    t += DROP_SEC

    # kinetic: cycle assets, filters, texts with snap zoom
    for i in range(len(found)):
        asset = found[i]
        dur = min(KINETIC_SEC, duration_sec(asset, project_dir))
        segments.append({
            "start": round(t, 3), "end": round(t + dur, 3),
            "phase": "kinetic_cut", "text": PHRASES[(i + 1) % len(PHRASES)],
            "asset": asset, "filter": FILTERS[i % len(FILTERS)],
            "effect": "snap_zoom",
        })
        t += dur

    _self_check(segments)
    return segments


def _self_check(segments):
    assert segments and segments[0]["start"] == 0.0
    for i in range(len(segments) - 1):
        assert segments[i]["end"] == segments[i + 1]["start"], "timeline gap"
        filter_a = segments[i].get("filter")
        filter_b = segments[i + 1].get("filter")
        assert filter_a is None or filter_b is None or filter_a != filter_b
    for seg in segments:
        assert seg["end"] > seg["start"]
        if seg["filter"] == "white_flash":
            assert seg["text"] is None
            assert seg["effect"] in (None, "strobe", "word_flash")
        elif seg.get("text"):
            words = seg["text"].split()
            assert 2 <= len(words) <= 5 and seg["text"].isupper()


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: generate_cutlist.py <project-dir>")
    project_dir = sys.argv[1]
    segments = build(project_dir)
    prompts = os.path.join(project_dir, "prompts")
    os.makedirs(prompts, exist_ok=True)
    with open(os.path.join(prompts, "cutlist.json"), "w") as f:
        json.dump(segments, f, indent=2)
    print(f"cutlist written: {len(segments)} segments, "
          f"{segments[-1]['end']:.1f}s total")


if __name__ == "__main__":
    main()
