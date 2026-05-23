# Project Scaffold

Copy this directory to `projects/<name>/` or use `./bootstrap.sh <name>`.

## Quick Start

```bash
# 1. Drop your assets
cp ~/Downloads/soundtrack.mp3 projects/<name>/audio/
cp ~/clips/*.mp4 projects/<name>/raw_footage/

# 2. Configure style (optional)
# Edit config.json — change preset, font, resolution

# 3. Generate cut-list
# Feed prompts/brutalist-video-prompt.md to any LLM
# Save output as prompts/cutlist.json

# 4. Render
python main.py --project projects/<name>
```

## Directory Roles

| Directory | Purpose | Accepts |
|-----------|---------|---------|
| `config.json` | Style: resolution, font, audio offset | JSON |
| `audio/` | Soundtrack + optional voiceover | `.wav`, `.mp3`, `.ogg` |
| `prompts/` | `cutlist.json` | JSON |
| `raw_footage/` | Your video clips + images | `.mp4`, `.mov`, `.gif`, `.jpg`, `.png` |
| `overlays/` | Logos, textures, grids | `.jpg`, `.png`, `.gif` |
| `output/` | Rendered video | auto-generated |
| `video_assets/` | Source clips for beat-detect mode | `.mp4` |

## Audio Convention

- `voice` or `vo.` in filename → voiceover (full volume)
- Everything else → soundtrack (ducked to 30% under VO)
- Single file → plays as-is
