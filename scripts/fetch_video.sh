#!/usr/bin/env bash
# Fetch public domain films from the Internet Archive.
# Usage: ./fetch_video.sh <target_dir> [identifier]
#   ./fetch_video.sh projects/my-video/raw_footage
#   ./fetch_video.sh projects/my-video/raw_footage Scipione_l_africano_1937

set -euo pipefail

TARGET="${1:-}"
IDENTIFIER="${2:-}"

if [ -z "$TARGET" ]; then
    echo "Usage: ./fetch_video.sh <target_dir> [ia_identifier]"
    echo "  ./fetch_video.sh projects/my-video/raw_footage"
    echo "  ./fetch_video.sh projects/my-video/raw_footage Scipione_l_africano_1937"
    echo ""
    echo "Known public domain identifiers:"
    echo "  Scipione_l_africano_1937  — Roman epic, 1937"
    echo "  Cabiria_1914              — Italian silent epic"
    echo "  (pass any Internet Archive identifier)"
    exit 1
fi

if ! command -v ia &>/dev/null; then
    echo "ERROR: 'ia' not found. Run ./scripts/install_deps.sh first."
    exit 1
fi

mkdir -p "$TARGET"
cd "$TARGET"

# Default to Scipio if no identifier given
if [ -z "$IDENTIFIER" ]; then
    echo "=== No identifier given — fetching default: Scipione_l_africano_1937 ==="
    IDENTIFIER="Scipione_l_africano_1937"
else
    echo "=== Fetching: $IDENTIFIER ==="
fi

ia download "$IDENTIFIER" --glob="*.mp4"

echo ""
echo "=== Video fetched → $TARGET ==="
ls -lh *.mp4 2>/dev/null || echo "  (no .mp4 files downloaded)"
