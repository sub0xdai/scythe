# typography - Delta Spec

## ADDED Requirements

### Requirement: .ass subtitle pipeline

Text overlays MUST be generated as a styled .ass file and burned through the subtitles filter in the graph. The TextClip newline-padding hack MUST be removed from the render path. Font, size, color, stroke, and alignment MUST come from the theme or config.

#### Scenario: ASS generated

- GIVEN a cutlist segment with text `BUILD THE FUTURE`
- WHEN the graph compiles
- THEN a .ass file is written for the render and the graph contains a subtitles node referencing it

#### Scenario: No TextClip path

- GIVEN the fixture cutlist with text segments
- WHEN the render runs
- THEN the output renders without constructing a MoviePy TextClip

### Requirement: Bounding-box wrapping

Text MUST wrap to a configured bounding box defined by canvas-relative width and margins. Multi-line text MUST be vertically centered within its box. Wrapping MUST break on word boundaries.

#### Scenario: Long text wraps

- GIVEN 60 characters of text in a box at 80 percent canvas width with 72px font
- WHEN the .ass is generated
- THEN the text spans multiple lines and no line exceeds the box width

### Requirement: Platform safe zones

The theme MUST define safe-zone margins per orientation with documented defaults for 9:16 vertical (bottom 25 percent, top 12 percent). Text positions MUST clamp into the safe zone for the canvas orientation.

#### Scenario: Caption stays safe

- GIVEN a 1080x1920 canvas with default vertical safe zones
- WHEN a bottom-positioned caption is laid out
- THEN the caption bottom edge is at or above 75 percent canvas height

#### Scenario: Safe zones configurable

- GIVEN a theme with custom safe-zone margins
- WHEN a caption is laid out
- THEN the caption uses the custom margins, not the defaults

### Requirement: Per-word kinetic timing

The `word_flash` effect MUST be a real implementation using .ass karaoke `\k` tags. Words MUST reveal sequentially across the segment duration. Timing MUST be computed from segment duration and word count. This replaces the current passthrough behavior.

#### Scenario: Words reveal in order

- GIVEN a 2.0 second segment with `word_flash` and a 4-word text
- WHEN the .ass is generated
- THEN the file contains `\k` tags whose cumulative durations span the full 2.0 seconds

### Requirement: Lower-thirds

The cutlist MUST support a `lower_third` style object with a title line and a subtitle line. It MUST render as an animated lower-third inside the safe zone, appearing at the segment start.

#### Scenario: Lower third renders

- GIVEN a cutlist segment carrying a lower_third object
- WHEN the graph compiles
- THEN the .ass contains the two-line lower-third block at the safe-zone position with entrance timing at segment start
