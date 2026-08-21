# theming - Delta Spec

## ADDED Requirements

### Requirement: Theme schema and loader

A theme MUST be a JSON file with a defined schema covering: font stack, palette, text style (size, color, stroke), filter and effect defaults, audio defaults (music volume, duck amount), and transition defaults. config.json MUST accept a `theme` field naming a bundled theme or a theme file path. The loader MUST validate the theme against its schema, and MUST abort on unknown fields or invalid values.

#### Scenario: Theme applied

- GIVEN config.json with `theme: "clean_editorial"`
- WHEN the render runs
- THEN the graph uses the theme palette, font, text style, and default filters

#### Scenario: Invalid theme aborts

- GIVEN a theme file containing an unknown field
- WHEN the render starts
- THEN validation fails with a message naming the field

### Requirement: Bundled themes

The repo MUST ship at least four themes: `brutalist` (behavior parity with current defaults), `clean_editorial`, `documentary`, and `minimalist`. The brutalist theme with no explicit per-segment overrides MUST produce the same filter chain as the current engine for the same cutlist.

#### Scenario: Brutalist parity

- GIVEN the fixture cutlist with theme brutalist and no per-segment overrides
- WHEN the graph compiles
- THEN the emitted filter chain matches the current default chain for that cutlist

### Requirement: LUT color grading

config.json MUST accept a `lut` field pointing at a `.cube` or `.3dl` file. The graph MUST insert a lut3d node when a LUT is set. The LUT applies after the segment filters and before encoding.

#### Scenario: LUT in graph

- GIVEN config.json with `lut: "grade/teal.cube"`
- WHEN the graph compiles
- THEN the `filter_complex` string contains a lut3d node referencing the file

#### Scenario: Missing LUT file aborts

- GIVEN config.json with a `lut` path that does not exist
- WHEN the render starts
- THEN pre-flight validation aborts naming the missing LUT file

### Requirement: Parameterized transitions

The theme MUST define a transition model supporting at least: hard cut (default), cross-dissolve (xfade), dip to black, dip to white, and luma wipe. Ken Burns easing MUST support linear, cubic, and bezier curves. After transition insertion the timeline MUST be re-checked for continuity so the no-gap rule holds.

#### Scenario: Cross-dissolve

- GIVEN a cutlist with a cross-dissolve transition between two segments
- WHEN the graph compiles
- THEN the graph contains an xfade node with the configured duration

#### Scenario: Dip to black

- GIVEN a theme with dip-to-black transitions on drop boundaries
- WHEN the graph compiles
- THEN the graph contains a fade node on the drop boundary

#### Scenario: Cubic easing

- GIVEN a theme with `ken_burns_easing: cubic`
- WHEN the graph compiles
- THEN the zoompan expression uses cubic easing

### Requirement: Filter registry extension

New filters and effects defined by themes MUST register in `schemas/filter-effect-matrix.json`, which remains the single source of truth for filter and effect compatibility. The validation gate MUST reject cutlists referencing filters or effects not present in the matrix.

#### Scenario: Unknown filter rejected

- GIVEN a cutlist using a filter not present in the matrix
- WHEN validation runs
- THEN it aborts naming the unknown filter
