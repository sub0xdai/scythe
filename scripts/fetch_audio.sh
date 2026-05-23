#!/usr/bin/env bash
# Fetch royalty-free audio tracks and voiceover assets.
# Usage: ./fetch_audio.sh <target_dir> [query]
#   ./fetch_audio.sh projects/my-video/audio
#   ./fetch_audio.sh projects/my-video/audio "royalty free phonk aggressive"

set -euo pipefail

TARGET="${1:-}"
QUERY="${2:-royalty free drill beat aggressive}"

if [ -z "$TARGET" ]; then
    echo "Usage: ./fetch_audio.sh <target_dir> [search_query]"
    echo "  ./fetch_audio.sh projects/my-video/audio"
    echo "  ./fetch_audio.sh projects/my-video/audio 'dark industrial phonk 140bpm'"
    exit 1
fi

mkdir -p "$TARGET"
cd "$TARGET"

echo "=== Fetching audio ==="
echo "  Target: $TARGET"
echo "  Query:  $QUERY"
echo ""

# Fetch 5 tracks from YouTube as WAV
yt-dlp \
    "ytsearch5:${QUERY}" \
    -x --audio-format wav \
    -o "%(title)s.%(ext)s" \
    --no-playlist \
    --extract-audio

echo ""
echo "=== Audio fetched → $TARGET ==="
ls -lh *.wav 2>/dev/null || echo "  (no tracks downloaded)"
