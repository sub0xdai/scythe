#!/usr/bin/env bash
# Standardize video assets into brutalist monochrome + contrast crush.
# Usage: ./preprocess.sh <input_dir> [output_dir]
#   ./preprocess.sh projects/my-video/raw_footage
#   ./preprocess.sh downloads/ projects/my-video/raw_footage

set -euo pipefail

INPUT="${1:-}"
OUTPUT="${2:-}"

if [ -z "$INPUT" ]; then
    echo "Usage: ./preprocess.sh <input_dir> [output_dir]"
    echo "  ./preprocess.sh projects/my-video/raw_footage"
    echo "  ./preprocess.sh downloads/ projects/my-video/raw_footage"
    echo ""
    echo "Applies to all .mp4: desaturate, contrast +50%, slight darken."
    exit 1
fi

if [ ! -d "$INPUT" ]; then
    echo "ERROR: directory not found: $INPUT"
    exit 1
fi

# If no output dir given, process in-place with _crushed suffix
IN_PLACE=false
if [ -z "$OUTPUT" ]; then
    IN_PLACE=true
fi

if [ "$IN_PLACE" = false ]; then
    mkdir -p "$OUTPUT"
fi

echo "=== Preprocessing assets ==="
echo "  Input:  $INPUT"
if [ "$IN_PLACE" = true ]; then
    echo "  Mode:   in-place (adds _crushed suffix)"
else
    echo "  Output: $OUTPUT"
fi
echo "  Filter: desaturate + contrast=1.5 + brightness=-0.1"
echo ""

shopt -s nullglob
videos=("$INPUT"/*.mp4)
shopt -u nullglob

if [ ${#videos[@]} -eq 0 ]; then
    echo "No .mp4 files found in $INPUT"
    exit 0
fi

for video in "${videos[@]}"; do
    basename="$(basename "$video" .mp4)"

    if [ "$IN_PLACE" = true ]; then
        out="$INPUT/${basename}_crushed.mp4"
    else
        out="$OUTPUT/${basename}.mp4"
    fi

    echo "  $(basename "$video") → $(basename "$out")"
    ffmpeg -y -i "$video" \
        -vf "hue=s=0,eq=contrast=1.5:brightness=-0.1" \
        -c:a copy \
        "$out" 2>/dev/null
done

echo ""
echo "=== Done ==="
