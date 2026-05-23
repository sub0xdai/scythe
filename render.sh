#!/usr/bin/env bash
# One-shot render: build container (if needed) + run on a project.
# Usage: ./render.sh <project-dir> [--audio-offset S] [--resolution WxH] [--font NAME] [--font-size N]
#
# Examples:
#   ./render.sh projects/my-video
#   ./render.sh projects/my-video --audio-offset 40
#   ./render.sh projects/my-video --resolution 1920x1080 --font LiberationSans-Bold

set -euo pipefail

PROJECT=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --resolution|--font|--font-size)
            EXTRA_ARGS+=("$1" "$2"); shift 2 ;;
        --audio-offset)
            EXTRA_ARGS+=("$1" "$2"); shift 2 ;;
        -*)
            echo "Unknown flag: $1"; exit 1 ;;
        *)
            PROJECT="$1"; shift ;;
    esac
done

if [ -z "$PROJECT" ]; then
    echo "Usage: ./render.sh <project-dir> [options]"
    echo "  --resolution WxH     Override resolution (e.g. 1920x1080)"
    echo "  --font NAME          Override font"
    echo "  --font-size N        Override font size"
    echo "  --audio-offset S     Start N seconds into audio"
    echo ""
    echo "Examples:"
    echo "  ./render.sh projects/my-video"
    echo "  ./render.sh projects/my-video --resolution 1920x1080"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Building container (cached) ==="
podman build -t kinetic-renderer .

echo ""
echo "=== Rendering: $PROJECT ==="
podman run --rm -v "$(pwd):/app:Z" kinetic-renderer --project "$PROJECT" "${EXTRA_ARGS[@]}"

echo ""
echo "Done → $(pwd)/$PROJECT/output/render.mp4"
