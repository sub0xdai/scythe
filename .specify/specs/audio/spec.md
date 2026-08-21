# audio - Living Spec

## Requirements

### Requirement: Dynamic sidechain ducking

When a voiceover exists, the soundtrack MUST pass through `sidechaincompress` keyed on the voiceover instead of a static volume reduction. Duck depth and threshold MUST come from config or theme with documented defaults. The static 30 percent `volume` rule MUST be removed from the render path.

#### Scenario: Ducking follows speech

- GIVEN a soundtrack plus a voiceover with a silent gap in the middle
- WHEN the render runs
- THEN the soundtrack level during the silent gap is measurably higher than during speech

### Requirement: Loudness normalization

The final mix MUST pass through `loudnorm` targeting -14 LUFS by default, configurable per project or theme. The integrated loudness of the rendered output MUST be within plus or minus 1 LUFS of the target.

#### Scenario: Output meets LUFS target

- GIVEN the fixture audio mix
- WHEN the render completes
- THEN an ebur128 measurement of the output audio reports integrated loudness within -15 to -13 LUFS

### Requirement: Voice cleanup

Voiceover MUST pass through `afftdn` for noise suppression and `agate` for silence gating when enabled. Enablement MUST be configurable, defaulting to on.

#### Scenario: Hum reduced

- GIVEN a voiceover with a synthetic hum at a known frequency
- WHEN the render runs
- THEN the output voiceover shows reduced energy at the hum frequency compared to the input

#### Scenario: Cleanup can be disabled

- GIVEN config with voice cleanup disabled
- WHEN the render runs
- THEN the graph contains no afftdn or agate nodes

### Requirement: Audio processing in the graph

All audio processing MUST be graph nodes: sidechaincompress, loudnorm, afftdn, agate, and amix. No post-hoc Python audio processing MAY remain in the render path.

#### Scenario: Nodes present

- GIVEN the fixture with a voiceover
- WHEN the graph compiles
- THEN the `filter_complex` string contains sidechaincompress and loudnorm nodes