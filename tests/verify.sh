#!/usr/bin/env bash
# Single verification gate for n0x-content (Spec A).
# Regenerates the synthetic fixture, runs the unit suite, renders the fixture,
# checks the output duration, and verifies the gate rejects a broken cutlist.
# Usage: tests/verify.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== 1/4 Generating fixture assets ==="
tests/fixtures/generate_fixture.sh

echo ""
echo "=== 2/4 Unit tests ==="
podman image exists kinetic-renderer || podman build -t kinetic-renderer .
podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v

echo ""
echo "=== 3/4 Fixture render ==="
./render.sh tests/fixtures/synthetic_project 2>&1 | tail -3

OUT="tests/fixtures/synthetic_project/output/render.mp4"
[ -s "$OUT" ] || { echo "FAIL: $OUT missing or empty"; exit 1; }

DURATION="$(podman run --rm --entrypoint ffprobe -v "$(pwd):/app:Z" kinetic-renderer \
    -v error -show_entries format=duration -of csv=p=0 "$OUT")"
python3 -c "import sys; assert float(sys.argv[1]) > 0.0, 'render duration must be > 0'" "$DURATION"
echo "Render OK: duration=${DURATION}s"

echo ""
echo "=== 4/4 Negative gate test (missing asset) ==="
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
if podman run --rm -v "$(pwd):/app:Z" kinetic-renderer --project "$BROKEN" >/tmp/n0x-negative.log 2>&1; then
    echo "FAIL: broken cutlist rendered successfully; expected non-zero exit"
    exit 1
fi
grep -q "ghost.mp4" /tmp/n0x-negative.log || { echo "FAIL: error output does not name ghost.mp4"; exit 1; }
echo "Negative gate OK: render aborted naming ghost.mp4"

echo ""
echo "ALL GATES PASSED"
