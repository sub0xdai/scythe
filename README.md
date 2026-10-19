# scythe

_headless content and video editing engine_

![scythe](assets/scythe.jpg)

> Describe the edit as JSON, get MP4s. One ffmpeg pass per render, zero frame loops.

scythe is an editing engine, not a style. It takes footage, images and audio
plus a cutlist that describes the timeline, and compiles it into a single
ffmpeg filtergraph: cuts, transitions, keyframed camera moves, speed ramps,
layered video tracks, a mixed and mastered audio timeline, burned captions.
The look comes from your cutlist and your theme, never from the engine.

## Quick start

```bash
curl -sSL https://raw.githubusercontent.com/sub0xdai/scythe/master/scythe.sh | bash -s my-video
```

Installs host deps, clones the engine if missing, and scaffolds
`projects/my-video/`. No assets are installed - this is your video:

```bash
cp ~/clips/*.mp4 projects/my-video/raw_footage/
cp ~/Downloads/soundtrack.mp3 projects/my-video/audio/
cp ~/Downloads/voiceover.wav projects/my-video/audio/   # optional
python3 scripts/generate_cutlist.py projects/my-video   # valid starting cutlist
./render.sh projects/my-video
```

Prefer an authored cutlist? Feed `prompts/video-prompt.md` to any LLM, save the
JSON as `projects/my-video/prompts/cutlist.json`, then `./render.sh
projects/my-video`.

## What it does

1. **Validates** the cutlist against a JSON schema and the cross-field rules
   before any render work. Bad input fails fast, naming every violation.
2. **Compiles** the timeline into one ffmpeg filtergraph: cuts, xfade
   transitions, keyframed camera moves, speed changes, per-segment looks, LUT
   grading, layered video tracks composited by time window.
3. **Burns captions** from a generated `.ass` file: wrapped, safe-zone
   positioned, karaoke word reveal, lower-thirds.
4. **Masters audio** in the same pass: any number of tracks with per-track
   gain, fades, offsets, denoise, noise gate, sidechain ducking, loudnorm.
5. **Encodes on the GPU** when one is present (NVENC, VAAPI, QSV,
   VideoToolbox) after a dry-run check. No GPU means libx264, unchanged.
6. **Verifies and evaluates** every output before it replaces the old file:
   duration to the frame, frame count, frozen picture, black runs, silence,
   integrated loudness, true peak. Failures leave the previous file alone.
7. **Records** each render in `<project>/project.md` so the next session knows
   what was built.
8. **Emits JSON progress events** on stdout in machine mode (`--json`).

## Project structure

```
projects/my-video/
├── config.json       # Style: theme, resolution, transitions, outputs
├── audio/            # soundtrack + voiceover (auto-detected)
├── prompts/          # cutlist.json
├── raw_footage/      # Your video clips + images
├── overlays/         # Logos, textures, grids
├── output/           # master.mp4 + web.mp4 (+ subtitles.ass)
└── project.md        # Append-only render history
```

## The cutlist

A cutlist is either a **segment array** (one video track) or a **document**
with tagged tracks. Both are validated.

```json
[
  { "start": 0.0, "end": 3.0, "asset": "raw_footage/a.mp4", "text": "Opening line" },
  { "start": 3.0, "end": 6.5, "asset": "raw_footage/b.mp4",
    "transition": "cross_dissolve", "transition_duration": 0.6,
    "keyframes": [{"at": 0, "scale": 1.0}, {"at": 1, "scale": 1.15}] }
]
```

```json
{
  "version": 2,
  "tracks": [
    { "kind": "video", "id": "base", "segments": [
      { "start": 0.0, "end": 6.0, "asset": "raw_footage/a.mp4" }
    ]},
    { "kind": "video", "id": "pip", "x": 1180, "y": 620, "scale": 0.3,
      "opacity": 0.95, "segments": [
        { "start": 1.0, "end": 4.0, "asset": "raw_footage/b.mp4",
          "fade_in": 0.3, "fade_out": 0.3 }
      ]},
    { "kind": "audio", "id": "music", "asset": "audio/track.mp3",
      "gain": 0.7, "fade_in": 1.0, "fade_out": 2.0, "duck_under": ["voice"] },
    { "kind": "audio", "id": "voice", "asset": "audio/vo.wav", "cleanup": true }
  ]
}
```

