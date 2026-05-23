#!/usr/bin/env bash
# Scrape public domain Wikimedia Commons categories for images.
# Usage: ./fetch_images.sh <target_dir> [category_url]
#   ./fetch_images.sh projects/my-video/overlays
#   ./fetch_images.sh projects/my-video/overlays "https://commons.wikimedia.org/wiki/Category:Statues_of_Marcus_Aurelius"

set -euo pipefail

TARGET="${1:-}"
CATEGORY_URL="${2:-https://commons.wikimedia.org/wiki/Category:Ancient_Roman_statues_in_the_Louvre}"

if [ -z "$TARGET" ]; then
    echo "Usage: ./fetch_images.sh <target_dir> [wikimedia_category_url]"
    echo "  ./fetch_images.sh projects/my-video/overlays"
    echo "  ./fetch_images.sh projects/my-video/raw_footage 'https://commons.wikimedia.org/wiki/Category:Statues_of_Marcus_Aurelius'"
    echo ""
    echo "Suggested categories:"
    echo "  Statues_of_Marcus_Aurelius"
    echo "  Ancient_Roman_statues_in_the_Louvre"
    echo "  Roman_sculptures_in_the_Vatican_Museums"
    exit 1
fi

mkdir -p "$TARGET"
cd "$TARGET"

echo "=== Scraping images ==="
echo "  Target:   $TARGET"
echo "  Category: $CATEGORY_URL"
echo ""

wget -nd -r -P . -A jpeg,jpg,png -e robots=off "$CATEGORY_URL" 2>&1 | tail -5

echo ""
echo "=== Images scraped → $TARGET ==="
count=$(find . -maxdepth 1 \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) 2>/dev/null | wc -l)
echo "  Downloaded: $count images"
