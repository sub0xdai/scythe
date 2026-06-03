#!/usr/bin/env bash
# One-time dependency installation for the ingestion pipeline.
# Arch Linux + AUR aware. Safe to re-run (--needed / already-installed checks).

# If you do not use arch but you made it this far surely you can work out how to do the needfull 


set -euo pipefail

echo "=== System binaries (pacman) ==="
sudo pacman -S --needed yt-dlp wget ffmpeg

echo ""
echo "=== Python CLI tools (uv, isolated) ==="
if ! command -v ia &>/dev/null; then
    uv tool install internetarchive
    echo "  → ia installed"
else
    echo "  → ia already installed ($(which ia))"
fi

echo ""
echo "=== Dependencies ready ==="
echo "  yt-dlp : $(which yt-dlp)"
echo "  wget    : $(which wget)"
echo "  ffmpeg  : $(which ffmpeg)"
echo "  ia      : $(which ia 2>/dev/null || echo 'restart shell if just installed')"
