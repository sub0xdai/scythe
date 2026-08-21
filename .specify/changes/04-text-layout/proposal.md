# 04-text-layout - Proposal

## Problem

Text is a TextClip centered on screen, padded with newlines to dodge Pillow stroke clipping (main.py lines 336-345). No wrapping, no bounding boxes, no safe zones, no per-word timing. `word_flash` is a documented no-op. improve.md section 3 demands responsive containers, kinetic words, and platform safe zones.

## User Stories

- As a user, I want long headlines to wrap inside a defined box instead of overflowing or clipping.
- As a user, I want captions that stay out of the TikTok, Reels, and Shorts UI zones.
- As a user, I want word-by-word flash and karaoke highlight effects.
- As a user, I want animated lower-thirds for names and stats.

## Risks

- .ass burn-in needs fonts inside the container. fonts-liberation is present; project fonts must be copied in per project and documented.
- Karaoke `\k` timing must stay in sync with the segment duration. Verification needs a timing assertion, not a visual check.
- Safe zones are opinionated per platform. Make them theme values with documented defaults so they are adjustable.
- Subtitles burned by the subtitles filter must share the graph's color and pixel format decisions. The format must be settled in Spec B first.
