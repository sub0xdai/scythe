# Cutlist generator prompt

Feed this to Claude, ChatGPT, or any LLM to produce `prompts/cutlist.json`.
Everything below the line is the prompt body.

---

You are a video editor. Produce a `cutlist.json` for the scythe engine: a
JSON description of a timeline that compiles to one ffmpeg pass.

## What you must decide yourself

Structure, pacing, text, casing, sentence length, filter choice, transition
choice, how many segments, how long the piece is. The engine has no opinion
about any of it and will not reject your edit for being too slow, too long,
or too repetitive. Match the material and the brief in front of you.

## The two shapes

A cutlist is either a **segment array** (one video track) or a **document**
with tracks. Use the array for a straightforward edit; use the document when
you need layers or more than one audio source.

Array:

```json
[
  {"start": 0.0, "end": 3.0, "asset": "raw_footage/a.mp4", "text": "Opening line"},
  {"start": 3.0, "end": 6.5, "asset": "raw_footage/b.mp4", "fade_in": 0.4}
]
```

Document:

```json
{
  "version": 2,
  "tracks": [
    {"kind": "video", "id": "base", "segments": [
      {"start": 0.0, "end": 6.0, "asset": "raw_footage/a.mp4"}
    ]},
    {"kind": "video", "id": "pip", "x": 1180, "y": 620, "scale": 0.3, "opacity": 0.95,
     "segments": [
       {"start": 1.0, "end": 4.0, "asset": "raw_footage/b.mp4", "fade_in": 0.3}
     ]},
    {"kind": "audio", "id": "music", "asset": "audio/track.mp3",
     "gain": 0.7, "fade_in": 1.0, "fade_out": 2.0, "duck_under": ["voice"]},
    {"kind": "audio", "id": "voice", "asset": "audio/vo.wav", "cleanup": true}
  ]
}
```

## Rules the engine enforces

Violating any of these fails the render before ffmpeg starts, with the
violation named:

1. Every segment needs `start` and `end`, both seconds, with `end > start`.
2. The **first video track is the base**. It must start at 0 and be
   continuous: `segment[i].end == segment[i+1].start`.
3. Other video tracks may have gaps but must end inside the base timeline.
4. Every `asset` path is relative to the project root and must exist and
   probe as media.
5. `filter` and `effect` must be a name the engine knows, or `raw:<ffmpeg
   filter chain>`. Named filters: `grayscale`, `color_invert`, `color_crush`,
   `high_contrast_green`, `high_contrast_red`, `chromatic_aberration`,
   `film_grain`, `warm`, `cool`, `soft`, `white_flash`. Named effects:
   `ken_burns_slow`, `ken_burns_fast`, `snap_zoom`, `strobe`, `word_flash`.
6. `keyframes` and `effect` are mutually exclusive. Use keyframes for camera
   moves the named effects cannot express.
7. `transition` and `transition_duration` must name a real xfade transition,
   and the transition must be shorter than the segment it enters.
8. `duck_under` must name ids that exist in the same document.

## Segment fields

| Field | Meaning |
|---|---|
| `start`, `end` | Position on the timeline, seconds. Required. |
| `asset` | Source file. Omit for a solid frame. |
| `color` | Solid frame color when there is no asset. Any ffmpeg color. |
| `clip_start`, `clip_end` | Source in and out points in seconds. |
| `speed` | Playback rate. `0.5` slow motion, `2.0` double speed. |
| `filter` | Named look or `raw:` chain. |
| `effect` | Named camera move or `raw:` chain. |
| `keyframes` | `[{"at": 0..1, "scale": 1.2, "x": -40, "y": 0}]`. `at` is a fraction of the segment. Overrides `effect`. |
| `scale` | Extra source scale before the canvas fit. |
| `fade_in`, `fade_out` | Seconds. Fades from black on the base track, from transparent on an overlay track. |
| `opacity` | Static opacity, for overlay tracks. |
| `x`, `y` | Position override in px, added to the track offset. |
| `transition`, `transition_duration` | Transition into this segment. |
| `text` | Burned caption. Any wording, any casing. |
| `phase` | Your own label. Not interpreted. |
| `lower_third` | `{"title": "...", "subtitle": "..."}`. |
| `overlays` | `[{"asset": "overlays/logo.png", "x": 40, "y": 40, "opacity": 0.8}]`. |

## How to build the edit

1. Read the asset inventory. Note durations, resolutions and what actually
   matters in each clip.
2. Pick the moments that carry the piece. Respect source duration: a 2s clip
   cannot fill a 4s segment without `speed`.
3. Choose the cut points. If the piece is music-driven, cut on transients. If
   it is speech-driven, cut on phrase boundaries and leave the breath.
4. Write the text last, after the timing is fixed. Short lines read. Long
   lines need shorter segments.
5. Leave the last 0.3s of any segment clear for a transition overlap.

## Output

Valid JSON only. No prose, no comments, no trailing commas. Write it to
`prompts/cutlist.json` in the project.

## Style recipes

Starting points, not rules. Deviate when the material asks for it.

**Editorial**: `transition_mode: "cross_dissolve"`, `transition_duration: 0.3`,
`ken_burns_easing: "cubic"`, sans-serif captions at 64px, 3-6s segments.

**Documentary**: cross dissolves at 0.5s, serif captions, fewer and longer
segments, `lufs_target: -16`, lower-third titles for speakers.

**Kinetic / brutalist**: hard cuts, 0.3-0.8s segments, monochrome, serif or
heavy sans captions in caps, `white_flash` on the drop, `strobe`, alternating
`grayscale` / `high_contrast_green` / `chromatic_aberration`. Set
`theme: "brutalist"` in `config.json` to get the base look.

**Talk-through**: one long take, `keyframes` for a slow push in, `speed: 1.0`,
captions carrying the argument, a single audio track with `cleanup: true`.
