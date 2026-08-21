#!/usr/bin/env bash
# scythe one-command scaffold: deps, clone, project, cutlist + render if assets exist.
#
#   curl -sSL https://raw.githubusercontent.com/sub0xdai/scythe/master/scythe.sh | bash -s my-video
#
# No assets are installed - this is your video. Drop your own clips into
# projects/<name>/raw_footage/ and run the final two commands, or re-run
# this script with assets in place.
#
# Env overrides: SCYTHE_DIR (engine location, default ~/1-projects/scythe)

set -euo pipefail

NAME="${1:-my-video}"
SCYTHE_DIR="${SCYTHE_DIR:-$HOME/1-projects/scythe}"

echo "=== scythe: setting up '$NAME' ==="

if [ ! -d "$SCYTHE_DIR" ]; then
    echo "Cloning scythe into $SCYTHE_DIR"
    git clone --depth 1 https://github.com/sub0xdai/scythe.git "$SCYTHE_DIR"
fi
cd "$SCYTHE_DIR"

echo "=== 1/3 host dependencies ==="
./scripts/install_deps.sh

echo "=== 2/3 scaffold ==="
./bootstrap.sh "$NAME"

echo "=== 3/3 project ready ==="
PROJECT="projects/$NAME"
FOUND="$(find "$PROJECT/raw_footage" -maxdepth 1 -type f \
    \( -name '*.mp4' -o -name '*.mov' -o -name '*.webm' -o -name '*.mkv' \
    -o -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.webp' \) \
    2>/dev/null | head -1)"
if [ -n "$FOUND" ]; then
    echo "Assets found - generating a default cutlist and rendering"
    python3 scripts/generate_cutlist.py "$PROJECT"
    ./render.sh "$PROJECT"
else
    echo "Drop your assets into:"
    echo "  $PWD/$PROJECT/raw_footage/   (video clips, images)"
    echo "  $PWD/$PROJECT/audio/         (soundtrack, optional voiceover)"
    echo "Then run:"
    echo "  python3 scripts/generate_cutlist.py $PROJECT"
    echo "  ./render.sh $PROJECT"
    echo "(or drop an LLM cutlist at $PROJECT/prompts/cutlist.json)"
fi
