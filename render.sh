#!/usr/bin/env bash
# One-shot render: build container (if needed) + run on a project.
# Usage: ./render.sh <project-dir> [--audio-offset S] [--resolution WxH] [--font NAME] [--font-size N] [--gpu nvidia|vaapi|qsv]
#
# Examples:
#   ./render.sh projects/my-video
#   ./render.sh projects/my-video --audio-offset 40
#   ./render.sh projects/my-video --resolution 1920x1080 --font LiberationSans-Bold
#   ./render.sh projects/my-video --gpu nvidia
#   ./render.sh projects/my-video --gpu vaapi

set -euo pipefail

PROJECT=""
GPU=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --resolution|--font|--font-size)
            EXTRA_ARGS+=("$1" "$2"); shift 2 ;;
        --audio-offset)
            EXTRA_ARGS+=("$1" "$2"); shift 2 ;;
        --gpu)
            GPU="$2"; shift 2 ;;
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
    echo "  --gpu nvidia|vaapi|qsv   Pass GPU hardware through to the container"
    echo ""
    echo "Examples:"
    echo "  ./render.sh projects/my-video"
    echo "  ./render.sh projects/my-video --resolution 1920x1080"
    echo "  ./render.sh projects/my-video --gpu nvidia"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GPU_ARGS=()
case "$GPU" in
    "")
        ;;
    nvidia)
        GPU_ARGS=(--gpus all) ;;
    vaapi|qsv)
        GPU_ARGS=(--device /dev/dri/renderD128) ;;
    *)
        echo "Unknown --gpu: $GPU (use nvidia, vaapi, or qsv)"
        exit 1 ;;
esac

if [ "${NOX_DRY_RUN:-}" = "1" ]; then
    echo "podman run --rm ${GPU_ARGS[*]:-} -v \"$(pwd):/app:Z\" scythe --project \"$PROJECT\" ${EXTRA_ARGS[*]:-}"
    exit 0
fi

echo "=== Building container (cached) ==="
podman build -t scythe .

echo ""
echo "=== Rendering: $PROJECT ==="
podman run --rm "${GPU_ARGS[@]}" -v "$(pwd):/app:Z" scythe --project "$PROJECT" "${EXTRA_ARGS[@]}"

echo ""
echo "Done → $(pwd)/$PROJECT/output/render.mp4"