### The rules the engine enforces

Correctness only. Structure, pacing, casing, filter variety and segment count
are yours.

1. `start` and `end` are required, seconds, `end > start`.
2. The first video track is the base: it starts at 0 and is continuous.
3. Other video tracks may have gaps but end inside the base timeline.
4. Every `asset` exists and probes as media.
5. `filter` / `effect` / `transition` resolve to a real implementation or use
   the `raw:` passthrough.
6. `keyframes` and `effect` are mutually exclusive.
7. A transition is shorter than the segment it enters.
8. `duck_under` names tracks that exist.

The full field table is in `schemas/cutlist.schema.json` and
`prompts/video-prompt.md`.

### Segment fields

| Field | Meaning |
|---|---|
| `start`, `end` | Timeline position, seconds |
| `asset` | Source path relative to the project; omit for a solid frame |
| `color` | Solid frame color when there is no asset |
| `clip_start`, `clip_end` | Source in and out points |
| `speed` | Playback rate (`0.5` half, `2.0` double) |
| `filter`, `effect` | Named look / camera move, or `raw:<ffmpeg chain>` |
| `keyframes` | `[{"at": 0..1, "scale": 1.2, "x": -40, "y": 0}]` |
| `fade_in`, `fade_out` | Seconds; alpha on overlay tracks |
| `opacity`, `x`, `y` | Overlay track placement |
| `transition`, `transition_duration` | Transition into this segment |
| `text`, `lower_third` | Burned caption / title block |
| `phase` | Your own label, not interpreted |
| `overlays` | Alpha layers composited over the segment |

### Filters and effects

Named filters: `grayscale`, `color_invert`, `color_crush`,
`high_contrast_green`, `high_contrast_red`, `chromatic_aberration`,
`film_grain`, `warm`, `cool`, `soft`, `white_flash`.

Named effects: `ken_burns_slow` (8% eased zoom), `ken_burns_fast` (15%),
`snap_zoom` (instant 30% at midpoint), `strobe`, `word_flash`.

Anything else: `"filter": "raw:eq=contrast=1.2:saturation=0.8"`. The name
registry is a shortcut, not a whitelist - the whole libavfilter set is
reachable.

### Transitions

`hard_cut` (default), `cross_dissolve`, `dip_to_black`, `dip_to_white`,
`luma_wipe`, `slide_left/right/up/down`, `circle_open/close`, `wipe_left/right`,
`pixelize`, `radial`, `dissolve`, or any `xfade` transition name. Set
`transition_mode` in config for the whole timeline, or `transition` per
segment to override a single cut.

## config.json

```json
{
  "preset": "widescreen",
  "theme": "clean_editorial",
  "lut": "grade/teal.cube",
  "transition_mode": "cross_dissolve",
  "transition_duration": 0.3,
  "ken_burns_easing": "cubic",
  "lufs_target": -14,
  "duck_threshold": 0.02,
  "duck_ratio": 2,
  "voice_cleanup": true,
  "safe_zone_bottom": 0.25,
  "eval_lufs_tolerance": 3.0,
  "outputs": [
    { "name": "master", "crf": 18 },
    { "name": "web", "max_height": 720, "crf": 23 }
  ]
}
```

Precedence: defaults < theme < preset < config.json < CLI flags.

Engine defaults are neutral: `LiberationSans` at 64px, 2px stroke, hard cuts,
no default filter or effect, -14 LUFS. Every opinion lives in a theme.

### Themes

| Theme | Look |
|---|---|
| `clean_editorial` | Sans-serif, grayscale default, cross-dissolves, cubic easing |
| `documentary` | Serif, -16 LUFS, slower dissolves, higher safe zone |
| `minimalist` | Sans-serif, thin stroke, color crush, hard cuts |
| `brutalist` | Serif heavy, grayscale default, hard cuts, monochrome crush |

