# rendering - Delta Spec

## ADDED Requirements

### Requirement: Single-pass filtergraph rendering

The render path MUST compile `config.json` and the validated cutlist into exactly one ffmpeg invocation using a `-filter_complex` graph. Video, text, and audio MUST be assembled inside that graph. No per-frame Python image processing MAY remain in the cutlist render path. The graph construction MUST live in a compiler module separate from the CLI.

#### Scenario: One ffmpeg process

- GIVEN the fixture project
- WHEN the render runs
- THEN the render log shows a single ffmpeg command containing `-filter_complex`

#### Scenario: No NumPy frame loop

- GIVEN the fixture project
- WHEN the render runs
- THEN the output is produced without executing `_contrast_crush`, `_chromatic_aberration`, or `_film_grain`

### Requirement: Filter parity

Each existing filter MUST map to native libavfilter nodes with equivalent output: `grayscale` (desaturation), `color_invert` (negate), `color_crush` (threshold crush via curves or eq), `high_contrast_green` and `high_contrast_red` (threshold crush plus accent color), `chromatic_aberration` (channel shift via split plus rgbashift or lutrgb), `film_grain` (seeded noise), and `white_flash` (timeline-evaluated color overlay).

#### Scenario: Filter appears in graph

- GIVEN a cutlist using `chromatic_aberration`
- WHEN the graph compiles
- THEN the `filter_complex` string contains a channel-shift node

#### Scenario: White flash is timeline-evaluated

- GIVEN a cutlist with a 0.08 second white_flash segment
- WHEN the graph compiles
- THEN the graph contains a white overlay node whose enable window matches the segment window

### Requirement: Effect parity

Each existing effect MUST map to native filters: `ken_burns_slow` (zoompan, 8% zoom, linear easing), `ken_burns_fast` (zoompan, 15% zoom, linear easing), and `snap_zoom` (zoompan step at segment midpoint). `strobe` remains an identity effect because the white_flash filter produces the flash frames. `word_flash` remains a passthrough in this spec and lands in Spec D.

#### Scenario: zoompan used

- GIVEN a cutlist using `ken_burns_slow`
- WHEN the graph compiles
- THEN the `filter_complex` string contains a zoompan node

#### Scenario: Snap zoom steps at midpoint

- GIVEN a 1.0 second segment with `snap_zoom`
- WHEN the graph compiles
- THEN the zoompan expression jumps at the segment midpoint

### Requirement: Text and audio parity

Center-positioned stroked text (current TextClip behavior) MUST render in the graph via drawtext with the configured font, size, color, and stroke. Soundtrack ducking to 30% under voiceover MUST render in the graph via volume and amix nodes. Text and audio behavior MUST match the current engine for the fixture cutlist. Specs D and E replace these with advanced versions in Phase 3.

#### Scenario: Text in graph

- GIVEN a cutlist segment with text `THE HEADLINE`
- WHEN the graph compiles
- THEN the `filter_complex` string contains a drawtext node carrying the text

#### Scenario: Ducking in graph

- GIVEN the fixture with a soundtrack and a voiceover
- WHEN the graph compiles
- THEN the graph contains volume and amix nodes

### Requirement: Deterministic output

Renders MUST be reproducible. Noise filters MUST use a fixed seed. The render path MUST hold no unseeded random state. Renderings of the same inputs MUST produce byte-identical output files.

#### Scenario: Re-render is identical

- GIVEN the fixture project
- WHEN the render runs twice with identical inputs
- THEN both output files are byte-identical

### Requirement: Container diet

The Containerfile MUST drop moviepy, librosa, pillow, and numpy from the Python install for the cutlist render path. ffmpeg remains a system package. Legacy beat-detect mode keeps librosa behind a lazy import so its CLI path still works.

#### Scenario: Image builds and renders

- GIVEN the updated Containerfile
- WHEN `podman build` runs and the fixture renders inside the container
- THEN the build succeeds and the render exits 0

### Requirement: Render output contract

The output MUST preserve the current contract: mp4 container, libx264-compatible video, aac audio, yuv420p pixel format, faststart flag, configured resolution and fps, and total duration equal to the cutlist span.

#### Scenario: Fixture output matches contract

- GIVEN the generated fixture
- WHEN the render completes
- THEN ffprobe reports the configured resolution, fps, and a duration matching the cutlist span
