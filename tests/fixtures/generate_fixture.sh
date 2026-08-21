#!/usr/bin/env bash
# Generate the synthetic fixture project assets deterministically with ffmpeg.
# Idempotent: safe to re-run, overwrites existing generated media.
# Usage: tests/fixtures/generate_fixture.sh

set -euo pipefail

FIXTURE="$(cd "$(dirname "$0")" && pwd)/synthetic_project"

mkdir -p "$FIXTURE/raw_footage" "$FIXTURE/audio" "$FIXTURE/overlays"

# 2s test video, 360x640 @ 15fps
ffmpeg -y -f lavfi -i "testsrc2=size=360x640:rate=15:duration=2" \
    -pix_fmt yuv420p "$FIXTURE/raw_footage/clip.mp4" 2>/dev/null

# Single-frame gray image
ffmpeg -y -f lavfi -i "color=c=0x606060:size=360x640:duration=1" \
    -frames:v 1 "$FIXTURE/raw_footage/photo.png" 2>/dev/null

# 4s soundtrack and voiceover (names trigger the ducking path)
ffmpeg -y -f lavfi -i "sine=frequency=220:duration=4" \
    -c:a pcm_s16le "$FIXTURE/audio/soundtrack.wav" 2>/dev/null
ffmpeg -y -f lavfi -i "sine=frequency=440:duration=4" \
    -c:a pcm_s16le "$FIXTURE/audio/voiceover.wav" 2>/dev/null

echo "fixture assets generated in $FIXTURE"
