#!/usr/bin/env bash
# Master ingestion orchestrator — fetches all assets into a project.
# Usage: ./ingest.sh <project-dir> [--audio-query "query"] [--ia-id "identifier"] [--image-cat "url"]
#
# Examples:
#   ./ingest.sh projects/my-video
#   ./ingest.sh projects/my-video --audio-query "dark industrial phonk 140bpm"
#   ./ingest.sh projects/my-video --ia-id Cabiria_1914 --no-images
#   ./ingest.sh projects/my-video --no-audio --no-video

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Defaults ──
AUDIO_QUERY="royalty free aggressive drill beat phonk"
IA_ID="Scipione_l_africano_1937"
IMAGE_CAT="https://commons.wikimedia.org/wiki/Category:Ancient_Roman_statues_in_the_Louvre"
FETCH_AUDIO=true
FETCH_VIDEO=true
FETCH_IMAGES=true
PREPROCESS=true

# ── Parse args ──
PROJECT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --audio-query) AUDIO_QUERY="$2"; shift 2 ;;
        --ia-id)       IA_ID="$2"; shift 2 ;;
        --image-cat)   IMAGE_CAT="$2"; shift 2 ;;
        --no-audio)    FETCH_AUDIO=false; shift ;;
        --no-video)    FETCH_VIDEO=false; shift ;;
        --no-images)   FETCH_IMAGES=false; shift ;;
        --no-preprocess) PREPROCESS=false; shift ;;
        -*) echo "Unknown flag: $1"; exit 1 ;;
        *)  PROJECT="$1"; shift ;;
    esac
done

if [ -z "$PROJECT" ]; then
    echo "Usage: ./ingest.sh <project-dir> [options]"
    echo ""
    echo "Options:"
    echo "  --audio-query STR   Search query for yt-dlp (default: drill beat phonk)"
    echo "  --ia-id STR         Internet Archive identifier (default: Scipione_l_africano_1937)"
    echo "  --image-cat URL     Wikimedia Commons category URL"
    echo "  --no-audio          Skip audio fetching"
    echo "  --no-video          Skip video fetching"
    echo "  --no-images         Skip image scraping"
    echo "  --no-preprocess     Skip monochrome crush"
    echo ""
    echo "Examples:"
    echo "  ./ingest.sh projects/my-video"
    echo "  ./ingest.sh projects/my-video --audio-query 'dark phonk 150bpm' --ia-id Cabiria_1914"
    exit 1
fi

# ── Scaffold if missing ──
if [ ! -d "$PROJECT" ]; then
    echo "=== Project not found, scaffolding from template ==="
    "$SCRIPT_DIR/bootstrap.sh" "$(basename "$PROJECT")"
fi

echo "============================================"
echo "  INGEST → $PROJECT"
echo "============================================"
echo "  Audio:   $FETCH_AUDIO  ($AUDIO_QUERY)"
echo "  Video:   $FETCH_VIDEO  ($IA_ID)"
echo "  Images:  $FETCH_IMAGES ($(basename "$IMAGE_CAT"))"
echo "  Preproc: $PREPROCESS"
echo "============================================"
echo ""

# ── Fetch audio ──
if $FETCH_AUDIO; then
    "$SCRIPT_DIR/scripts/fetch_audio.sh" "$PROJECT/audio" "$AUDIO_QUERY"
    echo ""
fi

# ── Fetch video ──
if $FETCH_VIDEO; then
    "$SCRIPT_DIR/scripts/fetch_video.sh" "$PROJECT/raw_footage" "$IA_ID"
    echo ""
fi

# ── Fetch images ──
if $FETCH_IMAGES; then
    "$SCRIPT_DIR/scripts/fetch_images.sh" "$PROJECT/overlays" "$IMAGE_CAT"
    echo ""
fi

# ── Preprocess (monochrome crush) ──
if $PREPROCESS; then
    if [ -d "$PROJECT/raw_footage" ] && ls "$PROJECT/raw_footage"/*.mp4 &>/dev/null; then
        "$SCRIPT_DIR/scripts/preprocess.sh" "$PROJECT/raw_footage"
    else
        echo "=== Skipping preprocess: no .mp4 files in $PROJECT/raw_footage ==="
    fi
    echo ""
fi

echo "============================================"
echo "  INGEST COMPLETE"
echo "============================================"
echo ""
echo "Project: $PROJECT"
echo "  $(find "$PROJECT/audio" -type f 2>/dev/null | wc -l) audio files"
echo "  $(find "$PROJECT/raw_footage" -type f 2>/dev/null | wc -l) raw footage files"
echo "  $(find "$PROJECT/overlays" -type f -not -name '.gitkeep' 2>/dev/null | wc -l) overlay files"
echo ""
echo "Next: generate cutlist → feed prompts/brutalist-video-prompt.md to an LLM"
echo "Then: render           → ./render.sh $PROJECT"
