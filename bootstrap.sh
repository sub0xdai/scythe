#!/usr/bin/env bash
# Bootstrap a new kinetic content project from the scaffold template.
# Usage: ./bootstrap.sh <project-name>
#   ./bootstrap.sh my-video   →  creates projects/my-video/

set -euo pipefail

NAME="${1:-}"
if [ -z "$NAME" ]; then
    echo "Usage: ./bootstrap.sh <project-name>"
    echo "  Creates projects/<project-name>/ from templates/project/"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTENT_DIR="$(dirname "$SCRIPT_DIR")"
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
echo "  3. Generate cutlist: feed prompts/brutalist-video-prompt.md to an LLM, save as projects/$NAME/prompts/cutlist.json"
echo "  4. Render:          python main.py --project projects/$NAME"
