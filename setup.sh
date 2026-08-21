#!/usr/bin/env bash
# scythe one-command setup: deps, scaffold, ingest, default cutlist, render.
#
#   curl -sSL https://raw.githubusercontent.com/sub0xdai/scythe/master/setup.sh | bash -s my-video
#   curl -sSL https://raw.githubusercontent.com/sub0xdai/scythe/master/setup.sh | bash -s my-video --no-video --no-images
#
# Env overrides: SCYTHE_DIR (engine location, default ~/1-projects/scythe)

set -euo pipefail

NAME="${1:-my-video}"
shift || true
SCYTHE_DIR="${SCYTHE_DIR:-$HOME/1-projects/scythe}"

echo "=== scythe: setting up '$NAME' ==="

if [ ! -d "$SCYTHE_DIR" ]; then
    echo "Cloning scythe into $SCYTHE_DIR"
    git clone --depth 1 https://github.com/sub0xdai/scythe.git "$SCYTHE_DIR"
fi
cd "$SCYTHE_DIR"

echo "=== 1/5 host dependencies ==="
./scripts/install_deps.sh

echo "=== 2/5 scaffold ==="
./bootstrap.sh "$NAME"

echo "=== 3/5 asset ingestion ==="
./ingest.sh "projects/$NAME" "$@"

echo "=== 4/5 default cutlist ==="
python3 scripts/generate_cutlist.py "projects/$NAME"

echo "=== 5/5 render ==="
./render.sh "projects/$NAME"

echo ""
echo "Done: $PWD/projects/$NAME/output/render.mp4"
