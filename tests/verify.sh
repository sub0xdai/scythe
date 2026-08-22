#!/usr/bin/env bash
# Single verification gate for scythe (Spec A).
# Regenerates the synthetic fixture, runs the unit suite, renders the fixture,
# checks the output duration, and verifies the gate rejects a broken cutlist.
# Usage: tests/verify.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== 1/5 Generating fixture assets ==="
tests/fixtures/generate_fixture.sh

echo ""
echo "=== 2/5 Unit tests ==="
podman image exists scythe || podman build -t scythe .
podman run --rm --entrypoint python -v "$(pwd):/app:Z" scythe -m unittest discover -s tests -v

echo ""
echo "=== 3/5 Fixture render ==="
./render.sh tests/fixtures/synthetic_project 2>&1 | tail -3

OUT="tests/fixtures/synthetic_project/output/master.mp4"
[ -s "$OUT" ] || { echo "FAIL: $OUT missing or empty"; exit 1; }

WEB="tests/fixtures/synthetic_project/output/web.mp4"
[ -s "$WEB" ] || { echo "FAIL: $WEB missing or empty"; exit 1; }

STREAMS_JSON="$(podman run --rm --entrypoint ffprobe -v "$(pwd):/app:Z" scythe \
    -v error -show_entries stream=codec_type,codec_name,width,height,r_frame_rate \
    -of json "$OUT")"
python3 -c "
import json, sys
data = json.loads(sys.argv[1])
video = next(s for s in data['streams'] if s['codec_type'] == 'video')
audio = next(s for s in data['streams'] if s['codec_type'] == 'audio')
assert (video['codec_name'], video['width'], video['height'], video['r_frame_rate']) == ('h264', 640, 360, '15/1'), video
assert audio['codec_name'] == 'aac', audio
print('streams OK')
" "$STREAMS_JSON"
duration="$(podman run --rm --entrypoint ffprobe -v "$(pwd):/app:Z" scythe \
    -v error -show_entries format=duration -of csv=p=0 "$OUT")"
python3 -c "import sys; assert float(sys.argv[1]) > 0.0, 'render duration must be > 0'" "$duration"
echo "Render OK: ${duration}s (h264 640x360@15, aac + web)"

echo ""
echo "=== 4/5 Negative gate test (missing asset) ==="
BROKEN="$(mktemp -d tests/fixtures/.broken.XXXXXX)"
trap 'rm -rf "$BROKEN"' EXIT
cp -r tests/fixtures/synthetic_project/. "$BROKEN/"
cat > "$BROKEN/prompts/cutlist.json" <<'JSON'
[
  {
    "start": 0.0,
    "end": 1.0,
    "phase": "hook",
    "text": "THE HOOK",
    "asset": "raw_footage/ghost.mp4",
    "filter": "grayscale",
    "effect": "ken_burns_slow"
  }
]
JSON
if podman run --rm -v "$(pwd):/app:Z" scythe --project "$BROKEN" >/tmp/scythe-negative.log 2>&1; then
    echo "FAIL: broken cutlist rendered successfully; expected non-zero exit"
    exit 1
fi
grep -q "ghost.mp4" /tmp/scythe-negative.log || { echo "FAIL: error output does not name ghost.mp4"; exit 1; }
echo "Negative gate OK: render aborted naming ghost.mp4"

echo ""
echo "=== 5/5 --check-gpu smoke ==="
podman run --rm --entrypoint python -v "$(pwd):/app:Z" scythe main.py --check-gpu \
    | python3 -c "
import json, sys
report = json.load(sys.stdin)
assert report['chosen']['encoder'] == 'libx264', report['chosen']
assert report['chosen']['dry_run_ok'] is True, report['chosen']
print('check-gpu OK:', report['chosen']['encoder'])
"

echo ""
echo "ALL GATES PASSED"
