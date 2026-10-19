#!/usr/bin/env bash

set -euo pipefail

NAME="${1:-}"
if [ -z "$NAME" ]; then
    echo "Usage: ./bootstrap.sh <project-name>"
    echo "  Creates projects/<project-name>/ from templates/project/"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTENT_DIR="$SCRIPT_DIR"
TEMPLATE="$CONTENT_DIR/templates/project"
TARGET="$CONTENT_DIR/projects/$NAME"

if [ -d "$TARGET" ]; then
    echo "Error: $TARGET already exists."
    exit 1
fi

echo "Bootstrapping: $TARGET"
cp -r "$TEMPLATE" "$TARGET"

echo "✓ Created projects/$NAME/"
echo ""
echo "Next steps:"
echo "  1. Add audio:       cp ~/Downloads/track.wav $NAME/audio/"
echo "  2. Add footage:     cp ~/captures/*.mp4 $NAME/raw_footage/"
echo "  3. Cutlist:         python3 scripts/generate_cutlist.py projects/$NAME"
echo "     or feed prompts/video-prompt.md to an LLM and save the JSON"
echo "     as projects/$NAME/prompts/cutlist.json"
echo "  4. Render:          ./render.sh projects/$NAME"