Themes live in `themes/`. `"theme"` accepts a name or a path to a JSON file.

### Presets

| Preset | Resolution |
|---|---|
| `widescreen` | 1920x1080 (default) |
| `vertical` | 1080x1920 |
| `square` | 1080x1080 |
| `story` | 1080x1920 |
| `cinematic` | 1920x1080 |
| `4k` | 3840x2160 |

### Outputs

One MP4 per entry in `outputs`, in a single pass:

- `master.mp4` - project resolution, higher quality
- `web.mp4` - scaled to max 720p height
- `max_height` scales down only; `resolution` sets an exact size
- A single entry renders one file

## CLI

```bash
python main.py --project projects/my-video                 # render
python main.py --project projects/my-video --json          # machine events
python main.py --project projects/my-video --strict        # warnings fail
python main.py --project projects/my-video --no-eval       # skip evaluation
python main.py --project projects/my-video --note "v2 grade"
python main.py --check-gpu                                 # encoder report
NOX_GPU=off python main.py --project projects/my-video     # force CPU
NOX_ENCODER=h264_nvenc python main.py --project ...        # force encoder
```

`NOX_JSON=1`, `NOX_EVAL=0` and `NOX_STRICT=1` are the env equivalents.

## Verification and evaluation

Two gates run on every output before it is renamed into place.

**Verification** (`src/verify.py`) is structural: container duration against
the timeline within a frame, frame count against `duration * fps`, and no
frozen picture across a cut between different sources.

**Evaluation** (`src/eval.py`) measures the file, it does not assume:
frozen picture runs, black runs, silence, integrated loudness against the
target, true peak against clipping. Errors block the render; warnings are
reported and written to `project.md`.

```bash
tests/verify.sh
```

## GPU acceleration

Renders auto-detect hardware encoders with a dry-run check (a 0.2s null
encode). No GPU means libx264, unchanged behavior.

`render.sh` auto-detects usable devices on the host and passes them to the
container: the NVIDIA CDI device when the NVIDIA container toolkit is present,
and `/dev/dri/renderD128` when it exists.

```bash
./render.sh projects/my-video              # auto-detect
./render.sh projects/my-video --gpu nvidia # requires nvidia-container-toolkit
./render.sh projects/my-video --gpu vaapi  # passes /dev/dri
./render.sh projects/my-video --gpu qsv
```

- `python main.py --check-gpu` prints the capability report and exits
  non-zero when the chosen encoder is not invokable.
- The VAAPI/QSV profiles assume `/dev/dri/renderD128`.

## Ingestion scripts

| Script | Purpose |
|---|---|
| `./ingest.sh projects/name` | Master orchestrator (scaffold + fetch all) |
| `scripts/fetch_audio.sh <dir> [query]` | yt-dlp extracts royalty-free WAVs |
| `scripts/fetch_video.sh <dir> [ia_id]` | Internet Archive public domain films |
| `scripts/fetch_images.sh <dir> [url]` | wget Wikimedia Commons scrape |
| `scripts/preprocess.sh <dir>` | ffmpeg monochrome + contrast crush |

## Layout

```
main.py                 CLI and orchestration
src/tracks.py           cutlist document -> Timeline (tagged track unions)
src/compiler/graph.py   Timeline -> one ffmpeg invocation
src/compiler/video.py   filter and effect chains, raw: passthrough
src/compiler/keyframes.py  keyframes -> libavfilter expressions
src/compiler/text.py    .ass caption generation
src/validator.py        pre-render gate
src/verify.py           post-render structural gate
src/eval.py             post-render measurement
src/memory.py           project.md append
src/themes.py           theme loading
schemas/                cutlist JSON schema
prompts/                LLM cutlist prompt
themes/                 look presets
```

## Dependencies

- **System**: `ffmpeg` >= 7, `wget`, `yt-dlp`
- **Container**: Podman or Docker
- **Python**: `jsonschema` (validation). Beat-detect mode additionally needs
  `librosa`, `moviepy`, `numpy`.

## License

MIT. See `LICENSE`.
