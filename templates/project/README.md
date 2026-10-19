# Project scaffold

Copy this directory to `projects/<name>/` or run `./bootstrap.sh <name>`.

## Quick start

```bash
# 1. Drop your assets in
cp ~/Downloads/soundtrack.mp3 projects/<name>/audio/
cp ~/clips/*.mp4 projects/<name>/raw_footage/

# 2. Style (optional)
$EDITOR projects/<name>/config.json

# 3. Cutlist: generate a starting point, or write one
python3 scripts/generate_cutlist.py projects/<name>
#    or feed prompts/video-prompt.md to any LLM and save
#    the JSON as projects/<name>/prompts/cutlist.json

# 4. Render
./render.sh projects/<name>
#    or: python3 main.py --project projects/<name>
```

## Directory roles

| Path | Purpose | Accepts |
|---|---|---|
| `config.json` | Style: resolution, theme, transitions, loudness | JSON |
| `audio/` | Soundtrack and optional voiceover | `.wav`, `.mp3`, `.ogg` |
| `prompts/` | `cutlist.json` (or a `{tracks: [...]}` document) | JSON |
| `raw_footage/` | Video clips and images | `.mp4`, `.mov`, `.gif`, `.jpg`, `.png` |
| `overlays/` | Logos, textures, grids | `.jpg`, `.png`, `.gif` |
| `output/` | Rendered MP4s and `subtitles.ass` | auto-generated |
| `video_assets/` | Source clips for beat-detect mode | `.mp4` |
| `project.md` | Append-only render history | auto-generated |

## Audio convention

Used only when the cutlist declares no `audio` track:

- `voice` or `vo.` in the filename -> voiceover, gated and denoised, standing
  at full level
- Everything else -> soundtrack, ducked under the voiceover
- A single file -> plays as-is

Declare audio tracks in the cutlist when you want more than that: any number
of beds, each with its own gain, fades, offset and ducking target.
