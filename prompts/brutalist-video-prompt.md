# Brutalist Kinetic Video Cut-List Generator

Feed this prompt to Claude, ChatGPT, or any LLM to generate a JSON cut-list for the kinetic video renderer.

---

You are an expert programmatic video editor. Generate a precise, frame-by-frame asset and edit timeline in JSON format for a high-velocity, brutalist short-form video.

## Output Video Specs

- Duration: 15-30 seconds
- Aspect ratio: 16:9 widescreen (1920×1080) — or specify your target
- Two-phase structure synchronized to a high-BPM soundtrack

### Phase 1: The Hook (0:00 - 0:05)
- Slow, tense, rhetorical
- Ken Burns effect on footage
- Monochrome visuals
- Text builds tension

### Phase 2: The Core Drop (0:05 - End)
- Hyper-kinetic, frantic
- Cuts on every audio transient (0.3-0.6s average)
- Rapid-fire visuals with alternating filters
- White flash strobes on beat drops

## Visual Aesthetic

1. **Color:** High-contrast monochrome with neon accents (green/red)
2. **Typography:** Sans-serif or serif, thick black stroke, UPPERCASE, word-by-word hard cuts
3. **Degradation:** Film grain, chromatic aberration, contrast crushing
4. **Transitions:** Hard cuts only. No dissolves. White flash on drops.

## Asset Categories

Reference paths relative to the project root:
- `raw_footage/` — Video clips and images
- `overlays/` — Logos, grids, textures

## Output Format

Valid JSON array only. No conversational filler.

```json
[
  {
    "start": 0.0,
    "end": 1.0,
    "phase": "hook",
    "text": "YOUR HEADLINE",
    "asset": "raw_footage/clip.mp4",
    "filter": "grayscale",
    "effect": "ken_burns_slow"
  },
  {
    "start": 5.0,
    "end": 5.08,
    "phase": "drop_transition",
    "text": null,
    "asset": null,
    "filter": "white_flash",
    "effect": "strobe"
  },
  {
    "start": 5.08,
    "end": 5.53,
    "phase": "kinetic_cut",
    "text": "CALL TO ACTION",
    "asset": "raw_footage/action.mp4",
    "filter": "high_contrast_green",
    "effect": "snap_zoom"
  }
]
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `start` | float | Start timestamp (seconds) |
| `end` | float | End timestamp (seconds) |
| `phase` | string | `hook`, `drop_transition`, or `kinetic_cut` |
| `text` | string\|null | UPPERCASE overlay text. Null for flash frames |
| `asset` | string\|null | Relative path to source file. Null for flash frames |
| `filter` | string\|null | `grayscale`, `color_invert`, `high_contrast_green`, `high_contrast_red`, `white_flash`, `chromatic_aberration`, `film_grain`, `color_crush` |
| `effect` | string\|null | `ken_burns_slow`, `ken_burns_fast`, `snap_zoom`, `strobe`, `word_flash` |
| `overlays` | array | Alpha layers composited over the segment (logos, scanlines, rain) |

### Overlays

A segment can composite alpha layers over the footage via `overlays`. Useful for logos, scanlines, money rain, skull rain. Each overlay:

| Field | Type | Description |
|-------|------|-------------|
| `asset` | string | Relative path to RGBA image or video with alpha (`overlays/`) |
| `x`, `y` | float | Base position in px (default 0) |
| `dx`, `dy` | float | Drift in px/sec (e.g. `dy: -300` makes rain fall) |
| `opacity` | float | 0..1 (default 1) |

The overlay stays for the segment's full duration. For a sub-window, split the segment.

### Copywriting Rules

- UPPERCASE only, 2-5 words max
- Declarative, mechanical tone
- No marketing fluff or adjectives
